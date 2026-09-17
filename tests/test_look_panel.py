"""The queue page's evidence that ordering by look does anything.

Everything this panel draws comes from files written by hand, outside
`bin/refresh.sh`: two curve files from `labelling/rank_queue.py` and a directory
of small pictures from `labelling/fetch_thumbs.py`. A fresh clone has none of
them, and a run that stopped part-way has some. So "the file is not there" and
"the file covers half of what I asked for" are both normal states, and the panel
has to be right in all of them rather than drawing an empty pair of axes or a
sheet with holes in it.

    .venv/bin/pytest tests/test_look_panel.py
"""

from __future__ import annotations

import base64
import os
from types import SimpleNamespace

import pytest


@pytest.fixture
def look(monkeypatch, figures, tmp_path):
    """`figures._look` pointed at a temporary data directory.

    Patched on `figures.hc`, the module object figures actually reads, and not
    on the `core` fixture: that fixture loads core under a second name, so a
    path set there would leave figures reading the real one.
    """
    monkeypatch.setattr(figures.hc, "DISCOVERY_CURVE_CSV", str(tmp_path / "discovery.csv"))
    monkeypatch.setattr(figures.hc, "NOVELTY_CURVE_CSV", str(tmp_path / "novelty.csv"))
    monkeypatch.setattr(figures.hc, "SELECTION_AUDIT_JSON", str(tmp_path / "audit.json"))
    monkeypatch.setattr(figures.hc, "SELECTION_CONFOUND_JSON",
                        str(tmp_path / "confound.json"))
    monkeypatch.setattr(figures.hc, "THUMB_DIR", str(tmp_path / "thumbs"))
    return figures, tmp_path


def _rows(*specs):
    """(queue, stem, prediction, confidence, novelty rank) per spec.

    Every stem carries a camera, because `figures.camera_of` reads the key and
    exits on one that names neither. A test frame called "a" is not a frame this
    repo could ever hold.
    """
    return [(q, stem if ("zoom" in stem or "tele" in stem) else f"{stem}_zoom",
             "guessed sp", 0.5, rank) for q, stem, rank in specs]


# ---------------------------------------------------------------------------
# missing files
# ---------------------------------------------------------------------------

def test_no_curve_files_leaves_every_curve_empty_rather_than_raising(look, queues):
    figures, _ = look
    out = figures._look(_rows(("normal", "a", 1)), {"zoom": 1}, 1)
    assert out["discovery"] == [] and out["novelty_curve"] == []
    assert out["discovery_half_directed"] is None
    assert out["thumbs"] == {}


def test_a_curve_file_missing_a_column_stops_the_build(look):
    """Silently drawing a chart one column short would publish a line nobody
    could trace. `_read_curve` names the file and the column instead."""
    figures, tmp = look
    (tmp / "discovery.csv").write_text("photos_named,species_directed\n1,1\n")
    with pytest.raises(ValueError, match="species_random"):
        figures._look(_rows(("normal", "a", 1)), {"zoom": 1}, 1)


def test_the_panel_says_so_when_there_is_nothing_to_draw(queue_why_panels):
    """A panel that renders nothing reads as a bug. This one says which script
    writes the files it is missing."""
    out = queue_why_panels.NO_CURVES
    assert "rank_queue.py" in out and "not been scored" in out


# ---------------------------------------------------------------------------
# the curves
# ---------------------------------------------------------------------------

def test_the_half_species_crossing_is_the_first_point_that_reaches_it(look):
    figures, tmp = look
    (tmp / "discovery.csv").write_text(
        "photos_named,species_directed,species_random\n"
        "1,2,1\n2,6,2\n3,8,4\n4,10,10\n")
    out = figures._look(_rows(("normal", "a", 1)), {"zoom": 1}, 1)
    assert out["discovery_species"] == 10
    assert out["discovery_half"] == 5
    # Directed reaches 5 species at its second photo; random not until its
    # fourth. That gap is the whole claim the chart makes.
    assert out["discovery_half_directed"] == 2
    assert out["discovery_half_random"] == 4


def test_a_line_that_never_reaches_the_level_has_no_crossing(look):
    """Reported as absent, not as the last photo: a run cut short must not read
    as one that got there on the final frame."""
    figures, tmp = look
    (tmp / "discovery.csv").write_text(
        "photos_named,species_directed,species_random\n1,2,0\n2,10,1\n")
    out = figures._look(_rows(("normal", "a", 1)), {"zoom": 1}, 1)
    assert out["discovery_half_directed"] == 2
    assert out["discovery_half_random"] is None


def test_the_novelty_curve_drops_the_bin_size_the_page_does_not_draw(look):
    figures, tmp = look
    (tmp / "novelty.csv").write_text(
        "novelty_rank,mean_distance_to_nearest_labelled,photos_in_bin\n"
        "30,0.42,30\n60,0.31,30\n")
    out = figures._look(_rows(("normal", "a", 1)), {"zoom": 1}, 1)
    assert out["novelty_curve"] == [(30.0, 0.42), (60.0, 0.31)]


# ---------------------------------------------------------------------------
# the camera mix at the head
# ---------------------------------------------------------------------------

def test_the_head_is_the_top_ranked_frames_not_the_top_of_the_page(look):
    """The page groups by queue first, so the frames it lists first are not the
    frames the ordering ranked first. The published share is the ranked ones."""
    figures, _ = look
    rows = _rows(("long_tail", "a", 40), ("long_tail", "b", 30),
                 ("normal", "c_tele", 1), ("normal", "d", 2))
    rows += [("can_wait", f"z{i}_zoom", "sp", 0.5, 100 + i) for i in range(16)]
    out = figures._look(rows, {"zoom": 19, "tele": 1}, 20)
    assert out["head_n"] == 2, "two frames is a tenth of twenty"
    # Ranks 1 and 2 are c_tele and d_zoom, whatever order the page lists them in.
    assert out["head_tele"] == 1
    assert out["head_tele_share"] == 0.5
    assert out["queue_tele_share"] == 0.05


def test_an_unranked_queue_publishes_no_share_of_its_head(look, queues):
    """With no ordering file every frame ties, so there is no head to report."""
    figures, _ = look
    rows = _rows(("normal", "a_tele", queues.NO_NOVELTY))
    out = figures._look(rows, {"tele": 1}, 0)
    assert out["head_n"] == 0 and out["head_tele_share"] is None


# ---------------------------------------------------------------------------
# the contact sheet
# ---------------------------------------------------------------------------

def _write_thumb(figures, stem):
    """The smallest thing that is a JPEG file. Nothing here opens it: the panel
    passes the bytes through, so what matters is that the bytes survive."""
    os.makedirs(figures.hc.THUMB_DIR, exist_ok=True)
    key = f"{figures.hc.GT_KEY_PREFIX}{stem}"
    with open(os.path.join(figures.hc.THUMB_DIR, f"{key}.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xd9")


def test_a_frame_with_no_picture_is_dropped_not_drawn_as_a_gap(look):
    """The fetch is resumable, so a half-finished run is normal. It must shorten
    the sheet, never punch holes in it."""
    figures, _ = look
    _write_thumb(figures, "b_zoom")
    out = figures._look(_rows(("normal", "a", 1), ("normal", "b", 2)), {"zoom": 2}, 2)
    assert [stem for stem, _, _ in out["thumbs"]["normal"]] == ["b_zoom"]


def test_the_sheet_stops_at_the_count_the_page_asks_for(look, monkeypatch):
    figures, _ = look
    monkeypatch.setattr(figures.hc, "THUMBS_PER_QUEUE", 2)
    for i in range(4):
        _write_thumb(figures, f"s{i}_zoom")
    rows = _rows(*[("normal", f"s{i}", i + 1) for i in range(4)])
    out = figures._look(rows, {"zoom": 4}, 4)
    assert len(out["thumbs"]["normal"]) == 2


def test_the_picture_reaches_the_page_as_bytes_and_not_as_a_path(look):
    """The page is one file that fetches nothing. A src pointing at disk would
    be a picture that only renders on the machine that built it."""
    figures, _ = look
    _write_thumb(figures, "a_zoom")
    out = figures._look(_rows(("normal", "a", 1)), {"zoom": 1}, 1)
    _, _, uri = out["thumbs"]["normal"][0]
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff\xd9"


def test_summary_does_not_assert_the_finding_when_nothing_was_scored(look, queue_why_panels):
    """A closed panel stands alone, so its summary must not outrun its evidence."""
    figures, _ = look
    html = queue_why_panels.p_look(SimpleNamespace(**figures._look([], {}, 0)))
    assert "finds species faster" not in html
    assert "has not been scored on this checkout" in html


def test_the_wait_queue_gets_no_pictures(look):
    """The bottom queue is a record: nobody works it, so the page prints its
    count and the rule's grade instead of a sheet, and the builder reads no
    thumbnail for it."""
    figures, _ = look
    _write_thumb(figures, "w_zoom")
    _write_thumb(figures, "n_zoom")
    rows = _rows(("can_wait", "w", 1), ("normal", "n", 2))
    out = figures._look(rows, {"zoom": 2}, 2)
    assert "can_wait" not in out["thumbs"]
    assert [stem for stem, _, _ in out["thumbs"]["normal"]] == ["n_zoom"]


# ---------------------------------------------------------------------------
# the send-first table's "how new it looks" column
# ---------------------------------------------------------------------------

def test_the_send_preview_table_prints_three_decimals_and_blank_for_unranked(
        queue_panels):
    """``queue_rows`` carries ``how_new_it_looks`` as its last field: three
    decimals for a frame the ordering file scored, blank for one it never
    ranked. The table has to print exactly that, not "0.000" or "None"."""
    c = SimpleNamespace(
        queue_rows=[
            ("long_tail", "comb_a_zoom", "guessed sp", 0.5, 1, "0.421"),
            ("long_tail", "comb_b_zoom", "guessed sp", 0.3, None, ""),
        ],
        support={"guessed sp": 4},
        selection_audit=None)
    html = queue_panels.send_preview_table(c)
    assert "how new it looks" in html
    assert "0.421" in html
    # The unranked row's cell is empty, not "None" or a stray "0.000".
    assert "None" not in html and "0.000" not in html


def test_the_ungraded_note_pulls_the_audit_figure_and_degrades_without_one(
        queue_panels, selection_panels, tmp_path):
    """The note over the send-first table says what the audit measures, on
    the labelled frames, and what it does not, on this pool. Absent the audit
    file, it degrades to the plain "not measured" wording."""
    import json

    d = {"audit": {"h1_sustainability": {"pct_gain": 162.4, "ci_low": 138.9,
                                         "ci_high": 193.3, "wilcoxon_p": 0.0039},
                   "alpha": 0.05, "n_seeds": 8, "rounds": 20, "n_seeds_agreeing": 8,
                   "library_version": "0.9.0",
                   "embedding_sha256": "anchor-sha0123456789abcdef"},
         "efficiency": {"labels_saved_pct": 70.0, "challenger_rounds_to_match": 6.0,
                        "baseline_rounds": 20},
         "preflight": {"separability_pct": 81.8, "gain_on_ladder": False},
         "population": {"n_frames": 1719, "n_species": 155, "n_rare_species": 107,
                        "rare_threshold": 5},
         "params": {"k_per_round": 20, "seed_pool_size": 200},
         "run": {"extra": {"written": "2026-09-10"}}}
    p = tmp_path / "audit.json"
    p.write_text(json.dumps(d))
    c = SimpleNamespace(selection_audit=selection_panels.selection_audit(str(p)))
    note = queue_panels.ungraded_note(c)
    assert "What this order is measured against" in note
    assert "1,719 labelled frames that already carry a name" in note
    assert "70% fewer labels for the same rare species" in note
    assert "This pool is not: it carries no label yet" in note

    absent = queue_panels.ungraded_note(SimpleNamespace(selection_audit=None))
    assert "has not been measured yet" in absent


# ---------------------------------------------------------------------------
# the contact sheet's per-queue record
# ---------------------------------------------------------------------------

def _sheet_context(**overrides):
    """A context with just enough for `contact_sheet`: three working queues,
    a wait queue that never gets a sheet, and the counters `queue_record`
    reads. Held-out grading is empty, so `wait_record` falls back to
    `best["err"]`."""
    from collections import Counter
    base = dict(
        thumbs={"long_tail": [("a_zoom", "sp a", "data:image/jpeg;base64,x")],
                "low_conf_known": [], "normal": [("n_zoom", "sp n",
                                                   "data:image/jpeg;base64,y")]},
        queue_counts={"long_tail": 5, "low_conf_known": 2, "normal": 9, "can_wait": 3},
        lt_species=Counter({"sp a": 2, "sp b": 1}),
        held_wait={"n": 0, "n_frames": 0, "err": 0.0},
        best={"err": 0.1})
    base.update(overrides)
    return SimpleNamespace(**base)


def test_queue_record_gives_long_tail_a_species_count_and_the_others_none(
        queue_why_panels):
    """Only `long_tail` has a leak-free number to show: how many distinct
    species its own guesses name. The other working queues get the photo
    count and the link, and no invented figure."""
    c = _sheet_context()
    lt = queue_why_panels.queue_record(c, "long_tail")
    assert "5 photos are in this queue" in lt
    assert "2 distinct species show up in these guesses" in lt
    assert "send_first_queue.csv" in lt

    normal = queue_why_panels.queue_record(c, "normal")
    assert "9 photos are in this queue" in normal
    assert "distinct species" not in normal
    assert "send_first_queue.csv" in normal


def test_contact_sheet_puts_the_caption_before_the_first_queue_heading(
        queue_why_panels):
    """A reader must meet the explanation of the crops before the crops, not
    after the last strip."""
    c = _sheet_context()
    html = queue_why_panels.contact_sheet(c)
    caption_at = html.index("What you are looking at")
    first_heading_at = html.index("<h3")
    assert caption_at < first_heading_at


def test_contact_sheet_says_so_when_a_working_queue_has_no_cached_thumbs(
        queue_why_panels):
    """`low_conf_known` has no thumbs in this context. The record still
    prints; the missing sheet says so instead of leaving a heading with
    nothing under it."""
    c = _sheet_context()
    html = queue_why_panels.contact_sheet(c)
    assert "No thumbnails are cached for this queue yet." in html
    assert "2 photos are in this queue" in html


def test_contact_sheet_keeps_crops_for_working_queues_but_not_the_wait_queue(
        queue_why_panels):
    c = _sheet_context()
    html = queue_why_panels.contact_sheet(c)
    assert html.count('<div class="sheet">') == 2  # long_tail and normal have shots
    assert "3 photos wait here" in html  # the wait queue's record, no sheet
