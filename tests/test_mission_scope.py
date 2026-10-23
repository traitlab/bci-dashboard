"""The scope table: frames, labels and accuracy per mission and site, its
check, and the model-health panel that lays it out.

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


def health(*stems, labelled=(), scored=()):
    """``scored`` is (stem, label, top prediction) per frame labelled to a species."""
    return SimpleNamespace(
        predictions=dict.fromkeys(stems, []), labelled_stems=set(labelled),
        sp_recs=[{"global_key": "comb_" + s, "gt": gt, "ranked": [(guess, 0.9)]}
                 for s, gt, guess in scored])


def row(mission, site, *n):
    return dict(zip(("mission", "site", "n_frames", "n_labelled", "n_scored",
                     "n_correct_top1"), (mission, site, *n)))


MISSION_A, MISSION_B = ORIGINS["comb_a.JPG"][0], ORIGINS["comb_c.JPG"][0]


def test_rows_count_every_frame_and_keep_unplaced_ones_blank(mods):
    h = health("a.JPG", "b.JPG", "c.JPG", "lost.JPG", labelled=("a.JPG", "b.JPG", "lost.JPG"),
               scored=[("a.JPG", "x", "x"), ("b.JPG", "x", "y"), ("lost.JPG", "y", "y")])
    assert mods.scope.rows(h, ORIGINS) == [
        row("", "", 1, 1, 1, 1), row(MISSION_A, "sitea", 2, 2, 2, 1),
        row(MISSION_B, "siteb", 1, 0, 0, 0)]
    assert mods.scope.rows(health(), ORIGINS) == []


def test_the_sites_panel_gives_each_rate_its_count(mods):
    with _on_path(REPO / "dashboard"):
        import page
    assert page.PANELS["sites"] == ("model-health", mods.scope.p_sites)
    assert "sites" in page.EXTERNAL_PANELS
    scope = [row(MISSION_A, "sitea", 2, 2, 2, 1), row(MISSION_B, "siteb", 1, 1, 0, 0),
             row("20250102_sitea_e_m3e", "sitea", 3, 2, 2, 2), row("", "", 1, 1, 1, 1)]
    html = mods.scope.p_sites(SimpleNamespace(scope=scope))
    site_table, mission_table = html.split('<details class="more"')
    # sitea pools two missions: 3 of 4 scored frames right.
    assert "75.0% of 4" in site_table and "not scored" in site_table
    assert "not placed" in site_table and "100.0% of 1" in site_table
    assert "The same per mission (4 missions)" in mission_table
    assert "50.0% of 2" in mission_table and "100.0% of 2" in mission_table
    assert html.count('href="scope.csv"') == 2
    assert "No close-up" in mods.scope.p_sites(SimpleNamespace(scope=[]))


def test_the_check_passes_skips_and_aborts(mods, tmp_path):
    table = mods.scope.rows(health("a.JPG", "c.JPG", labelled=("c.JPG",)), ORIGINS)
    assert "check skipped" in mods.history.check_scope(str(tmp_path), table)
    mods.scope.write(str(tmp_path), table)
    assert mods.history.check_scope(str(tmp_path), table) == "scope.csv: 2 mission and site rows match"
    with pytest.raises(SystemExit, match="VERIFY FAIL: scope.csv"):
        mods.history.check_scope(str(tmp_path), table[:1])
    with pytest.raises(SystemExit, match="VERIFY FAIL: scope.csv"):
        mods.history.check_scope(str(tmp_path), [{**table[0], "n_labelled": 9}, table[1]])
