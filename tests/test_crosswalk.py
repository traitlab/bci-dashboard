"""The WCVP crosswalk, which is the only reason match tier (d) exists.

`load_wcvp_crosswalk` turns a cache of 249 WCVP lookups into one mapping:
the botanist's label, normalized, to the accepted binomial, normalized. A
label that reaches a cached prediction only through this mapping is scored
correct; without it the same frame is a miss. `measure.py` prints the
sensitivity of the headline to exactly that, so what this function keeps and
what it drops moves a published number.

    .venv/bin/pytest tests/test_crosswalk.py
"""

from __future__ import annotations

import json

import pytest

# The shape of one cache record, from data/wcvp_cache.json. Only
# `accepted_name` is read; the rest is provenance the run log counts.
SYNONYM = {"gbif_key": 207124029,
           "accepted_name": "Jupunba macradenia (Pittier) M.V.B.Soares",
           "family": "Fabaceae", "rank": "SPECIES", "taxonomic_status": "SYNONYM"}


def _cache(tmp_path, records, name="wcvp_cache.json"):
    p = tmp_path / name
    p.write_text(json.dumps(records) if isinstance(records, dict) else records,
                 encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# No file: tier (d) is off, and every other tier still works
# ---------------------------------------------------------------------------

def test_no_path_at_all_disables_the_tier_rather_than_failing(core):
    # core.WCVP_CACHE_JSON is set to None on a checkout without the file, so
    # this is the ordinary first-run case, not an error path.
    assert core.load_wcvp_crosswalk(None) == ({}, {})


def test_a_path_that_does_not_exist_disables_the_tier(core, tmp_path):
    assert core.load_wcvp_crosswalk(str(tmp_path / "absent.json")) == ({}, {})


def test_an_empty_cache_is_an_empty_mapping(core, tmp_path):
    assert core.load_wcvp_crosswalk(_cache(tmp_path, {})) == ({}, {})


# ---------------------------------------------------------------------------
# What becomes a mapping
# ---------------------------------------------------------------------------

def test_a_synonym_maps_the_label_to_the_accepted_binomial(core, tmp_path):
    mapping, raw = core.load_wcvp_crosswalk(
        _cache(tmp_path, {"Abarema macradenia": SYNONYM}))
    assert mapping == {"abarema macradenia": "jupunba macradenia"}
    assert raw == {"Abarema macradenia": SYNONYM}


def test_the_authority_is_dropped_from_the_accepted_name(core, tmp_path):
    # WCVP returns "Genus species (Author) Author", and nothing Pl@ntNet
    # returns carries an authority, so the mapping would never match.
    mapping, _ = core.load_wcvp_crosswalk(_cache(tmp_path, {
        "Abarema macradenia": {"accepted_name": "Jupunba macradenia (Pittier) M.V.B.Soares"}}))
    assert mapping == {"abarema macradenia": "jupunba macradenia"}


def test_both_sides_go_through_the_same_normalization_as_a_label(core, tmp_path):
    # The label side arrives from the labels CSV with the collection codes the
    # box exports carry, so it has to be normalized the way every other name
    # in the join is, or the lookup misses.
    key = "Bombacopsis quinata-BOMBQU-BOMQ"
    mapping, _ = core.load_wcvp_crosswalk(_cache(tmp_path, {
        key: {"accepted_name": "Pachira quinata (Jacq.) W.S.Alverson"}}))
    assert mapping == {core.normalize(key): "pachira quinata"}


def test_the_raw_records_come_back_whole_including_the_dropped_ones(core, tmp_path):
    # The run log prints "N name changes from M WCVP cache records", so the
    # denominator has to be every record, not the ones that produced a change.
    records = {"Abarema macradenia": SYNONYM,
               "Ficus insipida": {"accepted_name": "Ficus insipida Willd."}}
    mapping, raw = core.load_wcvp_crosswalk(_cache(tmp_path, records))
    assert len(mapping) == 1 and len(raw) == 2


# ---------------------------------------------------------------------------
# What is dropped, and why each one has to be
# ---------------------------------------------------------------------------

def test_an_accepted_name_equal_to_the_label_is_not_a_mapping(core, tmp_path):
    # Most of the 249 records are a name WCVP already accepts. Keeping these
    # would put every label in tier (d), which is the tier that says a synonym
    # was applied, and the sensitivity line in the run log would read as though
    # the crosswalk carried the whole headline.
    mapping, _ = core.load_wcvp_crosswalk(_cache(tmp_path, {
        "Ficus insipida": {"accepted_name": "Ficus insipida Willd."}}))
    assert mapping == {}


def test_a_record_with_no_accepted_name_is_dropped(core, tmp_path):
    for value in ({}, {"accepted_name": None}, {"accepted_name": ""}):
        mapping, _ = core.load_wcvp_crosswalk(_cache(tmp_path, {"Alseis blackiana": value}))
        assert mapping == {}, value


def test_an_accepted_name_that_is_not_a_plain_binomial_is_dropped(core, tmp_path):
    # A genus-only or infraspecific accepted name cannot be matched against a
    # Pl@ntNet binomial, and half-matching it would score a genus as a species.
    for acc in ("Jupunba", "JUPUNBA MACRADENIA", "Jupunba Macradenia"):
        mapping, _ = core.load_wcvp_crosswalk(_cache(tmp_path, {"Abarema macradenia": {
            "accepted_name": acc}}))
        assert mapping == {}, acc


def test_a_label_that_normalizes_to_nothing_is_dropped(core, tmp_path):
    mapping, _ = core.load_wcvp_crosswalk(_cache(tmp_path, {
        "": {"accepted_name": "Pachira quinata (Jacq.) W.S.Alverson"}}))
    assert mapping == {}


def test_a_damaged_cache_stops_the_run_instead_of_silently_dropping_tier_d(core, tmp_path):
    # The opposite of the missing-file case above, and deliberately so: an
    # absent file is a checkout without the optional input, while a file that
    # will not parse is a broken input. Swallowing it would quietly move the
    # published headline by the size of tier (d).
    with pytest.raises(json.JSONDecodeError):
        core.load_wcvp_crosswalk(_cache(tmp_path, '{"Abarema macradenia": {'))


# ---------------------------------------------------------------------------
# add_input_flags: the four input paths, worded once for four commands
# ---------------------------------------------------------------------------

def test_every_command_offers_the_same_four_input_flags(core):
    import argparse

    p = argparse.ArgumentParser()
    core.add_input_flags(p)
    args = p.parse_args([])
    assert (args.gt, args.splits, args.cache_dir, args.wcvp_cache) == (
        core.GT_CSV, core.SPLITS_CSV, core.CACHE_DIR, core.WCVP_CACHE_JSON)


def test_a_command_can_ask_for_only_the_flags_it_reads(core):
    import argparse

    p = argparse.ArgumentParser()
    core.add_input_flags(p, "--gt")
    assert p.parse_args([]).gt == core.GT_CSV
    assert not hasattr(p.parse_args([]), "splits")


def test_the_help_names_the_default_relative_to_the_repo(core):
    # An absolute path in --help is a different string on every machine, and
    # the four defaults are all inside the checkout.
    import argparse
    import os
    import re

    p = argparse.ArgumentParser()
    core.add_input_flags(p, "--gt")
    # argparse wraps, so a path can arrive split across two lines.
    help_text = re.sub(r"\s+", " ", p.format_help())
    assert "botanist labels" in help_text
    assert f"(default: {os.path.relpath(core.GT_CSV, core.REPO)})" in help_text


def test_a_command_can_reword_one_flag_without_restating_the_others(core):
    import argparse

    p = argparse.ArgumentParser()
    core.add_input_flags(p, "--gt", "--cache-dir", cache_dir="the answers to score")
    help_text = p.format_help()
    assert "the answers to score" in help_text
    assert "botanist labels" in help_text
