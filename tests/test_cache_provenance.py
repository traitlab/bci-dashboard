"""Which Pl@ntNet project a cached answer came from, and why it must say so.

A project is a filter on one classifier, so the same photo gets different names
from different projects. Every per-species number pools the whole cache
directory, so after a flora switch an answer fetched through the old project and
one fetched through the new one are two populations in one average. Nothing on
disk separated them: a cached answer recorded its results and no provenance.

So the fetch now stamps the project, the backfill stamps the answers written
before it did, and the run log counts them apart. These tests hold the three to
the same name for the project and keep "recorded" from being confused with
"assumed", which is the difference between measuring the provenance and
inferring it.

    .venv/bin/pytest tests/test_cache_provenance.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def stamper():
    """predict/stamp_cache_project.py, loaded by path like the other scripts."""
    path = REPO / "predict" / "stamp_cache_project.py"
    spec = importlib.util.spec_from_file_location("_stamp_cache_project", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stamp_cache_project"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# The slug: three files derive it and must agree
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,slug", [
    ("https://my-api.plantnet.org/v2/identify/k-central-america", "k-central-america"),
    ("https://my-api.plantnet.org/v2/identify/bcnm", "bcnm"),
    ("https://my-api.plantnet.org/v2/identify/bcnm/", "bcnm"),
])
def test_the_page_and_the_fetch_name_the_project_the_same_way(core, photo, url, slug):
    # Two derivations of one setting, in files that cannot import each other.
    # If they disagree, a stamped answer and the page reporting on it name
    # different projects and the mismatch check compares the wrong strings.
    assert core.project_of(url) == slug
    assert photo.api_and_project({"plantnet": {"identify_url": url}})[1] == slug


def test_the_project_the_pages_report_is_the_one_config_names(core):
    assert core.EVAL_PROJECT == core.project_of(core.IDENTIFY_URL)


# ---------------------------------------------------------------------------
# Reading provenance off an answer
# ---------------------------------------------------------------------------

def test_an_answer_that_names_no_project_reads_as_unknown_not_as_the_current_one(core):
    # "" and EVAL_PROJECT are different claims. Defaulting to the configured
    # project here would make every unstamped answer look verified.
    assert core.entry_project({"results": {"species": []}}) == ""
    assert core.entry_project_source({"results": {"species": []}}) == ""


def test_an_answer_names_the_project_it_records(core):
    entry = {"project": "bcnm", "project_source": "recorded"}
    assert core.entry_project(entry) == "bcnm"
    assert core.entry_project_source(entry) == "recorded"


@pytest.mark.parametrize("junk", [None, [], "bcnm", 7])
def test_a_payload_that_is_not_an_object_reads_as_unknown(core, junk):
    assert core.entry_project(junk) == ""
    assert core.entry_project_source(junk) == ""


def test_a_salvaged_payload_gets_no_provenance(core, tmp_path):
    # A truncated file's ranked names survive bracket-matching. Its provenance
    # does not, and inventing one would put weight on a broken file.
    text = '{"project": "bcnm", "results": {"species": [{"binomial": "Ficus insipida"}]'
    entry, status = core.read_cache_json(str(_write(tmp_path, "a.json", text)))
    assert status == "salvaged"
    assert core.entry_species(entry) == [{"binomial": "Ficus insipida"}]
    assert core.entry_project(entry) == ""


def test_the_species_reader_still_returns_what_it_did_before_the_split(core, tmp_path):
    # load_cache_entry is the older two-value contract, now built on
    # read_cache_json. Every rate on both pages is counted through it.
    ok = {"project": "k-central-america",
          "results": {"species": [{"binomial": "Ficus insipida", "max_score": 0.9}]}}
    assert core.load_cache_entry(str(_write(tmp_path, "a.json", ok))) == (
        ok["results"]["species"], "ok")


# ---------------------------------------------------------------------------
# scan_cache: the counts the run log prints
# ---------------------------------------------------------------------------

def _cache(tmp_path, files):
    for stem, obj in files.items():
        _write(tmp_path, f"{stem}.json", obj)
    return str(tmp_path)


def _answer(project=None, source=None):
    entry = {"results": {"species": [
        {"binomial": "Ficus insipida", "coverage": 0.9, "max_score": 0.9, "count": 1}]}}
    if project is not None:
        entry["project"] = project
    if source is not None:
        entry["project_source"] = source
    return entry


def test_the_walk_counts_answers_by_the_project_they_name(core, health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {
        "a": _answer(core.EVAL_PROJECT, "recorded"),
        "b": _answer(core.EVAL_PROJECT, "assumed"),
        "c": _answer("bcnm", "recorded"),
        "d": _answer(),
    }))
    assert scan.project_count[core.EVAL_PROJECT] == 2
    assert scan.project_count["bcnm"] == 1
    assert scan.project_count[""] == 1
    assert scan.n_no_project == 1
    assert scan.n_foreign_project == 1


def test_recorded_and_assumed_are_counted_apart(core, health, tmp_path):
    # The backfill infers the project from the endpoint that was in force. That
    # is weaker than the fetch writing it, and merging the two loses the fact.
    scan = health.scan_cache(_cache(tmp_path, {
        "a": _answer(core.EVAL_PROJECT, "recorded"),
        "b": _answer(core.EVAL_PROJECT, "assumed"),
        "c": _answer(core.EVAL_PROJECT, "assumed"),
    }))
    assert scan.project_source_count["recorded"] == 1
    assert scan.project_source_count["assumed"] == 2


def test_a_cache_from_one_project_reports_no_foreign_answers(core, health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": _answer(core.EVAL_PROJECT, "recorded")}))
    assert scan.n_foreign_project == 0
    assert scan.n_no_project == 0


# ---------------------------------------------------------------------------
# The fetch stamps what it called
# ---------------------------------------------------------------------------

def test_the_fetch_records_the_project_it_called(photo):
    entry = photo.parse_response({"results": []}, "gk", "http://x/1.jpg", 4000, 3000,
                                1280, project="bcnm")
    assert entry["project"] == "bcnm"
    assert entry["project_source"] == "recorded"


def test_a_fetch_that_names_no_project_says_so_rather_than_guessing(photo):
    entry = photo.parse_response({"results": []}, "gk", "http://x/1.jpg", 4000, 3000, 1280)
    assert entry["project"] == ""
    assert entry["project_source"] == "recorded"


def test_the_settings_carry_the_project_beside_the_url(photo):
    cfg = {"plantnet": {"identify_url": "https://my-api.plantnet.org/v2/identify/bcnm",
                        "identify_nb_results": 5, "identify_organs": "auto",
                        "identify_lang": "en"}}
    api = photo.api_settings(cfg)
    assert api.project == "bcnm"


# ---------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------

def test_the_backfill_stamps_an_answer_that_names_no_project(core, stamper, tmp_path):
    p = _write(tmp_path, "a.json", _answer())
    stamper.run(tmp_path, "k-central-america", True, core)
    entry = json.loads(p.read_text())
    assert entry["project"] == "k-central-america"
    assert entry["project_source"] == "assumed"


def test_the_backfill_changes_nothing_else_in_the_file(core, stamper, tmp_path):
    before = _answer()
    p = _write(tmp_path, "a.json", before)
    stamper.run(tmp_path, "k-central-america", True, core)
    after = json.loads(p.read_text())
    del after["project"], after["project_source"]
    assert after == before


def test_the_backfill_is_a_no_op_the_second_time(core, stamper, tmp_path):
    _write(tmp_path, "a.json", _answer())
    stamper.run(tmp_path, "k-central-america", True, core)
    counts = stamper.run(tmp_path, "k-central-america", True, core)
    assert counts == {"stamp": 0, "already": 1, "foreign": 0, "unreadable": 0}


def test_the_backfill_leaves_an_answer_from_another_project_alone(core, stamper, tmp_path):
    # Overwriting this is how a real mismatch would be hidden, which is the one
    # thing the stamp exists to make visible.
    p = _write(tmp_path, "a.json", _answer("bcnm", "recorded"))
    counts = stamper.run(tmp_path, "k-central-america", True, core)
    assert counts["foreign"] == 1
    assert json.loads(p.read_text())["project"] == "bcnm"


def test_the_backfill_does_not_write_without_being_asked(core, stamper, tmp_path):
    p = _write(tmp_path, "a.json", _answer())
    counts = stamper.run(tmp_path, "k-central-america", False, core)
    assert counts["stamp"] == 1
    assert "project" not in json.loads(p.read_text())


def test_the_backfill_skips_a_payload_it_cannot_read(core, stamper, tmp_path):
    p = _write(tmp_path, "a.json", '{"results": {"species": [{"binomial"')
    counts = stamper.run(tmp_path, "k-central-america", True, core)
    assert counts["unreadable"] == 1
    assert "project" not in p.read_text()


def test_the_backfill_stops_on_an_empty_directory(core, stamper, tmp_path):
    with pytest.raises(SystemExit):
        stamper.run(tmp_path, "k-central-america", True, core)
