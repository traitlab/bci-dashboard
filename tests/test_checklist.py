"""`dashboard/checklist.py`'s own contract: absent, short, and how membership
is tested. `test_core.py` covers what `diagnose` does with what this reads
back; this file covers the reading."""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_a_missing_checklist_returns_none_not_an_error(dashboard_checklist, tmp_path):
    """No network call, no credential, and the normal state of a fresh clone:
    a caller has to degrade to today's behaviour, not abort a page build."""
    assert dashboard_checklist.load_checklist(
        path=str(tmp_path / "absent.json")) is None


def test_a_short_download_is_refused_loudly(dashboard_checklist, tmp_path):
    """`n_returned` short of `declared_species_count` is a partial download,
    not a real checklist, and a species missing from it proves nothing."""
    p = tmp_path / "checklist_short.json"
    p.write_text(json.dumps({
        "project": "k-central-america", "lang": "en",
        "declared_species_count": 15921, "n_returned": 2,
        "species": [{"scientificNameWithoutAuthor": "Ceiba pentandra"},
                    {"scientificNameWithoutAuthor": "Hura crepitans"}],
    }), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        dashboard_checklist.load_checklist(path=str(p))
    msg = str(e.value)
    assert "15921" in msg and "2" in msg


def test_a_complete_checklist_loads(dashboard_checklist, tmp_path):
    p = tmp_path / "checklist_ok.json"
    p.write_text(json.dumps({
        "project": "k-central-america", "lang": "en",
        "declared_species_count": 2, "n_returned": 2,
        "species": [{"scientificNameWithoutAuthor": "Ceiba pentandra"},
                    {"scientificNameWithoutAuthor": "Hura crepitans"}],
    }), encoding="utf-8")
    ck = dashboard_checklist.load_checklist(path=str(p))
    assert ck is not None
    assert ck.n_returned == 2
    assert "ceiba pentandra" in ck.binomials_norm


def test_membership_needs_the_crosswalk_not_normalize_alone(dashboard_checklist, core):
    """A name absent from the checklist under its own spelling can still be on
    it under a WCVP synonym. `canon_binomials` has to apply the same crosswalk
    every label and cached prediction goes through, not a second, looser
    match on the raw normalized text."""
    p = REPO / "data" / "checklist_k-central-america.json"
    wcvp = REPO / "data" / "wcvp_cache.json"
    if not p.exists() or not wcvp.exists():
        pytest.skip(f"{p} or {wcvp} not present (fresh clone, data/ is gitignored)")
    ck = dashboard_checklist.load_checklist(path=str(p))
    crosswalk, _ = core.load_wcvp_crosswalk(str(wcvp))
    canon = core.canonicaliser(crosswalk)

    assert "heteropterys intermedia" not in ck.binomials_norm, (
        "this case is only informative if the accepted name is absent under "
        "its own spelling")
    assert "heteropterys intermedia" in ck.canon_binomials(canon), (
        "heteropterys laurifolia, the synonym k-central-america carries, "
        "should resolve to heteropterys intermedia through the crosswalk")


# The 3 species measured absent from k-central-america (51 frames between
# them, the largest at 47). Reproduced against the checklist directly, not
# re-derived, so a future edit that moves the count has to explain why.
KNOWN_OUT_OF_SCOPE = {"virola surinamensis", "dendropanax arboreus", "ficus matiziana"}


def test_the_three_measured_absent_species_land_in_out_of_scope(dashboard_checklist, core):
    p = REPO / "data" / "checklist_k-central-america.json"
    if not p.exists():
        pytest.skip(f"{p} not present (fresh clone, data/ is gitignored)")
    ck = dashboard_checklist.load_checklist(path=str(p))
    crosswalk, _ = core.load_wcvp_crosswalk(str(REPO / "data" / "wcvp_cache.json"))
    canon = core.canonicaliser(crosswalk)
    members = ck.canon_binomials(canon)
    for sp in KNOWN_OUT_OF_SCOPE:
        assert sp not in members, f"{sp} was measured absent from k-central-america"


def test_species_the_corpus_never_returned_are_not_all_out_of_scope(health):
    """Before this checklist was wired in, every species with
    `in_corpus_vocabulary=False` showed as `unreachable`. Against
    k-central-america most of them are on the list and belong in
    `unreachable` still, not `out_of_scope`: proving 3 absent does not prove
    the rest are."""
    import checklist as ck_mod
    import core as hc
    from pathlib import Path
    if not Path(hc.GT_CSV).exists() or not Path(hc.CACHE_DIR).exists():
        pytest.skip("GT labels or cached predictions not present (fresh clone)")
    h = health.load_health()
    if h.checklist is None:
        pytest.skip(f"{ck_mod.checklist_path()} not present (fresh clone, data/ is gitignored)")
    never_ranked = [d for d in h.per_species if not d["in_corpus_vocabulary"]]
    out_of_scope = [d for d in never_ranked if d["in_project_checklist"] is False]
    still_unreachable = [d for d in never_ranked if d["in_project_checklist"] is True]
    assert {d["species"] for d in out_of_scope} == KNOWN_OUT_OF_SCOPE
    assert sum(d["n_labelled_frames"] for d in out_of_scope) == 51
    assert still_unreachable, (
        "expected at least one species that never ranked in a sample but IS "
        "on the project's checklist; the fixture data or the checklist changed")
    assert "virola nobilis" in {d["species"] for d in still_unreachable}
