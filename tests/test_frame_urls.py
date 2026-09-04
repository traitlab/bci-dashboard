"""A box whose frame cannot be resolved must not be dropped in silence.

Three global-key namespaces exist and only the basename is common between them.
The tracked frame list covers the 2024 corpus; frames ingested since resolve
only through the dataset inventory. When `load_frame_urls` read one source and
keyed on the full global key, every tele box fell through as `no_frame_url` and
six consecutive runs reported `requested ok: 0, errors: 0`, which reads as a
completed job.

    .venv/bin/pytest tests/test_frame_urls.py
"""

import json

import pytest

BOX = (0, 0, 900, 900, "Label")


@pytest.fixture
def frames_csv(tmp_path):
    def make(rows):
        path = tmp_path / "frames.csv"
        lines = ["global_key,image_url,mission,split"]
        lines += [f"{k},{u},m,train" for k, u in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
    return make


@pytest.fixture
def rows_jsonl(tmp_path):
    def make(rows):
        path = tmp_path / "rows.jsonl"
        path.write_text(
            "".join(json.dumps({"global_key": k, "row_data": u}) + "\n"
                    for k, u in rows),
            encoding="utf-8")
        return path
    return make


@pytest.fixture
def boxes_csv(tmp_path):
    path = tmp_path / "boxes.csv"
    path.write_text(
        "base_image,x_min,y_min,x_max,y_max,lb_label\n"
        "B_tele.JPG,0,0,900,900,Label\n", encoding="utf-8")
    return path


class TestFrameUrlsSpanEveryNamespace:
    def test_a_frame_only_in_the_inventory_still_resolves(
            self, crown, frames_csv, rows_jsonl):
        urls = crown.load_frame_urls(
            frames_csv([("A_zoom.JPG", "http://zoom")]),
            rows_jsonl([("flight_folder/B_tele.JPG", "http://tele")]))
        assert urls.get("B_tele.JPG") == "http://tele"
        assert urls.get("A_zoom.JPG") == "http://zoom"

    def test_a_prefixed_global_key_is_found_by_its_basename(
            self, crown, frames_csv, rows_jsonl):
        urls = crown.load_frame_urls(
            frames_csv([("comb_A_zoom.JPG", "http://csv")]),
            rows_jsonl([("migrated/comb_A_zoom.JPG", "http://inv")]))
        # The tracked frame list is the definition of the population, so it wins.
        assert urls.get("comb_A_zoom.JPG") == "http://csv"

    def test_a_missing_inventory_is_not_an_error(
            self, crown, frames_csv, tmp_path):
        urls = crown.load_frame_urls(
            frames_csv([("A_zoom.JPG", "http://zoom")]),
            tmp_path / "absent.jsonl")
        assert urls == {"A_zoom.JPG": "http://zoom"}


class TestPlanCountsWhatItCannotFetch:
    def test_an_unresolvable_frame_is_counted_not_swallowed(
            self, crown, tmp_path):
        todo, dropped = crown.plan(
            {"A_zoom.JPG": [BOX], "B_tele.JPG": [BOX]},
            {"A_zoom.JPG": "http://zoom"},
            tmp_path)
        assert len(todo) == 1
        assert dropped["no_frame_url"] == 1

    def test_a_resolvable_frame_reaches_the_todo(self, crown, tmp_path):
        todo, dropped = crown.plan(
            {"B_tele.JPG": [BOX]},
            {"B_tele.JPG": "http://tele"},
            tmp_path)
        assert dropped["no_frame_url"] == 0
        assert [t[1] for t in todo] == ["http://tele"]


class TestARunThatWouldDropCrownsExitsNonZero:
    def _run(self, crown, tmp_path, boxes, frames, rows, *extra):
        return crown.main([
            "--boxes-csv", str(boxes), "--frames-csv", str(frames),
            "--frames-jsonl", str(rows), "--out-dir", str(tmp_path / "out"),
            *extra,
        ])

    def test_exit_code_is_two_when_a_frame_has_no_url(
            self, crown, tmp_path, boxes_csv, frames_csv, rows_jsonl):
        code = self._run(crown, tmp_path, boxes_csv,
                         frames_csv([("A_zoom.JPG", "http://zoom")]),
                         rows_jsonl([]))
        assert code == 2

    def test_the_escape_hatch_lets_the_run_proceed(
            self, crown, tmp_path, boxes_csv, frames_csv, rows_jsonl):
        code = self._run(crown, tmp_path, boxes_csv,
                         frames_csv([("A_zoom.JPG", "http://zoom")]),
                         rows_jsonl([]), "--allow-missing-frames")
        assert code != 2
