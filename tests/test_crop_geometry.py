"""The crop rectangle that was sent, recorded next to the answer it produced.

A prediction made from 13.7% of the frame is scored against a label drawn
anywhere in the frame, so the rectangle is part of the number's meaning. Until
now only crown.py wrote it down and ingest_photos.py dropped it, which left the
dashboard recomputing the rectangle from a constant and no way to notice a frame
that broke the constant.

    .venv/bin/pytest tests/test_crop_geometry.py
"""

import io

import pytest


@pytest.fixture
def jpeg():
    """A solid JPEG of a given size, as bytes."""
    Image = pytest.importorskip("PIL.Image", reason="predict needs PIL")

    def make(w, h):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (11, 99, 33)).save(buf, format="JPEG")
        return buf.getvalue()

    return make


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
