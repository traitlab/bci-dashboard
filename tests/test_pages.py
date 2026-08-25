"""The two page builders, end to end: build a real page, assert invariants.

Nothing exercised `build_full.py`, `build_simple.py`, `build_export_only.py`,
`assets.py` or `explain.py` before this file, so every cleanup pass over them
had to be verified by hand-diffing 185KB of HTML. Golden-file comparison would
just move that problem into the test (any legitimate number change breaks it),
so this asserts structure instead: the build's own snapshot cross-check
passed, the page is one self-contained file, every id the inline JS looks up
by `getElementById` exists exactly once, tags balance, the species table has
one row per scored species and every row's status has a matching legend
entry, and there is no template residue from a forgotten `.substitute()` or
an unformatted placeholder.

Both builders run as a subprocess against `--verify-against
snapshots/model-health-2026-08-24`, the same gate `bin/refresh.sh` runs, so a
non-zero exit here means the page actually disagreed with the measurement,
not just that this test's assumptions are stale.

    .venv/bin/pytest tests/test_pages.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard"
SNAPSHOT_DIR = REPO / "snapshots" / "model-health-2026-08-24"
GT_CSV = REPO / "data" / "gt_dominant_taxon.csv"
SPLITS_CSV = REPO / "data" / "splits.csv"
CACHE_DIR = REPO / "data" / "predictions" / "cache"

# A fixed generation string, like the worktree byte-diff checks use: real
# dates would make two builds of the same code differ for no reason a test
# should care about.
_GENERATED = "2026-08-25-test"

_GETELEMENTBYID = re.compile(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)")
_ID_ATTR = re.compile(r"""\bid=['"]([^'"]+)['"]""")
_SCRIPT_BODY = re.compile(r"<script>(.*)</script>", re.S)
_LEGEND = re.compile(r'<ul class="status-legend">.*?</ul>', re.S)
_TAG_LABEL = re.compile(r'<span class="tag [^"]*"[^>]*>([^<]*)</span>')
_ROW = re.compile(r"<tr data-species=.*?</tr>", re.S)


def _require_buildable():
    """Skip on a fresh clone: the builders need measurement inputs and a
    snapshot to verify against, neither of which is tracked in git."""
    for path, label in ((GT_CSV, "data/gt_dominant_taxon.csv"),
                        (SPLITS_CSV, "data/splits.csv"),
                        (CACHE_DIR, "data/predictions/cache")):
        if not path.exists():
            pytest.skip(f"{label} not present (fresh clone)")
    if not SNAPSHOT_DIR.exists():
        pytest.skip("snapshots/model-health-2026-08-24 not present (fresh clone)")


def _build(tmp_path_factory, script: str, out_name: str) -> tuple[str, str]:
    """Run a builder as a real subprocess, the way `bin/refresh.sh` does.

    Returns (page_html, stdout). Raises via `assert` on a non-zero exit so
    the failure message carries the process's own stderr (a `VERIFY FAIL:
    ...` line from `history.verify_snapshot`, or a traceback).
    """
    out = tmp_path_factory.mktemp("page") / out_name
    proc = subprocess.run(
        [sys.executable, str(DASHBOARD / script),
         "--out", str(out), "--verify-against", str(SNAPSHOT_DIR),
         "--generated", _GENERATED],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, (
        f"{script} exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return out.read_text(encoding="utf-8"), proc.stdout


@pytest.fixture(scope="session")
def full_page(tmp_path_factory):
    _require_buildable()
    return _build(tmp_path_factory, "build_full.py", "model_health_dashboard.html")


@pytest.fixture(scope="session")
def simple_page(tmp_path_factory):
    _require_buildable()
    return _build(tmp_path_factory, "build_simple.py", "simple_dashboard.html")


@pytest.fixture(scope="session")
def n_species():
    """Independent of both builders: the population size the snapshot's own
    measurement recorded, so this doesn't drift if a builder's row count
    logic breaks in a way that happens to agree with itself."""
    import csv
    with open(SNAPSHOT_DIR / "per_species_health.csv", newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


@pytest.fixture(params=["full_page", "simple_page"])
def page(request):
    """Runs every shared assertion against both pages without writing it twice."""
    html, stdout = request.getfixturevalue(request.param)
    return html, stdout


# ---------------------------------------------------------------------------
# The build itself
# ---------------------------------------------------------------------------

def test_build_verifies_clean_against_the_snapshot(page):
    html, stdout = page
    verified = [line for line in stdout.splitlines() if "verified" in line]
    assert verified, "build printed no verify lines -- verify_snapshot did not run"
    assert "VERIFY FAIL" not in stdout


# ---------------------------------------------------------------------------
# Self-contained
# ---------------------------------------------------------------------------

def test_page_has_no_external_asset_references(page):
    html, _ = page
    assert "<link" not in html
    assert "script src" not in html
    assert "http://" not in html
    assert "https://" not in html


# ---------------------------------------------------------------------------
# JS <-> HTML id coupling: derived from the JS text, not hardcoded here
# ---------------------------------------------------------------------------

def test_every_id_the_js_looks_up_exists_exactly_once(page):
    html, _ = page
    script = _SCRIPT_BODY.search(html)
    assert script, "no inline <script> block -- JS was not embedded"
    ids = _GETELEMENTBYID.findall(script.group(1))
    assert ids, "no getElementById calls found in the inline script"
    counts = {}
    for m in _ID_ATTR.finditer(html):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    for eid in ids:
        assert counts.get(eid, 0) == 1, (
            f"id {eid!r} (looked up by the inline JS) appears {counts.get(eid, 0)} "
            f"times in the page, not once")


# ---------------------------------------------------------------------------
# Tag balance
# ---------------------------------------------------------------------------

def test_tags_balance(page):
    html, _ = page
    assert html.count("<details") == html.count("</details>")
    assert len(re.findall(r"<table\b", html)) == html.count("</table>")
    assert len(re.findall(r"<section\b", html)) == html.count("</section>")
    assert len(re.findall(r"<tr[ >]", html)) == html.count("</tr>")


# ---------------------------------------------------------------------------
# Species table: one row per scored species, every status explained
# ---------------------------------------------------------------------------

def test_one_species_row_per_scored_species(page, n_species):
    html, _ = page
    rows = re.findall(r"<tr data-species=", html)
    assert len(rows) == n_species


def test_every_row_status_has_a_matching_legend_entry(page):
    html, _ = page
    legend = _LEGEND.search(html)
    assert legend, "no <ul class=\"status-legend\"> block -- legend was not rendered"
    legend_start = legend.start()
    # Not the first <table> in the page -- panels earlier in the document
    # (e.g. threshold_card) have tables of their own. The species table is
    # the one the filter JS looks up by id.
    table_start = min(i for i in (html.find("id='species-table'"),
                                  html.find('id="species-table"')) if i >= 0)
    assert legend_start < table_start, "legend does not sit above the species table"

    legend_labels = set(_TAG_LABEL.findall(legend.group()))
    assert legend_labels, "legend block has no status labels in it"

    row_labels = set()
    for row in _ROW.findall(html):
        found = _TAG_LABEL.findall(row)
        assert found, "a species row has no status tag"
        row_labels.update(found)

    missing = row_labels - legend_labels
    assert not missing, f"row status labels with no legend entry: {missing}"


# ---------------------------------------------------------------------------
# Template residue: a forgotten .substitute() or an unformatted placeholder
# ---------------------------------------------------------------------------

def test_no_unrendered_template_residue(page):
    html, _ = page
    assert "object at 0x" not in html, "a repr() leaked in (e.g. an un-substituted Template)"
    for placeholder in ("$table_id", "$input_id", "$select_id", "$count_id"):
        assert placeholder not in html, f"Template placeholder {placeholder!r} was not substituted"
    assert not re.search(r"\bNone\b", html)
    assert not re.search(r"\bnan\b", html, re.IGNORECASE)


# ---------------------------------------------------------------------------
# the send-first list
# ---------------------------------------------------------------------------
def test_the_rendered_queue_matches_the_file_it_points_at(full_page):
    """The page prints the head of send_first_queue.csv and tells the reader to
    open that file for the rest. A different sort in either place would hand a
    botanist two orders and no way to tell which one to work."""
    import csv

    html, _ = full_page
    with open(SNAPSHOT_DIR / "send_first_queue.csv", newline="", encoding="utf-8") as f:
        expected = [r["global_key"] for r in csv.DictReader(f)]
    shown = re.findall(r'<code class="key">([^<]+)</code>', html)
    assert shown, "the send-first panel renders no photo keys"
    # The CSV keys carry the GT prefix the page strips for display, so the
    # rendered key is the tail of the CSV's rather than equal to it.
    assert all(e.endswith(s) for e, s in zip(expected, shown)), (
        f"rendered order differs from the CSV: {shown[:3]} against {expected[:3]}")


def test_the_camera_note_counts_the_frames_it_describes(full_page):
    """The note names a camera split read off the frame keys. If the keys stop
    naming a camera the build aborts, so this checks the number that survived
    is the number of keys actually rendered as tele."""
    html, _ = full_page
    m = re.search(r"(\d[\d,]*) of the ([\d,]*) photos in this queue \(([\d.]+)%\) are tele",
                  html)
    assert m, "the camera note is not on the page"
    tele = int(m.group(1).replace(",", ""))
    pool = int(m.group(2).replace(",", ""))
    pct = float(m.group(3))
    assert 0 < tele < pool
    assert abs(100 * tele / pool - pct) < 0.05
    # The note says the scored population is all zoom. If a tele key ever reaches
    # the scored table the sentence beside it becomes false, so check the claim
    # rather than only the arithmetic.
    assert "Every crown scored on this page was shot with the zoom lens" in html


# ---------------------------------------------------------------------------
# anchors and jump lists
# ---------------------------------------------------------------------------
# These five gate behaviour shipped in fcb0aec (panel anchors, per-section jump
# lists, the table scroll wrapper) and in af4b521 (the status legend). They are
# assertions about the page, not about either builder's internals, so they run
# against both pages like everything above.

def test_every_link_into_the_page_lands_on_something(page):
    """The jump lists are generated from the panels, so a broken one means the
    two have drifted apart."""
    html, _ = page
    targets = set(_ID_ATTR.findall(html))
    for href in set(re.findall(r'href="#([^"]+)"', html)):
        assert href in targets, f"jump link #{href} has no target"


def test_no_anchor_carries_a_number(page):
    """An id built from a summary that states a live count changes on the next
    snapshot, and every saved link to it breaks. `panel()` rejects those, so
    this is the assertion that the guard is actually wired up."""
    html, _ = page
    for eid in re.findall(r'<details class="panel" id="([^"]+)"', html):
        assert not any(c.isdigit() for c in eid), f"anchor {eid!r} carries a number"


def test_each_id_is_unique(page):
    html, _ = page
    ids = _ID_ATTR.findall(html)
    duplicated = {i for i in ids if ids.count(i) > 1}
    assert not duplicated, f"duplicate ids: {sorted(duplicated)}"


def test_a_wide_table_scrolls_inside_its_own_box(page):
    """Without the wrapper the widest table sets the page width and every
    paragraph scrolls sideways with it on a phone."""
    html, _ = page
    assert len(re.findall(r"<table\b", html)) == html.count('class="tscroll"')


def test_the_filter_can_reach_every_row(page):
    """The filter reads data-species and data-status. A row missing either is
    invisible to it, which reads as a table that loses rows when you type."""
    html, _ = page
    tagged = [r for r in re.findall(r"<tr\b[^>]*>", html) if "data-species=" in r]
    assert tagged, "no filterable rows"
    for row in tagged:
        assert "data-status=" in row, f"row filterable by name but not status: {row}"
