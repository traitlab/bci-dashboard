"""The two controls that say what the camera classes do and do not share.

Both exist because the numbers they print were prose in a spec before they were
code. Control 6 is the magnification claim, which reads the frame size from the
cache entry rather than assuming 4000x3000. Control 7 is the mission, day and
site sharing, which is what decides whether the decomposition's middle step is
about the camera at all.
"""

from __future__ import annotations

import json


def test_frame_fraction_is_linear_not_area(crown_accuracy):
    """A box of a quarter of the frame's area is half of it linearly."""
    box = {"x_min": 0, "y_min": 0, "x_max": 2000, "y_max": 1500}
    assert crown_accuracy.frame_fraction(box, 4000, 3000) == 0.5


def test_frame_fraction_reads_the_frame_it_is_given(crown_accuracy):
    """The same box against a smaller frame is a larger fraction."""
    box = {"x_min": 0, "y_min": 0, "x_max": 1000, "y_max": 750}
    assert crown_accuracy.frame_fraction(box, 4000, 3000) == 0.25
    assert crown_accuracy.frame_fraction(box, 2000, 1500) == 0.5


def test_frame_fraction_survives_a_frame_it_cannot_use(crown_accuracy):
    box = {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100}
    assert crown_accuracy.frame_fraction(box, None, 3000) == 0.0
    assert crown_accuracy.frame_fraction(box, 0, 3000) == 0.0
    assert crown_accuracy.frame_fraction({}, 4000, 3000) == 0.0


def test_load_missions_keys_on_the_basename(crown_accuracy, tmp_path):
    """The three global-key namespaces share only the file name."""
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in [
        {"global_key": "migrated/A_zoom.JPG",
         "metadata": {"mission": "20250101_site_wpt_m3e"}},
        {"global_key": "flight_folder/B_tele.JPG",
         "metadata": {"mission": "20260402_site_wpt_m3t"}},
        {"global_key": "C_tele.JPG", "metadata": {"mission": None}},
    ]) + "\n", encoding="utf-8")
    missions = crown_accuracy.load_missions(path)
    assert missions == {"A_zoom.JPG": "20250101_site_wpt_m3e",
                        "B_tele.JPG": "20260402_site_wpt_m3t"}


def test_load_missions_absent_file_is_empty_not_an_error(crown_accuracy, tmp_path):
    assert crown_accuracy.load_missions(tmp_path / "nope.jsonl") == {}


def _rows(*frames):
    """One crown per frame, carrying only the two keys `campaigns` reads."""
    return [{"camera": "tele" if "tele" in f else "zoom", "frame": f}
            for f in frames]


def test_campaigns_reports_no_shared_mission(crown_accuracy, capsys):
    """The state on disk: the two cameras are two disjoint campaigns."""
    rows = _rows("A_zoom.JPG", "B_tele.JPG")
    missions = {"A_zoom.JPG": "20250101_northsite_wpt_m3e",
                "B_tele.JPG": "20260402_southsite_wpt_m3t"}
    crown_accuracy.campaigns(rows, ["tele", "zoom"], missions)
    out = capsys.readouterr().out
    assert "missions carrying both cameras:" in out
    assert "0 of 2" in out
    assert "share no mission" in out


def test_campaigns_reports_a_shared_mission_when_there_is_one(crown_accuracy, capsys):
    """The claim the spec made. It must be detectable, not assumed absent."""
    rows = _rows("A_zoom.JPG", "B_tele.JPG")
    missions = {"A_zoom.JPG": "20260402_onesite_wpt_m3e",
                "B_tele.JPG": "20260402_onesite_wpt_m3e"}
    crown_accuracy.campaigns(rows, ["tele", "zoom"], missions)
    out = capsys.readouterr().out
    assert "1 of 1" in out
    assert "share no mission" not in out


def test_campaigns_survives_a_camera_with_no_mission(crown_accuracy, capsys):
    rows = _rows("A_zoom.JPG", "B_tele.JPG")
    crown_accuracy.campaigns(rows, ["tele", "zoom"],
                             {"A_zoom.JPG": "20250101_site_wpt_m3e"})
    out = capsys.readouterr().out
    assert "no mission recorded" in out
    assert "carrying both cameras" not in out
