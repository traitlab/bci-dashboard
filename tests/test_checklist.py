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


# The 18 species measured absent from bcnm, 178 scored frames between them.
# Every one of them is a late-alphabet tree: the list carries Trichomanes,
# Trimezia and Tripogandra, which sort among them, so it is not a truncation.
# Reproduced against the checklist directly, not re-derived, so a future edit
# that moves the count has to explain why.
KNOWN_OUT_OF_SCOPE = {
    "tontelea passiflora", "trattinnickia aspera", "trema domingense",
    "trema micranthum", "trichilia tuberculata", "trichospermum mexicanum",
    "tynanthus croatianus", "uncaria tomentosa", "vatairea erythrocarpa",
    "virola fosteri", "virola nobilis", "virola sebifera",
    "virola surinamensis", "vismia macrophylla", "vitis tiliifolia",
    "vochysia ferruginea", "zanthoxylum ekmanii", "zanthoxylum panamense"}

# Three labels the botanists renamed in Labelbox. Each one is on bcnm under the
# new name and read as absent under the old one until the GBIF key was joined,
# which is the entire case for joining on it.
RENAMED_BUT_ON_THE_LIST = {
    "Quararibea asterolepis": "Quararibea stenophylla",
    "Pochota quinata": "Pochota fendleri",
    "Platymiscium pinnatum": "Platymiscium dimorphandrum"}


def test_the_measured_absent_species_are_absent_by_name_and_by_key(
        dashboard_checklist, dashboard_gbif_keys, core):
    """Both halves of the membership test agree these are genuinely not on it.

    A name join alone cannot tell "absent" from "spelled differently", which is
    the objection this whole join answers, so the assertion is made on the keys
    as well and the two have to say the same thing.
    """
    p = dashboard_checklist.checklist_path("bcnm")
    if not Path(p).exists():
        pytest.skip(f"{p} not present (fresh clone, data/ is gitignored)")
    keys = dashboard_gbif_keys.load_keys()
    if keys is None:
        pytest.skip("data/gbif_keys.json not present (run labelling/build_gbif_keys.py)")
    ck = dashboard_checklist.load_checklist(path=p)
    crosswalk, _ = core.load_wcvp_crosswalk(str(REPO / "data" / "wcvp_cache.json"))
    on_list = ck.canon_binomials(core.canonicaliser(crosswalk))
    on_list_keys = ck.accepted_keys(keys)
    for sp in KNOWN_OUT_OF_SCOPE:
        assert sp not in on_list, f"{sp} was measured absent from bcnm"
        assert keys.key_for(sp) not in on_list_keys, (
            f"{sp} is absent from bcnm by name but its GBIF key is on the list")


def test_a_renamed_option_is_found_by_its_key_not_its_name(
        dashboard_checklist, dashboard_gbif_keys, core):
    p = dashboard_checklist.checklist_path("bcnm")
    if not Path(p).exists():
        pytest.skip(f"{p} not present (fresh clone, data/ is gitignored)")
    keys = dashboard_gbif_keys.load_keys()
    if keys is None:
        pytest.skip("data/gbif_keys.json not present (run labelling/build_gbif_keys.py)")
    ck = dashboard_checklist.load_checklist(path=p)
    crosswalk, _ = core.load_wcvp_crosswalk(str(REPO / "data" / "wcvp_cache.json"))
    canon = core.canonicaliser(crosswalk)
    is_member = dashboard_checklist.membership(ck, canon, keys)
    for old, new in RENAMED_BUT_ON_THE_LIST.items():
        assert keys.key_for(old) == keys.key_for(new), (
            f"{old} and {new} are one Labelbox option and must share a key")
        assert is_member(canon(old), [old]), (
            f"{old} is on bcnm as {new} and the key join has to find it")


def test_species_the_corpus_never_returned_are_not_all_out_of_scope(
        health, dashboard_checklist, dashboard_gbif_keys, core):
    """Before this checklist was wired in, every species with
    `in_corpus_vocabulary=False` showed as `unreachable`. Half of them are on
    bcnm and belong in `unreachable` still, not `out_of_scope`: proving 18
    absent does not prove the rest are.

    Tested against bcnm by name, not against whichever project is live: the
    live checklist can flip (it did, back to k-central-america) without this
    regression losing its fixture.
    """
    import core as hc
    from pathlib import Path
    if not Path(hc.GT_CSV).exists() or not Path(hc.CACHE_DIR).exists():
        pytest.skip("GT labels or cached predictions not present (fresh clone)")
    p = dashboard_checklist.checklist_path("bcnm")
    if not Path(p).exists():
        pytest.skip(f"{p} not present (fresh clone, data/ is gitignored)")
    keys = dashboard_gbif_keys.load_keys()
    ck = dashboard_checklist.load_checklist(path=p)
    crosswalk, _ = core.load_wcvp_crosswalk(str(REPO / "data" / "wcvp_cache.json"))
    canon = core.canonicaliser(crosswalk)
    is_member = dashboard_checklist.membership(ck, canon, keys)
    bcnm_cache = str(REPO / "data" / "predictions_bcnm" / "cache")
    if not Path(bcnm_cache).exists():
        pytest.skip(f"{bcnm_cache} not present (fresh clone, data/ is gitignored)")
    h = health.load_health(cache_dir=bcnm_cache)
    never_ranked = [d for d in h.per_species if not d["in_corpus_vocabulary"]]
    membership_of = {d["species"]: is_member(d["species"], d["gt_raw_labels"].split("|"))
                      for d in never_ranked}
    out_of_scope = [d for d in never_ranked if membership_of[d["species"]] is False]
    still_unreachable = [d for d in never_ranked if membership_of[d["species"]] is True]
    assert {d["species"] for d in out_of_scope} == KNOWN_OUT_OF_SCOPE
    assert sum(d["n_labelled_frames"] for d in out_of_scope) == 178
    assert still_unreachable, (
        "expected at least one species that never ranked in a sample but IS "
        "on the project's checklist; the fixture data or the checklist changed")
    assert "quararibea asterolepis" not in {d["species"] for d in out_of_scope}, (
        "a renamed Labelbox option is on the list under its new name; reading "
        "it as out of scope is the name join failing, not a measurement")


def test_membership_falls_back_to_the_name_when_no_keys_are_on_disk(
        dashboard_checklist, dashboard_gbif_keys, core, tmp_path):
    """A weaker test, not a wrong one: `data/gbif_keys.json` is built by a
    network-touching step and a fresh clone has none."""
    p = tmp_path / "checklist_t.json"
    p.write_text(json.dumps({
        "project": "t", "declared_species_count": 1, "n_returned": 1,
        "species": [{"scientificNameWithoutAuthor": "Ceiba pentandra",
                     "gbifId": 3152707}]}), encoding="utf-8")
    ck = dashboard_checklist.load_checklist(path=str(p))
    keys = dashboard_gbif_keys.KeyIndex("", "", {}, {}, {}, {})
    is_member = dashboard_checklist.membership(ck, core.normalize, keys)
    assert is_member("ceiba pentandra", ["Ceiba pentandra"])
    assert not is_member("hura crepitans", ["Hura crepitans"])


def test_membership_is_none_without_a_checklist(dashboard_checklist, core):
    """Nothing on disk can prove a species absent, so the page says unknown
    rather than guessing."""
    assert dashboard_checklist.membership(None, core.normalize) is None


def test_a_checklist_without_gbif_ids_does_not_read_as_an_empty_list(
        dashboard_checklist, dashboard_gbif_keys, core, tmp_path):
    """Every key test would fail against an empty key set, turning a checklist
    the names match into a wall of false absences."""
    p = tmp_path / "checklist_t.json"
    p.write_text(json.dumps({
        "project": "t", "declared_species_count": 1, "n_returned": 1,
        "species": [{"scientificNameWithoutAuthor": "Ceiba pentandra"}]}), encoding="utf-8")
    ck = dashboard_checklist.load_checklist(path=str(p))
    assert ck.accepted_keys(dashboard_gbif_keys.KeyIndex("", "", {}, {}, {}, {})) == frozenset()
    is_member = dashboard_checklist.membership(ck, core.normalize)
    assert is_member("ceiba pentandra", ["Ceiba pentandra"])
