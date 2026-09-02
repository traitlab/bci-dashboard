"""The crop rectangle that was sent, recorded next to the answer it produced.

A prediction made from 13.7% of the frame is scored against a label drawn
anywhere in the frame, so the rectangle is part of the number's meaning. Until
now only crown.py wrote it down and ingest_photos.py dropped it, which left the
dashboard recomputing the rectangle from a constant and no way to notice a frame
that broke the constant.

    .venv/bin/pytest tests/test_crop_geometry.py
"""

import io


def _size(data):
    from PIL import Image
    return Image.open(io.BytesIO(data)).size


class TestCenterCropReportsWhatItSent:
    def test_large_frame_is_cropped_and_the_box_is_the_centre_square(
            self, ingest, jpeg):
        data, w, h, box = ingest.center_crop_jpeg_from_bytes(jpeg(4000, 3000))
        assert (w, h) == (4000, 3000)
        assert box == (1360, 860, 2640, 2140)
        assert _size(data) == (ingest.CROP_SIZE, ingest.CROP_SIZE)

    def test_small_frame_is_sent_whole_and_says_so(self, ingest, jpeg):
        # The uncropped branch is the one that silently breaks a downstream
        # constant, so the box has to cover the frame rather than be omitted.
        data, _w, _h, box = ingest.center_crop_jpeg_from_bytes(jpeg(800, 600))
        assert box == (0, 0, 800, 600)
        assert _size(data) == (800, 600)

    def test_box_matches_the_rectangle_the_dashboard_assumes(
            self, ingest, jpeg, crop_overlap):
        _, w, h, box = ingest.center_crop_jpeg_from_bytes(
            jpeg(crop_overlap.FRAME_W, crop_overlap.FRAME_H))
        assert box == crop_overlap.crop_rect(w, h)


class TestStampGeometry:
    def test_the_stamp_carries_frame_size_and_box_in_photo_pixels(self, ingest):
        out = ingest.stamp_geometry({"results": {}}, 4000, 3000,
                                    (1360, 860, 2640, 2140))
        crop = out["crop"]
        assert crop["frame_width"] == 4000
        assert crop["frame_height"] == 3000
        assert crop["crop_size"] == ingest.CROP_SIZE
        assert crop["unit"] == "photo"
        assert crop["box"] == {"x_min": 1360, "y_min": 860,
                               "x_max": 2640, "y_max": 2140}

    def test_the_answer_is_left_alone(self, ingest):
        payload = {"results": {"species": [{"binomial": "Hura crepitans"}]}}
        out = ingest.stamp_geometry(payload, 4000, 3000, (0, 0, 4000, 3000))
        assert out["results"]["species"][0]["binomial"] == "Hura crepitans"


def test_both_fetch_paths_cut_the_same_square(ingest, photo, jpeg):
    """The two fetchers used to hold a centre crop each, one returning the
    rectangle it sent and one returning the crop size, at the same quality by
    coincidence rather than by construction. They are one function now, and a
    second copy would mean the model sees different pixels depending on which
    script fetched the photo."""
    # Compared by where the code lives, not by identity: the fixtures load
    # photo.py twice, once by path and once as ingest_photos' sibling.
    took_from = ingest.center_crop_jpeg_from_bytes.__code__.co_filename
    assert took_from.endswith("predict/photo.py"), (
        f"ingest_photos.py crops with code from {took_from}. There is one "
        f"centre crop, in photo.py, and both fetch paths call it.")
    for size in ((4000, 3000), (1279, 2000)):
        raw = jpeg(*size)
        sent, w, h, box = photo.center_crop_jpeg_box(raw)
        also, w2, h2, crop_s = photo.center_crop_jpeg(raw)
        assert (sent, w, h) == (also, w2, h2)
        # The two return shapes have to describe one rectangle: the crop size
        # is set exactly when the box is the centre square.
        assert crop_s == (photo.CROP_SIZE
                          if box[2] - box[0] == photo.CROP_SIZE else None)


def test_the_two_remaining_copies_of_the_crop_size_agree(ingest, photo, crop_overlap):
    """1280 is written down twice now, and the comment names one of them.

    `predict/photo.py` cuts the square for both fetch paths, and
    `dashboard/crop_overlap.py` reconstructs it to decide how much of the crop
    a labelled crown covers. `crop_overlap.py:23` says "Must match CROP_SIZE in
    predict/photo.py", which is the copy that filled the cache the pages score.
    `predict/` needs PIL and a key, so it cannot import from `dashboard/`; this
    compares them instead.
    """
    assert photo.CROP_SIZE == ingest.CROP_SIZE == crop_overlap.CROP_SIZE, (
        f"predict/photo.py {photo.CROP_SIZE}, predict/ingest_photos.py "
        f"{ingest.CROP_SIZE}, dashboard/crop_overlap.py {crop_overlap.CROP_SIZE}. "
        f"The dashboard reconstructs the crop from its own copy, so a mismatch "
        f"scores every prediction against the wrong rectangle.")


def test_the_edge_tolerance_still_covers_what_the_boxes_actually_do(crop_overlap):
    """EDGE_TOLERANCE is a judgement call, and its comment holds the evidence.

    `crop_overlap.py` admits a box up to EDGE_TOLERANCE px outside the frame
    because the comment above it measured the overhang: 286 of 3,280 frames in
    the tracked box file overhang by 1 to 2 px, and the largest coordinate seen
    is 4002 x 3002. Nothing recomputed any of that. Re-export the boxes at a
    real second resolution and the comment keeps reporting the old corpus while
    the tolerance quietly reclassifies frames as suspect.
    """
    import collections
    import csv
    import pathlib
    import re

    src = pathlib.Path(crop_overlap.__file__).read_text(encoding="utf-8")
    said = re.search(r"# ([\d,]+) of ([\d,]+) frames have a box edge (\d)-(\d) px outside"
                     r".*?largest coordinate is (\d+) x (\d+)", src, re.DOTALL)
    assert said, "crop_overlap.py no longer records what the overhang measured"
    n_over, n_frames, lo, hi, max_x, max_y = (int(g.replace(",", "")) for g in said.groups())

    frames = collections.defaultdict(list)
    with open(crop_overlap.BOXES_CSV, newline="") as fh:
        for r in csv.DictReader(fh):
            frames[r["base_image"]].append((int(r["x_max"]), int(r["y_max"])))
    boxes = [b for bs in frames.values() for b in bs]
    over = [f for f, bs in frames.items()
            if any(x > crop_overlap.FRAME_W or y > crop_overlap.FRAME_H for x, y in bs)]
    excess = {max(x - crop_overlap.FRAME_W, 0) for x, y in boxes} | \
             {max(y - crop_overlap.FRAME_H, 0) for x, y in boxes}

    assert (len(over), len(frames)) == (n_over, n_frames), (
        f"the comment says {n_over} of {n_frames} frames overhang, the tracked "
        f"box file has {len(over)} of {len(frames)}.")
    assert (max(x for x, _ in boxes), max(y for _, y in boxes)) == (max_x, max_y), (
        f"the comment says the largest coordinate is {max_x} x {max_y}.")
    assert sorted(excess) == [0] + list(range(lo, hi + 1)), (
        f"the comment says the overhang is {lo} to {hi} px, the file overhangs "
        f"by {sorted(excess - {0})} px.")
    assert max(excess) < crop_overlap.EDGE_TOLERANCE, (
        f"EDGE_TOLERANCE is {crop_overlap.EDGE_TOLERANCE} and a box now hangs "
        f"{max(excess)} px outside the frame, so the rounding artifact the "
        f"tolerance was sized for is no longer what it is admitting.")
