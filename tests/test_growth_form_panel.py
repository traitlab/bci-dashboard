"""Growth form: the coverage guard, the per-form accuracy rows and the panel."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def gf():
    with _on_path(REPO / "dashboard"):
        import growth_form
        import page
        yield SimpleNamespace(mod=growth_form, page=page)


def rec(gt, guess):
    return {"gt": gt, "ranked": [(guess, 0.9)]}


RECS = [rec("a", "a"), rec("a", "b"), rec("b", "b"), rec("c", "a"), rec("z", "z")]
FORMS = {"a": "tree", "b": "tree", "c": "liana"}  # z is not in the file


def test_rows_count_frames_hits_and_species_per_form(gf):
    assert gf.mod.rows(RECS, FORMS) == [
        {"growth_form": "tree", "n_scored": 3, "n_correct_top1": 2, "n_species": 2},
        {"growth_form": "liana", "n_scored": 1, "n_correct_top1": 0, "n_species": 1},
        {"growth_form": "unknown", "n_scored": 1, "n_correct_top1": 1, "n_species": 1}]
    assert gf.mod.rows([], FORMS) == []


def test_panel_gives_each_rate_its_count(gf):
    assert gf.page.PANELS["growth"] == ("model-health", gf.mod.p_growth_form)
    assert "growth" in gf.page.EXTERNAL_PANELS
    html = gf.mod.p_growth_form(SimpleNamespace(growth_forms=gf.mod.rows(RECS, FORMS)))
    assert "66.7% of 3" in html and "0.0% of 1" in html and "100.0% of 1" in html
    assert "No frame" in gf.mod.p_growth_form(SimpleNamespace(growth_forms=[]))


def test_attach_adds_the_column_and_unknown_rows_count_as_covered(gf):
    rows = [{"species": "a"}, {"species": "q"}]
    gf.mod.attach(rows, {"a": "tree", "q": "unknown"})
    assert [r["growth_form"] for r in rows] == ["tree", "unknown"]


def test_attach_shows_a_species_the_file_lacks_as_unknown_and_names_it(gf, capsys):
    rows = [{"species": "a"}, {"species": "m"}, {"species": "n"}]
    assert gf.mod.attach(rows, {"a": "tree"}) == ["m", "n"]
    assert [r["growth_form"] for r in rows] == ["tree", "unknown", "unknown"]
    assert "2 species, shown as unknown: m, n." in capsys.readouterr().err


def test_species_table_filters_on_growth_form(gf):
    import assets
    out = assets.filterable_table([("Species", False)], [["a"], ["b"]], options=[],
                                  row_attrs=[' data-form="tree"', ' data-form="liana"'],
                                  forms=["liana", "tree"])
    assert 'id="form-filter"' in out and '<option value="liana">liana</option>' in out
    assert 'data-form="tree"' in out
    assert 'id="form-filter"' not in assets.filterable_table([("Species", False)], [["a"]], options=[])
