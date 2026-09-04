"""The one review table: every frame, grouped by pair, linked where a link exists.

The panel used to print two tables, a confusion-pairs table capped at ten and a
frames table capped at fifteen. Two caps over one population read as two
populations, and the pair a reader goes looking for is the one outside the
first cap. There is now one table, every frame in it, each label-and-guess pair
a heading over its own frames.

The row count is the gate. It has to equal the row count of
label_review_queue.csv, which the page also links, because a reader who opens
both is comparing the same list.

    .venv/bin/pytest tests/test_review_panel.py
"""

from __future__ import annotations

import csv
import re
from types import SimpleNamespace

import pytest
from conftest import SNAPSHOT_DIR

PANEL = re.compile(r'id="labels-worth-a-second-look".*?</details>', re.S)
HEADING = re.compile(r"<th colspan=")
FRAME_ROW = re.compile(r'<td class="num">\d\.\d\d</td>')


def review_panel(html: str) -> str:
    found = PANEL.search(html)
    assert found, "the external page carries no review panel"
    return found.group(0)


def queue_rows():
    with open(SNAPSHOT_DIR / "label_review_queue.csv", newline="",
              encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_the_preview_cap_is_gone(panels):
    """The constant that capped the old frames table. Named here so a revert
    that brings the cap back fails rather than quietly shortening the table."""
    assert not hasattr(panels, "REVIEW_PREVIEW")


def test_the_panel_prints_one_table(external_page):
    """One table, not a pairs table beside a frames table."""
    assert review_panel(external_page[0]).count("<table>") == 1


def test_every_review_frame_is_in_the_table(external_page):
    """The gate: the table and the CSV the panel links are the same list."""
    rows = queue_rows()
    panel = review_panel(external_page[0])
    assert len(FRAME_ROW.findall(panel)) == len(rows) > 0


def test_one_heading_per_label_and_guess_pair(external_page):
    """A heading row carries the pair and its own frame count, so the pair
    counts survive without a second table and a second denominator."""
    rows = queue_rows()
    pairs = {(r["gt_species"], r["predicted_species"]) for r in rows}
    assert len(HEADING.findall(review_panel(external_page[0]))) == len(pairs)


def test_the_pair_coverage_sentence_counts_the_recurring_pairs(panels):
    """The sentence and the headings are both read off one grouping."""
    review = [{"gt": "a b", "ranked": [("c d", 0.9)], "global_key": "k1",
               "split": "train"},
              {"gt": "a b", "ranked": [("c d", 0.95)], "global_key": "k2",
               "split": "train"},
              {"gt": "e f", "ranked": [("g h", 0.9)], "global_key": "k3",
               "split": "val"}]
    groups = panels._review_pairs(review)
    assert [len(rows) for _, rows in groups] == [2, 1]
    # Most confident first inside a pair, recurring pairs first between them.
    assert [r["global_key"] for r in groups[0][1]] == ["k2", "k1"]


def fake_context(review, n_adjudicated=0):
    """The figures a review panel reads, and nothing else."""
    return SimpleNamespace(review=review, n_adjudicated=n_adjudicated,
                           confident=review, confident_hits=len(review),
                           confident_ok=1.0,
                           h=SimpleNamespace(gt_rows=list(review)))


def test_a_frame_a_botanist_confirmed_still_counts_against_accuracy(panels):
    """It leaves the queue, because it would return on every build, and the
    panel says so rather than letting the shorter list read as a better model."""
    review = [{"gt": "a b", "ranked": [("c d", 0.9)], "global_key": "k1",
               "split": "train"}]
    html = panels.p_review(fake_context(review, n_adjudicated=3))
    assert "3 further frames" in html
    assert "still count against" in html


def test_nothing_is_said_about_suppression_when_nothing_is_suppressed(panels):
    review = [{"gt": "a b", "ranked": [("c d", 0.9)], "global_key": "k1",
               "split": "train"}]
    assert "further frame" not in panels.p_review(fake_context(review))


def test_an_empty_review_list_prints_no_empty_table(panels):
    """A model that is never confidently wrong raises no rows, which is a
    sentence and not a table with a header and nothing under it."""
    html = panels.p_review(fake_context([]))
    assert "<table>" not in html
    assert "None at this confidence" in html


# ---------------------------------------------------------------------------
# The Labelbox links, and the sentence that says how far they reach
# ---------------------------------------------------------------------------

def test_a_frame_with_a_known_data_row_is_linked(external_page, core):
    """Every key the offline join reaches carries an anchor, and no key it does
    not reach carries an invented one."""
    urls = core.labelbox_urls()
    panel = review_panel(external_page[0])
    linked = set(re.findall(r'rel="noopener">([^<]+)</a>', panel))
    keys = {r["global_key"] for r in queue_rows()}
    assert linked == {k for k in keys if k in urls}
    assert linked, "no review frame links to Labelbox"


def test_the_links_open_the_legacy_project(external_page, core):
    """Legacy by default: those are the rows the botanist's boxes were drawn
    in, so a link into the dispatch project would open a row with no boxes.

    Asserted on the project id in each URL, not on the prefix: every mode
    produces the same prefix, so a prefix check passes when the destination is
    wrong. The dispatch project is the one `data_row_ids.csv` stamps on every
    row, and in legacy mode no published link may land there.
    """
    assert core.link_project_mode() == core.LINK_PROJECT_LEGACY
    dispatch = {r["project_id"] for r in core.read_csv_rows(core.DATA_ROW_IDS_CSV)
                if r.get("project_id")}
    assert dispatch, f"{core.DATA_ROW_IDS_CSV} names no project"
    panel = review_panel(external_page[0])
    urls = re.findall(r'href="(https://[^"]+)"', panel)
    assert urls, "no review frame links to Labelbox"
    seen = set()
    for url in urls:
        assert url.startswith(core.LABELBOX_URL.split("{", 1)[0]), url
        project = re.search(r"/projects/([^/]+)/", url).group(1)
        assert project not in dispatch, f"{url} opens the dispatch project"
        seen.add(project)
    assert len(seen) > 1, f"every link went to one project, {seen}"


def test_the_panel_states_how_far_the_links_reach(external_page, core):
    """A count with its population, twice: this table's, and the page-wide
    figure that says whether the shortfall is local."""
    urls = core.labelbox_urls()
    keys = [r["global_key"] for r in queue_rows()]
    here = core.labelbox_link_coverage(keys, urls)
    panel = review_panel(external_page[0])
    assert (f'{here["n_linked"]} of {here["n_frames"]} frames link to their row '
            f'in Labelbox') in panel
    assert "labelled frames page-wide" in panel


def test_a_shortfall_is_explained_rather_than_left_as_a_gap(panels):
    """Not a broken link and not a limitation: no file here names both halves of
    the link, and either of the two files that can closes it.

    Tested on the note rather than on the page, because the page has no
    shortfall to show: both sources together now name a link for every labelled
    frame. The sentence still has to be right for the build where they do not."""
    note = panels._link_note(
        {"n_linked": 40, "n_frames": 51, "n_unlinked": 11, "by_project": {"p": 40}},
        {"n_linked": 3000, "n_frames": 3781, "share": 0.79})
    assert "The other 11 are not unlinkable" in note
    assert "names both the project and the data row" in note


def test_no_shortfall_means_no_sentence_about_one(external_page, core):
    """The clause is conditional, so a fully linked table must not carry it."""
    keys = [r["global_key"] for r in queue_rows()]
    here = core.labelbox_link_coverage(keys, core.labelbox_urls())
    panel = review_panel(external_page[0])
    if here["n_unlinked"]:
        pytest.skip(f"{here['n_unlinked']} frames are unlinked in this build")
    assert "are not unlinkable" not in panel


def test_the_link_note_says_nothing_about_a_split_it_cannot_see(panels):
    """One project, or none linked at all, is not a split worth a clause."""
    assert panels._project_split({"by_project": {}}) == ""
    assert panels._project_split({"by_project": {"p": 4}}) == ""
    two = panels._project_split({"by_project": {"p": 4, "q": 1}})
    assert two == ", 4 in one Labelbox project and 1 in the other"
