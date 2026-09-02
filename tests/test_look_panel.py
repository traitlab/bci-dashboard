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


def test_the_panel_says_so_when_there_is_nothing_to_draw(queue_panels):
    """A panel that renders nothing reads as a bug. This one says which script
    writes the files it is missing."""
    out = queue_panels.NO_CURVES
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


def test_summary_does_not_assert_the_finding_when_nothing_was_scored(look, queue_panels):
    """A closed panel stands alone, so its summary must not outrun its evidence."""
    figures, _ = look
    html = queue_panels.p_look(SimpleNamespace(**figures._look([], {}, 0)))
    assert "finds species faster" not in html
    assert "has not been scored on this checkout" in html
