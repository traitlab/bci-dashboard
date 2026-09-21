"""`dashboard/gbif_keys.py`'s own contract: what a label resolves to, and what
it refuses to resolve. `test_checklist.py` covers the membership test built on
top of this; this file covers the lookup."""

import json

import pytest


def _index(mod, **over):
    doc = {"ontology_name": "t", "fetched": "", "by_code": {"POCHQU": 9158473},
           "by_name": {"pochota fendleri": 9158473}, "by_legacy": {"pochota quinata": 9158473},
           "accepted": {"9158473": 9158473}}
    doc.update(over)
    return mod.KeyIndex(
        ontology_name=doc["ontology_name"], fetched=doc["fetched"],
        by_code=doc["by_code"], by_name=doc["by_name"],
        by_legacy=doc["by_legacy"], accepted=doc["accepted"])


@pytest.mark.parametrize("label, name, codes", [
    ("Abuta panamensis-ABUTPA-ABUP", "Abuta panamensis", ["ABUTPA", "ABUP"]),
    ("Virola surinamensis", "Virola surinamensis", []),
    # A hyphenated epithet is not a collection code, and popping it would turn
    # one species into another that exists.
    ("Macfadyena unguis-cati", "Macfadyena unguis-cati", []),
])
def test_only_trailing_code_tokens_are_split_off(dashboard_gbif_keys, label, name, codes):
    assert dashboard_gbif_keys.split_codes(label) == (name, codes)


def test_the_code_answers_before_the_name(dashboard_gbif_keys):
    """The code is the stable half of a label. When both are present and they
    disagree, the label was renamed and the code is the one that survived it."""
    idx = _index(dashboard_gbif_keys, by_name={"pochota quinata": 111},
                 accepted={"9158473": 9158473, "111": 111})
    assert idx.key_for("Pochota quinata-POCHQU") == 9158473


def test_a_retired_name_resolves_to_the_option_that_replaced_it(dashboard_gbif_keys):
    """The ground truth stores labels with their codes stripped, so a renamed
    option arrives as a bare old name. Without `by_legacy` it has nothing to
    join on and reads as absent from a list that carries it."""
    assert _index(dashboard_gbif_keys).key_for("Pochota quinata") == 9158473


def test_a_live_name_is_never_shadowed_by_a_retired_reading_of_it(dashboard_gbif_keys):
    idx = _index(dashboard_gbif_keys, by_legacy={"pochota fendleri": 111})
    assert idx.key_for("Pochota fendleri") == 9158473


def test_a_synonym_key_resolves_to_the_accepted_one(dashboard_gbif_keys):
    """GBIF holds one taxon under both, and the label and the checklist do not
    always pick the same one. Comparing them raw reads four species absent."""
    idx = _index(dashboard_gbif_keys, by_name={"virola nobilis": 3742998},
                 accepted={"3742998": 3152848})
    assert idx.key_for("Virola nobilis") == 3152848
    assert idx.accepted_key(3742998) == 3152848


def test_an_unknown_label_is_none_not_a_guess(dashboard_gbif_keys):
    idx = _index(dashboard_gbif_keys)
    assert idx.key_for("Ficus insipida") is None
    assert idx.key_for("") is None


def test_an_unresolved_key_stands_for_itself(dashboard_gbif_keys):
    assert _index(dashboard_gbif_keys).accepted_key(4073669) == 4073669


def test_a_missing_file_returns_none_not_an_error(dashboard_gbif_keys, tmp_path):
    """No network call, no credential: the normal state of a fresh clone, and
    every caller degrades to the name join rather than aborting a page build."""
    assert dashboard_gbif_keys.load_keys(str(tmp_path / "absent.json")) is None


def test_an_older_file_without_the_retired_names_still_loads(dashboard_gbif_keys, tmp_path):
    p = tmp_path / "gbif_keys.json"
    p.write_text(json.dumps({"by_code": {"POCHQU": 9158473}, "by_name": {},
                             "accepted": {}}), encoding="utf-8")
    idx = dashboard_gbif_keys.load_keys(str(p))
    assert idx.by_legacy == {}
    assert idx.key_for("Pochota quinata-POCHQU") == 9158473
