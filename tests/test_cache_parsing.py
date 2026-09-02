"""Reading a cached Pl@ntNet response, including the ones that came back broken.

`load_cache_entry` is where the outside world enters this repo. Every rate on
both pages is computed from what it returns, and it is the only function in
`core.py` that has to cope with a file it did not write: a fetch killed
mid-write, a payload truncated inside `per_tiles_embeddings`, JSON with trailing
bytes after it. It had no test, so the difference between "no species" and
"unreadable" rested on nothing.

The distinction matters on the page. An empty list is a real answer, counted in
"unlabelled photos got no answer at all"; unreadable is a broken file, and the
run log reports the two separately.

    .venv/bin/pytest tests/test_cache_parsing.py
"""

from __future__ import annotations

import json

OK = {"results": {"species": [{"name": "Ficus insipida", "score": 0.9}]}}


def _write(tmp_path, text, name="entry.json"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# The three statuses
# ---------------------------------------------------------------------------

def test_a_clean_response_reads_as_ok(core, tmp_path):
    sp, status = core.load_cache_entry(_write(tmp_path, json.dumps(OK)))
    assert status == "ok"
    assert sp[0]["name"] == "Ficus insipida"


def test_a_response_with_no_species_is_ok_and_empty_not_unreadable(core, tmp_path):
    """Pl@ntNet returning nothing is an answer. The queue page counts these as
    "got no answer at all" and sends them to a human, which is a different
    action from re-fetching a corrupt file."""
    for payload in ('{"results": {"species": []}}', '{"results": {}}', "{}"):
        sp, status = core.load_cache_entry(_write(tmp_path, payload))
        assert (sp, status) == ([], "ok"), payload


def test_json_followed_by_trailing_bytes_is_salvaged_whole(core, tmp_path):
    """A second write appended to a finished one. The first object is complete,
    so nothing is lost and the status records that the file was not clean."""
    sp, status = core.load_cache_entry(_write(tmp_path, json.dumps(OK) + '\n{"results"'))
    assert status == "salvaged"
    assert sp[0]["name"] == "Ficus insipida"


def test_a_payload_truncated_after_the_species_array_is_salvaged(core, tmp_path):
    """The failure this was written for: the fetch died while writing
    `per_tiles_embeddings`, which follows `species` in the payload. The species
    array is complete and is the only part any page reads."""
    text = ('{"results": {"species": [{"name": "Ficus insipida", "score": 0.9}], '
            '"per_tiles_embeddings": [[0.1, 0.2, 0.3')
    sp, status = core.load_cache_entry(_write(tmp_path, text))
    assert status == "salvaged"
    assert [s["name"] for s in sp] == ["Ficus insipida"]


def test_a_file_truncated_inside_the_species_array_is_unreadable(core, tmp_path):
    """No closing bracket, so nothing can be trusted. Reported as unreadable
    rather than as the partial list, which would publish a rate over a
    truncated candidate set."""
    text = '{"results": {"species": [{"name": "Ficus insipida", "sco'
    assert core.load_cache_entry(_write(tmp_path, text)) == ([], "unreadable")


def test_a_file_that_is_not_json_at_all_is_unreadable(core, tmp_path):
    assert core.load_cache_entry(_write(tmp_path, "")) == ([], "unreadable")
    assert core.load_cache_entry(_write(tmp_path, "<html>502</html>")) == ([], "unreadable")


def test_undecodable_bytes_do_not_raise(core, tmp_path):
    """Opened with errors="replace", so a half-written UTF-8 sequence gives an
    unreadable entry rather than an exception that stops the whole run."""
    p = tmp_path / "bad.json"
    p.write_bytes(b'{"results": {"species": [{"name": "Fic\xff\xfe')
    assert core.load_cache_entry(str(p)) == ([], "unreadable")


# ---------------------------------------------------------------------------
# salvage_species_array, the bracket matcher underneath
# ---------------------------------------------------------------------------

def test_the_salvage_matches_brackets_rather_than_stopping_at_the_first(core):
    """Every candidate carries nested lists in a real payload, so a matcher
    that stopped at the first `]` would return a short list and the page would
    report a smaller candidate set than Pl@ntNet sent."""
    text = ('{"results": {"species": [{"name": "A", "images": [1, 2]}, '
            '{"name": "B", "images": []}], "per_tiles_embeddings": [[0.1')
    assert [s["name"] for s in core.salvage_species_array(text)] == ["A", "B"]


def test_the_salvage_starts_looking_after_the_species_key_not_at_the_first_bracket(core):
    """A real payload carries `predictedOrgans` and a `query` block before
    `results`, so the first `[` in the file is not the species array. Searching
    from the start of the text would salvage the wrong list and report it as
    Pl@ntNet's candidates."""
    text = ('{"predictedOrgans": [{"organ": "leaf"}], '
            '"results": {"species": [{"name": "A"}], "per_tiles_embeddings": [[0.1')
    assert [s["name"] for s in core.salvage_species_array(text)] == ["A"]


def test_the_salvage_returns_none_when_there_is_nothing_to_find(core):
    assert core.salvage_species_array("") is None
    assert core.salvage_species_array('{"results": {}}') is None      # no key
    assert core.salvage_species_array('{"species"') is None           # no bracket
    assert core.salvage_species_array('{"species": [1, 2') is None    # never closes


def test_the_salvage_returns_none_rather_than_raising_on_bad_json_inside(core):
    """Brackets can balance over content that is not valid JSON. None, so the
    caller records unreadable instead of the exception reaching a builder."""
    assert core.salvage_species_array('{"species": [not json]}') is None
