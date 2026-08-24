"""The crop rectangle that was sent, recorded next to the answer it produced.

A prediction made from 13.7% of the frame is scored against a label drawn
anywhere in the frame, so the rectangle is part of the number's meaning. Until
now only crown.py wrote it down and ingest_photos.py dropped it, which left the
dashboard recomputing the rectangle from a constant and no way to notice a frame
that broke the constant.

    python -m unittest discover tests
"""

import importlib.util
import io
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


try:
    ingest = _load("_ingest_under_test", REPO / "predict" / "ingest_photos.py")
    from PIL import Image
except Exception as exc:                                    # noqa: BLE001
    ingest = None
    _why = str(exc)


def _jpeg(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (11, 99, 33)).save(buf, format="JPEG")
    return buf.getvalue()


@unittest.skipIf(ingest is None, "predict deps not installed")
class CenterCropReportsWhatItSent(unittest.TestCase):
    def test_large_frame_is_cropped_and_the_box_is_the_centre_square(self):
        jpeg, w, h, box = ingest.center_crop_jpeg_from_bytes(_jpeg(4000, 3000))
        self.assertEqual((w, h), (4000, 3000))
        self.assertEqual(box, (1360, 860, 2640, 2140))
        self.assertEqual(Image.open(io.BytesIO(jpeg)).size,
                         (ingest.CROP_SIZE, ingest.CROP_SIZE))

    def test_small_frame_is_sent_whole_and_says_so(self):
        # The uncropped branch is the one that silently breaks a downstream
        # constant, so the box has to cover the frame rather than be omitted.
        jpeg, w, h, box = ingest.center_crop_jpeg_from_bytes(_jpeg(800, 600))
        self.assertEqual(box, (0, 0, 800, 600))
        self.assertEqual(Image.open(io.BytesIO(jpeg)).size, (800, 600))

    def test_box_matches_the_rectangle_the_dashboard_assumes(self):
        sys.path.insert(0, str(REPO / "dashboard"))
        self.addCleanup(sys.path.remove, str(REPO / "dashboard"))
        import crop_overlap
        _, w, h, box = ingest.center_crop_jpeg_from_bytes(
            _jpeg(crop_overlap.FRAME_W, crop_overlap.FRAME_H))
        self.assertEqual(box, crop_overlap.crop_rect(w, h))


@unittest.skipIf(ingest is None, "predict deps not installed")
class StampGeometry(unittest.TestCase):
    def test_the_stamp_carries_frame_size_and_box_in_photo_pixels(self):
        out = ingest.stamp_geometry({"results": {}}, 4000, 3000,
                                    (1360, 860, 2640, 2140))
        crop = out["crop"]
        self.assertEqual(crop["frame_width"], 4000)
        self.assertEqual(crop["frame_height"], 3000)
        self.assertEqual(crop["crop_size"], ingest.CROP_SIZE)
        self.assertEqual(crop["unit"], "photo")
        self.assertEqual(crop["box"], {"x_min": 1360, "y_min": 860,
                                       "x_max": 2640, "y_max": 2140})

    def test_the_answer_is_left_alone(self):
        payload = {"results": {"species": [{"binomial": "Hura crepitans"}]}}
        out = ingest.stamp_geometry(payload, 4000, 3000, (0, 0, 4000, 3000))
        self.assertEqual(out["results"]["species"][0]["binomial"],
                         "Hura crepitans")


if __name__ == "__main__":
    unittest.main()
