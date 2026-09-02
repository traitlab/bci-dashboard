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


def test_the_three_copies_of_the_crop_size_agree(ingest, photo, crop_overlap):
    """1280 is written down three times, and the comment names one of them.

    `predict/photo.py` and `predict/ingest_photos.py` each cut the square, and
    `dashboard/crop_overlap.py` reconstructs it to decide how much of the crop
    a labelled crown covers. `crop_overlap.py:23` says "Must match CROP_SIZE in
    predict/photo.py" and does not mention the third, which is the one that
    actually filled the cache the pages score. `predict/` needs PIL and a key,
    so it cannot import from `dashboard/`; this compares them instead.
    """
    assert photo.CROP_SIZE == ingest.CROP_SIZE == crop_overlap.CROP_SIZE, (
        f"predict/photo.py {photo.CROP_SIZE}, predict/ingest_photos.py "
        f"{ingest.CROP_SIZE}, dashboard/crop_overlap.py {crop_overlap.CROP_SIZE}. "
        f"The dashboard reconstructs the crop from its own copy, so a mismatch "
        f"scores every prediction against the wrong rectangle.")
