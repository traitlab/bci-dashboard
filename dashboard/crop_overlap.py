"""What Pl@ntNet actually saw, and how much of the label it covered.

The prediction scripts send Pl@ntNet a fixed CROP_SIZE square cut from the
centre of each base drone frame, then discard the crop offsets. Ground truth,
meanwhile, comes from crown bounding boxes drawn anywhere in the full frame. So
a prediction made from 13.7% of the frame is scored against a label that may lie
entirely outside it.

This module recomputes the crop rectangle offline and measures, per frame, how
much of that rectangle each labelled species covers. Downstream code uses the
coverage fraction to admit or reject a frame: admit only if one species covers at
least T of the region the model saw.

Nothing here calls an API or touches Labelbox. It reads crown geometry from
two files and prefers the newer one per frame. ``data/export_boxes.csv`` comes
from the Labelbox export (labelling/gt_from_export.py) and matches the July 2026
botanist revision. ``input/boxes/crop_bounding_boxes.csv`` predates it and is
kept only for the frames the export does not cover: where both describe a frame,
the old file holds twice as many boxes, only 35% of them are the same crown at
IoU 0.5, and a fifth of even those carry a superseded species.

Frame geometry: all 16 randomly sampled base frames (2024-2026, zoom and tele)
measured exactly FRAME_W x FRAME_H, so the crop rectangle is constant. Frames
that contradict that are reported in `suspect_frames` rather than silently
scored, because their crop rectangle would be wrong.
"""

import collections
import csv
import os

from core import REPO, strip_collection_codes

# Must match CROP_SIZE in predict/photo.py
CROP_SIZE = 1280

# Verified constant across the sampled corpus. Used only when a frame's real
# dimensions are unknown, which is the normal case: the cache written by
# predict/ingest_photos.py stores no geometry.
FRAME_W = 4000
FRAME_H = 3000

BOXES_CSV = os.path.join(REPO, "input", "boxes", "crop_bounding_boxes.csv")
EXPORT_BOXES_CSV = os.path.join(REPO, "data", "export_boxes.csv")

# Default admission threshold: the dominant species must cover at least this
# fraction of the crop.
DEFAULT_MIN_COVERAGE = 0.50

# 286 of the 3,280 frames have a box edge 1-2 px outside the frame, which is a
# rounding artifact from whatever drew them, not a second camera resolution (the
# largest coordinate anywhere is 4002 x 3002). Clamp within this tolerance and
# only treat a bigger overshoot as a genuinely unknown frame size.
EDGE_TOLERANCE = 4


def crop_rect(frame_w=FRAME_W, frame_h=FRAME_H, crop_size=CROP_SIZE):
    """The rectangle the prediction scripts sent, as (x0, y0, x1, y1).

    Returns None when the frame is smaller than crop_size in either dimension,
    which is the branch where center_crop_jpeg sends the whole image untouched.
    """
    if frame_w < crop_size or frame_h < crop_size:
        return None
    x0 = (frame_w - crop_size) // 2
    y0 = (frame_h - crop_size) // 2
    return (x0, y0, x0 + crop_size, y0 + crop_size)


def _intersect_area(box, rect):
    bx0, by0, bx1, by1 = box
    rx0, ry0, rx1, ry1 = rect
    w = min(bx1, rx1) - max(bx0, rx0)
    h = min(by1, ry1) - max(by0, ry0)
    return max(0, w) * max(0, h)


def _read_boxes(path):
    """One geometry file -> base_image -> list of (x0, y0, x1, y1, species)."""
    frames = collections.defaultdict(list)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            frames[r["base_image"]].append((
                int(r["x_min"]), int(r["y_min"]),
                int(r["x_max"]), int(r["y_max"]),
                strip_collection_codes(r["lb_label"]),
            ))
    return frames


def load_boxes(path=BOXES_CSV, export_path=EXPORT_BOXES_CSV):
    """base_image -> list of (x0, y0, x1, y1, normalized_species).

    Export geometry wins per frame, whole. The two sources are not merged box by
    box: a frame the botanists revised has a complete, current set of crowns, and
    mixing superseded boxes back in would reintroduce exactly the crowns they
    removed. Frames absent from the export keep their old boxes.

    Pass ``export_path=None`` to read the old file alone, which is what the
    regression tests do.

    lb_label carries trailing BCI collection codes ('Hura crepitans-HURACR-HURC').
    They come off here rather than downstream, because they are recognised by
    being upper case: once normalize() has lowered the string a code can no
    longer be told from a hyphenated epithet, and the name would never compare
    equal to a GT species again.
    """
    frames = _read_boxes(path)
    if export_path and os.path.exists(export_path):
        frames.update(_read_boxes(export_path))
    return frames


def frame_coverage(boxes, rect):
    """Coverage of `rect` by each species in `boxes`.

    Returns (per_species_fraction, n_boxes_overlapping). Fractions are areas
    divided by the rect area, so they sum to at most 1 only when crowns of
    different species do not overlap; a single species can exceed 1 if its own
    boxes overlap, hence the clamp.
    """
    rect_area = (rect[2] - rect[0]) * (rect[3] - rect[1])
    per = collections.Counter()
    n_boxes = 0
    for b in boxes:
        a = _intersect_area(b[:4], rect)
        if a > 0:
            per[b[4]] += a
            n_boxes += 1
    return {sp: min(a / rect_area, 1.0) for sp, a in per.items()}, n_boxes


def build(path=BOXES_CSV, frame_w=FRAME_W, frame_h=FRAME_H,
          crop_size=CROP_SIZE, export_path=EXPORT_BOXES_CSV):
    """Per-frame view of what the model saw.

    Returns (frames, suspect_frames) where frames maps base_image to a dict:
        dominant        species covering most of the crop, or None
        coverage        that species' fraction of the crop
        any_coverage    fraction covered by any labelled crown
        n_species       distinct labelled species overlapping the crop
        n_boxes         labelled boxes overlapping the crop
        crop_rect       the rectangle used
    suspect_frames lists base_images whose boxes fall outside the assumed frame
    size, so their crop rectangle cannot be trusted.
    """
    rect = crop_rect(frame_w, frame_h, crop_size)
    if rect is None:
        raise ValueError(
            f"frame {frame_w}x{frame_h} is smaller than crop {crop_size}; "
            "13a sends such frames uncropped, so there is no rectangle to score"
        )
    out, suspect = {}, []
    for base, boxes in load_boxes(path, export_path).items():
        if any(b[2] > frame_w + EDGE_TOLERANCE or b[3] > frame_h + EDGE_TOLERANCE
               for b in boxes):
            suspect.append(base)
            continue
        boxes = [(max(0, b[0]), max(0, b[1]),
                  min(b[2], frame_w), min(b[3], frame_h), b[4]) for b in boxes]
        per, n_boxes = frame_coverage(boxes, rect)
        dominant, cov = (None, 0.0)
        if per:
            dominant, cov = max(per.items(), key=lambda kv: kv[1])
        out[base] = {
            "dominant": dominant,
            "coverage": cov,
            "any_coverage": min(sum(per.values()), 1.0),
            "n_species": len(per),
            "n_boxes": n_boxes,
            "crop_rect": rect,
        }
    return out, suspect
