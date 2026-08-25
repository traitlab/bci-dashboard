"""What must hold of a built page, whatever the numbers on it say.

Nothing tested the builders, so every cleanup pass had to be verified by
hand-diffing 185KB of HTML against a build from the previous commit. These are
structural assertions, not golden files: they stay green when a number moves
and go red when the page breaks. The build's own `--verify-against` gate
already covers whether the numbers agree with the measurement.

Both pages are built once per session, so the cost is two builds, not two per
test.

    .venv/bin/pytest tests/test_pages.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOTS = REPO / "snapshots"


def _latest_snapshot() -> pathlib.Path | None:
    dated = sorted(SNAPSHOTS.glob("model-health-20*"))
    return dated[-1] if dated else None


def _build(builder: str, tmp_path_factory) -> str:
    """Run one builder as a script and return the page it wrote.

    Through `subprocess` rather than an import: the builders are scripts with a
    `main()`, and running them the way `bin/refresh.sh` does is what the test is
    for. A non-zero exit or a failed `--verify-against` fails the test here.
    """
    snapshot = _latest_snapshot()
    if snapshot is None:
        pytest.skip(f"no snapshots/model-health-<date>/ to verify against ({SNAPSHOTS})")
    if not (REPO / "data" / "gt_dominant_taxon.csv").exists():
        pytest.skip("data/gt_dominant_taxon.csv not present")
    out = tmp_path_factory.mktemp("pages") / f"{builder}.html"
    proc = subprocess.run(
        [sys.executable, str(REPO / "dashboard" / f"{builder}.py"),
         "--out", str(out), "--verify-against", str(snapshot)],
        cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, f"{builder} exited {proc.returncode}:\n{proc.stderr}"
    assert "MISMATCH" not in proc.stdout, proc.stdout
    return out.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def full(tmp_path_factory):
    return _build("build_full", tmp_path_factory)


@pytest.fixture(scope="session")
def simple(tmp_path_factory):
    return _build("build_simple", tmp_path_factory)


@pytest.fixture(params=["full", "simple"])
def page(request):
    """Each invariant below runs against both pages."""
    return request.getfixturevalue(request.param)


# ---------------------------------------------------------------------------
# self-contained
# ---------------------------------------------------------------------------
def test_the_page_pulls_nothing_over_the_network(page):
    """A page is opened from a laptop with no network and no credential, so
    every byte it needs has to already be in the file."""
    for pattern in (r"<script[^>]+\bsrc=", r"<link\b", r"<img[^>]+\bsrc=",
                    r"https?://[^\"']+\.(?:css|js|woff2?|png|jpe?g|svg)"):
        assert not re.search(pattern, page), f"external reference: {pattern}"


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tag", ["details", "table", "tr", "section", "ul", "svg"])
def test_every_element_that_opens_also_closes(page, tag):
    """A page is one long string built by concatenation, so an unbalanced tag
    is the failure mode: the browser recovers silently and swallows whatever
    came after it."""
    opened = len(re.findall(rf"<{tag}[\s>]", page))
    closed = page.count(f"</{tag}>")
    assert opened == closed, f"{opened} <{tag}> against {closed} </{tag}>"


def test_the_script_finds_every_element_it_looks_up(page):
    """Derived from the JS text, not a hardcoded list: the sort/filter strip
    silently does nothing when an id it queries is not in the document, which
    is what a renamed id looks like from the reader's side."""
    wanted = set(re.findall(r"getElementById\('([^']+)'\)", page))
    assert wanted, "no getElementById calls found; has the JS moved?"
    for eid in wanted:
        found = len(re.findall(rf"""\bid=['"]{re.escape(eid)}['"]""", page))
        assert found == 1, f"id {eid!r} appears {found} times in the document"


def test_every_link_into_the_page_lands_on_something(page):
    """The jump lists are generated from the panels, so a broken one means the
    two have drifted apart."""
    targets = set(re.findall(r"""\bid=['"]([^'"]+)['"]""", page))
    for href in set(re.findall(r'href="#([^"]+)"', page)):
        assert href in targets, f"jump link #{href} has no target"


def test_no_anchor_carries_a_number(page):
    """An id built from a summary that states a live count changes on the next
    snapshot, and every saved link to it breaks. panel() rejects those, so this
    is the assertion that the guard is actually wired up."""
    for eid in re.findall(r'<details class="panel" id="([^"]+)"', page):
        assert not any(c.isdigit() for c in eid), f"anchor {eid!r} carries a number"


def test_each_panel_id_is_unique(page):
    ids = re.findall(r"""\bid=['"]([^'"]+)['"]""", page)
    duplicated = {i for i in ids if ids.count(i) > 1}
    assert not duplicated, f"duplicate ids: {sorted(duplicated)}"


def test_a_wide_table_scrolls_inside_its_own_box(page):
    """Without the wrapper the widest table sets the page width and every
    paragraph scrolls sideways with it on a phone."""
    assert page.count('<table') == page.count('class="tscroll"')


# ---------------------------------------------------------------------------
# the species table
# ---------------------------------------------------------------------------
def test_every_species_row_states_its_status_in_words(page):
    """Status must not be carried by colour alone. The reasons live once in a
    legend, so the tag label on the row is what maps a row to its reason."""
    rows = re.findall(r'<tr data-species="[^"]*"[^>]*>(.*?)</tr>', page, re.S)
    assert rows, "no species rows"
    labels = set()
    for row in rows:
        tags = re.findall(r'<span class="tag [a-z]+"[^>]*>([^<]+)</span>', row)
        assert len(tags) == 1, f"row carries {len(tags)} status tags"
        labels.add(tags[0])
    legend = re.search(r'<ul class="status-legend">.*?</ul>', page, re.S)
    assert legend, "species table has no status legend"
    explained = set(re.findall(r'<span class="tag [a-z]+">([^<]+)</span>', legend.group(0)))
    assert labels <= explained, f"rows use tags the legend never explains: {labels - explained}"
    assert explained <= labels, f"legend explains tags no row draws: {explained - labels}"


def test_the_filter_can_reach_every_row(page):
    """The filter reads data-species and data-status. A row missing either is
    invisible to it, which reads as a table that loses rows when you type."""
    rows = re.findall(r"<tr\b[^>]*>", page)
    tagged = [r for r in rows if "data-species=" in r]
    assert tagged, "no filterable rows"
    for row in tagged:
        assert "data-status=" in row, f"row filterable by name but not status: {row}"


# ---------------------------------------------------------------------------
# nothing half-rendered
# ---------------------------------------------------------------------------
# Matched on word boundaries: a species called Tynanthus contains "nan", and a
# substring search reports the botanist's name as a formatting bug.
@pytest.mark.parametrize("residue", [r"\bNone\b", r"\bnan\b", r"Template object at",
                                     r"\{\}", r"n/a%"])
def test_no_value_reached_the_page_unrendered(page, residue):
    """A None or a bare format placeholder in the visible text is a formatting
    path that was never exercised, not a number the reader can act on."""
    visible = re.sub(r"<(script|style|svg)\b.*?</\1>", "", page, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    found = re.search(residue, visible)
    assert not found, f"{residue} rendered into the page text: {visible[max(0, found.start() - 60):found.end() + 60]!r}"
