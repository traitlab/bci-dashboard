"""Tests for the part of dashboard/panels.py that needs no snapshot: the panel
registry and the section-assembly machinery.

`prepare()` needs real measurement CSVs (a snapshot), so `tests/test_pages.py`
builds a real page end to end and skips itself on a fresh clone. That leaves
the registry itself -- which panel belongs to which page, the prose
dictionaries every panel reads, `parse_args` -- with no coverage at all on a
bare checkout. These tests call none of `prepare()`, `render()`'s builders, or
any panel function: everything here is reachable from the module's top level.

    .venv/bin/pytest tests/test_panels_registry.py
"""

from __future__ import annotations

import os
import re

import pytest

# A valid HTML id fragment: letters, digits and hyphens, not starting with a
# digit. `panel()` in assets.py derives the id a reader actually links to from
# the summary text via `slug()`, not from these registry keys -- but the keys
# are also read back by `render()` and by INTERNAL_PANELS/EXTERNAL_PANELS, and
# nothing stops a future call site from using one as an anchor=, so the same
# rule is worth holding them to now.
_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


# ---------------------------------------------------------------------------
# The registry: PANELS, SECTIONS, INTERNAL_PANELS, EXTERNAL_PANELS
# ---------------------------------------------------------------------------

def test_every_panel_belongs_to_exactly_one_page(panels):
    # panels.py already raises SystemExit at import time if this is violated
    # (see the `if set(INTERNAL_PANELS) | set(EXTERNAL_PANELS) != set(PANELS)`
    # check right after the registry), so importing the module at all is one
    # proof of this. Asserted again here so a future refactor that removes
    # that guard still has a test catching the drift.
    internal = set(panels.INTERNAL_PANELS)
    external = set(panels.EXTERNAL_PANELS)
    assert internal | external == set(panels.PANELS)
    assert not (internal & external), (
        f"panels claimed by both pages: {sorted(internal & external)}")


def test_internal_and_external_panel_lists_have_no_duplicates(panels):
    # A tuple, unlike PANELS, does not enforce uniqueness on its own -- a panel
    # id repeated in INTERNAL_PANELS would render the same section twice.
    assert len(panels.INTERNAL_PANELS) == len(set(panels.INTERNAL_PANELS))
    assert len(panels.EXTERNAL_PANELS) == len(set(panels.EXTERNAL_PANELS))


def test_every_panel_entry_has_a_known_section_and_a_callable_builder(panels):
    for pid, (section_key, builder) in panels.PANELS.items():
        assert section_key in panels.SECTIONS, (
            f"panel {pid!r} claims section {section_key!r}, which is not in SECTIONS")
        assert callable(builder), f"panel {pid!r}'s builder is not callable"


def test_panel_ids_are_non_empty_and_valid_html_id_fragments(panels):
    for pid in panels.PANELS:
        assert pid, "a panel id is empty"
        assert _ID_RE.match(pid), f"panel id {pid!r} is not a valid HTML id fragment"


def test_section_headings_are_non_empty_except_the_headline_band(panels):
    # `render()` treats a title of None as the un-headed band the headline
    # cards sit in; every other section must carry a real heading and lede,
    # since a blank one would print an empty <h2> or <p class="lede">.
    for key, (title, lede) in panels.SECTIONS.items():
        if key == "headline":
            assert title is None and lede is None
            continue
        assert title, f"section {key!r} has an empty heading"
        assert lede, f"section {key!r} has an empty lede"


def test_every_section_key_used_by_a_panel_is_a_real_section(panels):
    used = {section_key for section_key, _ in panels.PANELS.values()}
    assert used <= set(panels.SECTIONS)


# ---------------------------------------------------------------------------
# render(): section assembly and the id-collision guard it exists to enforce
# ---------------------------------------------------------------------------

def test_render_rejects_an_unknown_panel_id(panels):
    with pytest.raises(SystemExit, match="no such panel"):
        panels.render(None, ["not-a-real-panel-id"])


def test_render_of_no_panels_is_empty(panels):
    assert panels.render(None, []) == ""


# ---------------------------------------------------------------------------
# The prose dictionaries: every status/queue the code can branch to must have
# an entry, or a reader hits a KeyError or a blank cell.
# ---------------------------------------------------------------------------

def test_status_reason_covers_every_status_key(panels):
    # STATUS is the order the to-do list prints in; STATUS_REASON is the
    # legend sentence for each. p_species looks both up by the same key
    # (see status_legend([(st, STATUS[st][0], STATUS_REASON[st]) ...])), so a
    # status present in one and missing from the other is a KeyError waiting
    # on whichever species first gets that status.
    assert set(panels.STATUS) == set(panels.STATUS_REASON)


def test_status_and_status_reason_entries_are_non_empty(panels):
    for key, (label, action) in panels.STATUS.items():
        assert label.strip(), f"STATUS[{key!r}] has an empty label"
        assert action.strip(), f"STATUS[{key!r}] has an empty action"
    for key, reason in panels.STATUS_REASON.items():
        assert reason.strip(), f"STATUS_REASON[{key!r}] is empty"


def test_ql_covers_every_queue_hc_diagnoses(queue_panels):
    # QL is read in QUEUE_ORDER, hc.QUEUE_ORDER's own order (p_send). Derived
    # from core.py rather than a copied literal list, so this fails the moment
    # a queue is added or renamed on either side without the other.
    import core as hc  # already on sys.path via the `panels` fixture

    assert set(queue_panels.QL) == set(hc.QUEUE_ORDER)


def test_ql_entries_are_non_empty(queue_panels):
    for key, (label, why) in queue_panels.QL.items():
        assert label.strip(), f"QL[{key!r}] has an empty label"
        assert why.strip(), f"QL[{key!r}] has an empty why"


# ---------------------------------------------------------------------------
# Prose that quotes a live constant: it must actually quote it, not a literal
# that happened to match the constant's value on the day it was written.
# ---------------------------------------------------------------------------

def test_status_reason_unmeasured_quotes_the_well_sampled_constant(panels):
    import core as hc

    assert str(hc.WELL_SAMPLED_MIN_N) in panels.STATUS_REASON["unmeasured"]


def test_ql_long_tail_quotes_the_well_sampled_constant(queue_panels):
    import core as hc

    assert str(hc.WELL_SAMPLED_MIN_N) in queue_panels.QL["long_tail"][1]


def test_rare_and_wait_thresholds_are_the_well_sampled_constant(queue_panels):
    # RARE_MAX_SUPPORT and WAIT_SUPPORT_MIN both alias hc.WELL_SAMPLED_MIN_N
    # rather than restating it, per the comment above their definition --
    # if either drifted into its own literal, a page could show a status
    # that disagrees with the rule hc.diagnose actually applied.
    import core as hc

    assert queue_panels.RARE_MAX_SUPPORT == hc.WELL_SAMPLED_MIN_N
    assert queue_panels.WAIT_SUPPORT_MIN == hc.WELL_SAMPLED_MIN_N


# ---------------------------------------------------------------------------
# parse_args: defaults, and the flags bin/refresh.sh actually passes
# ---------------------------------------------------------------------------

def test_parse_args_defaults(panels, monkeypatch):
    monkeypatch.setattr("sys.argv", ["build_external.py"])
    args = panels.parse_args("doc", "some_page.html")
    assert args.model_tag == "unknown"
    assert args.verify_against is None
    assert args.generated is None
    assert args.out.endswith("some_page.html")


def test_parse_args_accepts_every_flag_bin_refresh_sh_passes(panels, monkeypatch):
    # bin/refresh.sh calls both builders as:
    #   python3 dashboard/build_*.py --verify-against "$SNAP" \
    #       --out "$REPO/build/*.html" --generated "$TODAY"
    # A flag refresh.sh passes that parse_args does not accept would abort
    # every scheduled refresh with an argparse error.
    monkeypatch.setattr("sys.argv", [
        "build_external.py",
        "--verify-against", "/tmp/snap",
        "--out", "/tmp/out.html",
        "--generated", "2026-08-25",
    ])
    args = panels.parse_args("doc", "some_page.html")
    assert args.verify_against == "/tmp/snap"
    assert args.out == "/tmp/out.html"
    assert args.generated == "2026-08-25"


def test_parse_args_default_out_is_under_the_repo_build_dir(panels, monkeypatch):
    import core as hc

    monkeypatch.setattr("sys.argv", ["build_internal.py"])
    args = panels.parse_args("doc", "label_queue_dashboard.html")
    assert args.out == os.path.join(hc.REPO, "build", "label_queue_dashboard.html")


# ---------------------------------------------------------------------------
# document(): the page wrapper, a pure function of a title and a body
# ---------------------------------------------------------------------------

def test_document_embeds_css_and_js_inline_with_no_external_reference(panels):
    html = panels.document("A Title", "<p>body</p>")
    assert "<title>A Title</title>" in html
    assert "<p>body</p>" in html
    # panels.py imports CSS and JS from assets and inlines them verbatim, so
    # the module's own copies must show up whole in the wrapped page.
    assert f"<style>{panels.CSS}</style>" in html
    assert f"<script>{panels.JS}</script>" in html
    assert "<link" not in html
    assert "script src" not in html


def test_document_is_one_self_contained_html_document(panels):
    html = panels.document("T", "body")
    assert html.startswith("<!DOCTYPE html>")
    assert html.count("<html") == 1
    assert html.rstrip().endswith("</html>")
