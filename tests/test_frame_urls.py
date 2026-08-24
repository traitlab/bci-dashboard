"""A box whose frame cannot be resolved must not be dropped in silence.

Three global-key namespaces exist and only the basename is common between them.
The tracked frame list covers the 2024 corpus; frames ingested since resolve
only through the dataset inventory. When `load_frame_urls` read one source and
keyed on the full global key, every tele box fell through as `no_frame_url` and
six consecutive runs reported `requested ok: 0, errors: 0`, which reads as a
completed job.

    python -m unittest discover tests
"""

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


try:
    crown = _load("_crown_under_test", REPO / "predict" / "crown.py")
except Exception as exc:                                    # noqa: BLE001
    crown = None
    _why = str(exc)


def _frames_csv(tmp, rows):
    path = pathlib.Path(tmp) / "frames.csv"
    lines = ["global_key,image_url,mission,split"]
    lines += [f"{k},{u},m,train" for k, u in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rows_jsonl(tmp, rows):
    path = pathlib.Path(tmp) / "rows.jsonl"
    path.write_text(
        "".join(json.dumps({"global_key": k, "row_data": u}) + "\n" for k, u in rows),
        encoding="utf-8")
    return path


@unittest.skipIf(crown is None, "crown.py did not import")
class FrameUrlsSpanEveryNamespace(unittest.TestCase):
    def test_a_frame_only_in_the_inventory_still_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _frames_csv(tmp, [("A_zoom.JPG", "http://zoom")])
            jsonl = _rows_jsonl(tmp, [("flight_folder/B_tele.JPG", "http://tele")])
            urls = crown.load_frame_urls(csv_path, jsonl)
        self.assertEqual(urls.get("B_tele.JPG"), "http://tele")
        self.assertEqual(urls.get("A_zoom.JPG"), "http://zoom")

    def test_a_prefixed_global_key_is_found_by_its_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _frames_csv(tmp, [("comb_A_zoom.JPG", "http://csv")])
            jsonl = _rows_jsonl(tmp, [("migrated/comb_A_zoom.JPG", "http://inv")])
            urls = crown.load_frame_urls(csv_path, jsonl)
        # The tracked frame list is the definition of the population, so it wins.
        self.assertEqual(urls.get("comb_A_zoom.JPG"), "http://csv")

    def test_a_missing_inventory_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _frames_csv(tmp, [("A_zoom.JPG", "http://zoom")])
            urls = crown.load_frame_urls(csv_path, pathlib.Path(tmp) / "absent.jsonl")
        self.assertEqual(urls, {"A_zoom.JPG": "http://zoom"})


@unittest.skipIf(crown is None, "crown.py did not import")
class PlanCountsWhatItCannotFetch(unittest.TestCase):
    BOX = (0, 0, 900, 900, "Label")

    def test_an_unresolvable_frame_is_counted_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            todo, dropped = crown.plan(
                {"A_zoom.JPG": [self.BOX], "B_tele.JPG": [self.BOX]},
                {"A_zoom.JPG": "http://zoom"},
                pathlib.Path(tmp))
        self.assertEqual(len(todo), 1)
        self.assertEqual(dropped["no_frame_url"], 1)

    def test_a_resolvable_frame_reaches_the_todo(self):
        with tempfile.TemporaryDirectory() as tmp:
            todo, dropped = crown.plan(
                {"B_tele.JPG": [self.BOX]},
                {"B_tele.JPG": "http://tele"},
                pathlib.Path(tmp))
        self.assertEqual(dropped["no_frame_url"], 0)
        self.assertEqual([t[1] for t in todo], ["http://tele"])


@unittest.skipIf(crown is None, "crown.py did not import")
class ARunThatWouldDropCrownsExitsNonZero(unittest.TestCase):
    def test_exit_code_is_two_when_a_frame_has_no_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            boxes = tmp / "boxes.csv"
            boxes.write_text(
                "base_image,x_min,y_min,x_max,y_max,lb_label\n"
                "B_tele.JPG,0,0,900,900,Label\n", encoding="utf-8")
            csv_path = _frames_csv(tmp, [("A_zoom.JPG", "http://zoom")])
            jsonl = _rows_jsonl(tmp, [])
            code = crown.main([
                "--boxes-csv", str(boxes), "--frames-csv", str(csv_path),
                "--frames-jsonl", str(jsonl), "--out-dir", str(tmp / "out"),
            ])
        self.assertEqual(code, 2)

    def test_the_escape_hatch_lets_the_run_proceed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            boxes = tmp / "boxes.csv"
            boxes.write_text(
                "base_image,x_min,y_min,x_max,y_max,lb_label\n"
                "B_tele.JPG,0,0,900,900,Label\n", encoding="utf-8")
            csv_path = _frames_csv(tmp, [("A_zoom.JPG", "http://zoom")])
            jsonl = _rows_jsonl(tmp, [])
            code = crown.main([
                "--boxes-csv", str(boxes), "--frames-csv", str(csv_path),
                "--frames-jsonl", str(jsonl), "--out-dir", str(tmp / "out"),
                "--allow-missing-frames",
            ])
        self.assertIsNot(code, 2)


if __name__ == "__main__":
    unittest.main()
