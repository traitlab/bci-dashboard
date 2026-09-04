"""Tests for the part of dashboard/panels.py that needs no snapshot: the panel
registry and the section-assembly machinery.

`prepare()` needs real measurement CSVs (a snapshot), so `tests/test_pages.py`
builds a real page end to end and skips itself on a fresh clone. That leaves
the registry itself -- which panel belongs to which page, the prose
dictionaries every panel reads, `parse_args` -- with no coverage at all on a
bare checkout. These tests call none of `prepare()`, `render()`'s builders, or
any panel function: everything here is reachable from the module's top level.

    .venv/bin/pytest tests/test_page.py
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

def test_every_panel_belongs_to_exactly_one_page(pagemod, panels):
    # panels.py already raises SystemExit at import time if this is violated
    # (see the `if set(INTERNAL_PANELS) | set(EXTERNAL_PANELS) != set(PANELS)`
    # check right after the registry), so importing the module at all is one
    # proof of this. Asserted again here so a future refactor that removes
    # that guard still has a test catching the drift.
    internal = set(pagemod.INTERNAL_PANELS)
    external = set(pagemod.EXTERNAL_PANELS)
    assert internal | external == set(pagemod.PANELS)
    assert not (internal & external), (
        f"panels claimed by both pages: {sorted(internal & external)}")


def test_internal_and_external_panel_lists_have_no_duplicates(pagemod):
    # A tuple, unlike PANELS, does not enforce uniqueness on its own -- a panel
    # id repeated in INTERNAL_PANELS would render the same section twice.
    assert len(pagemod.INTERNAL_PANELS) == len(set(pagemod.INTERNAL_PANELS))
    assert len(pagemod.EXTERNAL_PANELS) == len(set(pagemod.EXTERNAL_PANELS))


def test_every_panel_entry_has_a_known_section_and_a_callable_builder(pagemod):
    for pid, (section_key, builder) in pagemod.PANELS.items():
        assert section_key in pagemod.SECTIONS, (
            f"panel {pid!r} claims section {section_key!r}, which is not in SECTIONS")
        assert callable(builder), f"panel {pid!r}'s builder is not callable"


def test_panel_ids_are_non_empty_and_valid_html_id_fragments(pagemod):
    for pid in pagemod.PANELS:
        assert pid, "a panel id is empty"
        assert _ID_RE.match(pid), f"panel id {pid!r} is not a valid HTML id fragment"


def test_section_headings_are_non_empty_except_the_headline_band(pagemod):
    # `render()` treats a title of None as the un-headed band the headline
    # cards sit in; every other section must carry a real heading and lede,
    # since a blank one would print an empty <h2> or <p class="lede">.
    for key, (title, lede) in pagemod.SECTIONS.items():
        if key == "headline":
            assert title is None and lede is None
            continue
        assert title, f"section {key!r} has an empty heading"
        assert lede, f"section {key!r} has an empty lede"


def test_every_section_key_used_by_a_panel_is_a_real_section(pagemod):
    used = {section_key for section_key, _ in pagemod.PANELS.values()}
    assert used <= set(pagemod.SECTIONS)


# ---------------------------------------------------------------------------
# render(): section assembly and the id-collision guard it exists to enforce
# ---------------------------------------------------------------------------

def test_render_rejects_an_unknown_panel_id(pagemod):
    with pytest.raises(SystemExit, match="no such panel"):
        pagemod.render(None, ["not-a-real-panel-id"])


def test_render_of_no_panels_is_empty(pagemod):
    assert pagemod.render(None, []) == ""


# ---------------------------------------------------------------------------
# The prose dictionaries: every status/queue the code can branch to must have
# an entry, or a reader hits a KeyError or a blank cell.
# ---------------------------------------------------------------------------

def test_status_reason_covers_every_status_key(status_words):
    # STATUS is the order the to-do list prints in; STATUS_REASON is the
    # legend sentence for each. `status_words.legend_entries` looks both up by
    # the same key, so a status present in one and missing from the other is a
    # KeyError waiting on whichever species first gets that status.
    assert set(status_words.STATUS) == set(status_words.STATUS_REASON)


def test_status_and_status_reason_entries_are_non_empty(status_words):
    for key, (label, action) in status_words.STATUS.items():
        assert label.strip(), f"STATUS[{key!r}] has an empty label"
        assert action.strip(), f"STATUS[{key!r}] has an empty action"
    for key, reason in status_words.STATUS_REASON.items():
        assert reason.strip(), f"STATUS_REASON[{key!r}] is empty"


def test_ql_covers_every_queue_the_send_first_policy_can_return(queues, queue_panels):
    # QL is read in QUEUE_ORDER, queues.py's own order (p_send). Derived from
    # there rather than a copied literal list, so this fails the moment a queue
    # is added or renamed on either side without the other.
    assert set(queue_panels.QL) == set(queues.QUEUE_ORDER)


def test_ql_entries_are_non_empty(queue_panels):
    for key, (label, why) in queue_panels.QL.items():
        assert label.strip(), f"QL[{key!r}] has an empty label"
        assert why.strip(), f"QL[{key!r}] has an empty why"


# ---------------------------------------------------------------------------
# Prose that quotes a live constant: it must actually quote it, not a literal
# that happened to match the constant's value on the day it was written.
# ---------------------------------------------------------------------------

def test_status_reason_unmeasured_quotes_the_well_sampled_constant(status_words, core):
    assert str(core.WELL_SAMPLED_MIN_N) in status_words.STATUS_REASON["unmeasured"]


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
# parse_args: the defaults, which are what a bare run gets
# ---------------------------------------------------------------------------

def test_parse_args_defaults(pagemod, monkeypatch):
    monkeypatch.setattr("sys.argv", ["build_external.py"])
    args = pagemod.parse_args("doc", "some_page.html")
    assert args.model_tag == "unknown"
    assert args.verify_against is None
    assert args.generated is None
    assert args.out.endswith("some_page.html")


# The flags refresh.sh passes were retyped here and checked against
# parse_args, which is a copy of a command line that lives in a file.
# tests/test_documented_commands.py reads refresh.sh, the README and every
# module docstring instead, and puts each command to the script it names.


def test_parse_args_default_out_is_under_the_repo_build_dir(pagemod, monkeypatch):
    import core as hc

    monkeypatch.setattr("sys.argv", ["build_internal.py"])
    args = pagemod.parse_args("doc", "label_queue_dashboard.html")
    assert args.out == os.path.join(hc.REPO, "build", "label_queue_dashboard.html")


# ---------------------------------------------------------------------------
# document(): the page wrapper, a pure function of a title and a body
# ---------------------------------------------------------------------------

def test_document_embeds_css_and_js_inline_with_no_external_reference(assets, pagemod, panels):
    strip_comments = assets.strip_comments
    html = pagemod.document("A Title", "<p>body</p>")
    assert "<title>A Title</title>" in html
    assert "<p>body</p>" in html
    # page.py inlines the CSS and JS with the maintainer comments stripped, and
    # the CSS also drops the rules for classes this body never renders.
    css = assets.css_for(strip_comments(pagemod.CSS), "<p>body</p>" + pagemod.JS)
    assert f"<style>{css}</style>" in html
    # This body has no species table, so it gets the half of the script every
    # page needs and not the 2.4KB that drives one.
    assert f"<script>{strip_comments(pagemod.EVERY_PAGE_JS)}</script>" in html
    with_table = pagemod.document("T", f"<table id={pagemod.TABLE_ID!r}></table>")
    assert strip_comments(pagemod.JS) in with_table
    # Stripping is comments only: no rule and no statement may go with them.
    assert "box-sizing:border-box" in html and "addEventListener" in html
    assert "/*" not in html.split("</style>")[0]
    assert "<link" not in html
    assert "script src" not in html


def test_document_is_one_self_contained_html_document(pagemod):
    html = pagemod.document("T", "body")
    assert html.startswith("<!DOCTYPE html>")
    assert html.count("<html") == 1
    assert html.rstrip().endswith("</html>")


# ---------------------------------------------------------------------------
# The CSVs a page links have to travel with it.
# ---------------------------------------------------------------------------

def test_a_linked_csv_is_copied_next_to_the_page(pagemod, tmp_path):
    """The link resolves wherever the page lands, build/ or a snapshot.

    bin/refresh.sh used to be the only thing putting a page beside its CSVs,
    and the two newest snapshots on the machine this was written on hold CSVs
    and no page, because those builds bypassed the script. Doing the copy in
    the build is what makes the two arrive together every time.
    """
    snap, out = tmp_path / "snap", tmp_path / "build" / "page.html"
    snap.mkdir()
    (snap / "label_review_queue.csv").write_text("global_key\nk1\n", encoding="utf-8")
    (snap / "unlinked.csv").write_text("nobody links this\n", encoding="utf-8")
    out.parent.mkdir()

    page = '<a href="label_review_queue.csv">label_review_queue.csv</a>'
    pagemod.copy_linked_csvs(page, str(snap), str(out))

    assert (out.parent / "label_review_queue.csv").read_text(encoding="utf-8") == \
        "global_key\nk1\n"
    assert not (out.parent / "unlinked.csv").exists(), \
        "only the CSVs the page links travel with it"


def test_a_link_to_a_csv_the_snapshot_does_not_hold_aborts_the_build(pagemod, tmp_path):
    """A 404 in front of the reader is worse than a filename in prose."""
    snap, out = tmp_path / "snap", tmp_path / "build" / "page.html"
    snap.mkdir()
    out.parent.mkdir()

    with pytest.raises(SystemExit) as e:
        pagemod.copy_linked_csvs('<a href="send_first_queue.csv">q</a>',
                                 str(snap), str(out))
    assert "send_first_queue.csv" in str(e.value)


def test_every_csv_a_panel_links_is_one_measure_writes(pagemod, measure):
    """A link is only as good as the name in it, and the name is typed by hand.

    Reads the panel sources rather than a built page so it runs on a fresh
    clone, where no snapshot exists to build one from.
    """
    import glob
    linked = set()
    for path in glob.glob(os.path.join(os.path.dirname(pagemod.__file__), "*.py")):
        with open(path, encoding="utf-8") as f:
            linked |= set(pagemod._LINKED_CSV.findall(f.read()))
    assert linked, "no panel links a CSV; this test has stopped covering anything"
    unknown = linked - set(measure.OUTPUTS)
    assert not unknown, f"linked CSVs that measure.py never writes: {sorted(unknown)}"


def test_the_publish_script_reads_the_links_rather_than_listing_them(measure):
    """The other half of the copy, and the half that fails on the public site.

    ``copy_linked_csvs`` puts a linked CSV beside the page in build/;
    ``bin/publish_pages.sh`` is what puts it in docs/, which is what GitHub
    Pages serves. It used to name the four files it copied. That list was a
    second copy of a fact the pages already state, and the way it broke was a
    panel adding a link and the file never reaching docs/: a 404 for every
    reader, and nothing local to notice it. So the names must not be back.
    """
    script = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "bin", "publish_pages.sh")
    with open(script, encoding="utf-8") as f:
        text = f.read()
    named = [name for name in measure.OUTPUTS if name in text]
    assert not named, (
        f"publish_pages.sh names {named} instead of reading the links out of the "
        f"built pages; add one link to a panel and these stop reaching docs/")
    assert "grep" in text and "href=" in text, \
        "publish_pages.sh no longer scans the pages for the CSVs they link"
