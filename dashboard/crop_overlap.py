"""What Pl@ntNet actually saw, and how much of the label it covered.

Predictions use a fixed CROP_SIZE square at the frame centre; labels are
boxes anywhere in the frame. Recomputes the rectangle offline and scores
each label's share of it, admitting a frame only past threshold T.

No API, no Labelbox. ``export_boxes.csv`` (July 2026 revision) wins per
frame over the older ``crop_bounding_boxes.csv``, which fills gaps; where
both cover a frame, the old file has twice the boxes, only 35% matching a
current crown at IoU 0.5, a fifth superseded.

All 16 sampled frames measured exactly FRAME_W x FRAME_H, so the
rectangle is constant; contradicting boxes go to `suspect_frames` instead
of being scored wrong.
"""

import collections
import csv
import os

from core import REPO, strip_collection_codes

# Must match CROP_SIZE in predict/photo.py and predict/ingest_photos.py.
# The second is the one that filled the cache the pages score.
# tests/test_crop_geometry.py compares all three.
CROP_SIZE = 1280

# Verified constant across the sampled corpus. Used only when a frame's real
# dimensions are unknown, which is the normal case: the cache written by
# predict/ingest_photos.py stores no geometry.
FRAME_W = 4000
FRAME_H = 3000

BOXES_CSV = os.path.join(REPO, "input", "boxes", "crop_bounding_boxes.csv")
EXPORT_BOXES_CSV = os.path.join(REPO, "data", "export_boxes.csv")

# 286 of 3,280 frames have a box edge 1-2 px outside it, a rounding artifact
# rather than a second resolution (the largest coordinate is 4002 x 3002).
EDGE_TOLERANCE = 4


def crop_rect(frame_w=FRAME_W, frame_h=FRAME_H, crop_size=CROP_SIZE):
    """The rectangle the prediction scripts sent, as (x0, y0, x1, y1).

    None when the frame is smaller than crop_size in either dimension:
    center_crop_jpeg then sends the whole image untouched.
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

    Export geometry wins whole per frame, not merged box by box: that
    would reintroduce crowns the revision removed. Frames absent from the
    export keep their old boxes. ``export_path=None`` reads the old file
    alone, for regression tests.

    lb_label's trailing BCI collection codes are stripped here, since a
    code is upper case and cannot be told from a hyphenated epithet once
    normalize() lowers the string.
    """
    frames = _read_boxes(path)
    if export_path and os.path.exists(export_path):
        frames.update(_read_boxes(export_path))
    return frames


def frame_coverage(boxes, rect):
    """Fraction of `rect` each species in `boxes` covers.

    A species can exceed 1 where its own boxes overlap, hence the clamp.
    """
    rect_area = (rect[2] - rect[0]) * (rect[3] - rect[1])
    per = collections.Counter()
    for b in boxes:
        a = _intersect_area(b[:4], rect)
        if a > 0:
            per[b[4]] += a
    return {sp: min(a / rect_area, 1.0) for sp, a in per.items()}


def build():
    """Per-frame view of what the model saw.

    Returns (frames, suspect_frames): frames maps base_image to
    {"dominant": top species (or None), "coverage": its fraction}.
    suspect_frames lists base_images whose boxes fall outside the frame
    size, so their rectangle cannot be trusted.

    The two box files and the frame geometry are the module constants above.
    They were once five parameters defaulting to those constants, which no
    caller in the repo ever passed and no test could have overridden anyway:
    a default is bound when the function is defined, so pointing the module
    at another file would not have moved them.
    """
    rect = crop_rect()
    if rect is None:
        raise ValueError(
            f"frame {FRAME_W}x{FRAME_H} is smaller than crop {CROP_SIZE}; "
            "13a sends such frames uncropped, so there is no rectangle to score"
        )
    out, suspect = {}, []
    for base, boxes in load_boxes(BOXES_CSV, EXPORT_BOXES_CSV).items():
        if any(b[2] > FRAME_W + EDGE_TOLERANCE or b[3] > FRAME_H + EDGE_TOLERANCE
               for b in boxes):
            suspect.append(base)
            continue
        boxes = [(max(0, b[0]), max(0, b[1]),
                  min(b[2], FRAME_W), min(b[3], FRAME_H), b[4]) for b in boxes]
        per = frame_coverage(boxes, rect)
        dominant, cov = (None, 0.0)
        if per:
            dominant, cov = max(per.items(), key=lambda kv: kv[1])
        out[base] = {"dominant": dominant, "coverage": cov}
    return out, suspect
