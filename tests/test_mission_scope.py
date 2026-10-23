"""The scope table: frames and labels per mission and site, and its check.

    .venv/bin/pytest tests/test_mission_scope.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def mods():
    with _on_path(REPO / "dashboard"):
        import history
        import mission_scope
        yield SimpleNamespace(history=history, scope=mission_scope)


ORIGINS = {"comb_a.JPG": ("20240911_sitea_w_m3e", "sitea"),
           "comb_b.JPG": ("20240911_sitea_w_m3e", "sitea"),
           "comb_c.JPG": ("20250101_siteb_w_m3e", "siteb")}


def health(*stems, labelled=()):
    return SimpleNamespace(predictions=dict.fromkeys(stems, []), labelled_stems=set(labelled))


def test_rows_count_every_frame_and_keep_unplaced_ones_blank(mods):
    h = health("a.JPG", "b.JPG", "c.JPG", "lost.JPG", labelled=("a.JPG", "lost.JPG"))
    assert mods.scope.rows(h, ORIGINS) == [
        {"mission": "", "site": "", "n_frames": 1, "n_labelled": 1},
        {"mission": "20240911_sitea_w_m3e", "site": "sitea", "n_frames": 2, "n_labelled": 1},
        {"mission": "20250101_siteb_w_m3e", "site": "siteb", "n_frames": 1, "n_labelled": 0}]
    assert mods.scope.rows(health(), ORIGINS) == []


def test_the_check_passes_skips_and_aborts(mods, tmp_path):
    table = mods.scope.rows(health("a.JPG", "c.JPG", labelled=("c.JPG",)), ORIGINS)
    assert "check skipped" in mods.history.check_scope(str(tmp_path), table)
    mods.scope.write(str(tmp_path), table)
    assert mods.history.check_scope(str(tmp_path), table) == "scope.csv: 2 mission and site rows match"
    with pytest.raises(SystemExit, match="VERIFY FAIL: scope.csv"):
        mods.history.check_scope(str(tmp_path), table[:1])
    with pytest.raises(SystemExit, match="VERIFY FAIL: scope.csv"):
        mods.history.check_scope(str(tmp_path), [{**table[0], "n_labelled": 9}, table[1]])
