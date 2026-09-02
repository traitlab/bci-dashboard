"""Every page builder, end to end: build a real page, assert invariants.

Nothing exercised `build_external.py` or `build_internal.py` before this file,
so every cleanup pass over them had to be verified by hand-diffing 185KB of
HTML. `assets.py` is exercised by `test_assets.py`; the page-shape invariants
below run against both pages.
Golden-file comparison would just move that problem into the test (any
legitimate number change breaks it), so this asserts structure instead: the
build's own snapshot cross-check passed, the page is one self-contained file,
every id the inline JS looks up exists exactly once, tags balance, the species
table has one row per scored species and every row's status has a matching
legend entry, and there is no template residue from a forgotten `.substitute()`
or an unformatted placeholder.

Since the 2026-08-27 split the pages no longer all carry the same panels, so
each one declares what it holds in `PAGES` and the assertions that are about a
panel read that allowlist. An assertion is never skipped for a page that lacks
the panel: it flips to the opposite claim, that the page carries *none* of that
panel's machinery. A page holding half of it -- a filter input with no table,
say -- fails both ways, which is the failure this file exists to catch.

Every builder runs as a subprocess against `--verify-against` the newest
snapshot, the same gate `bin/refresh.sh` runs and picked the same way, so a
non-zero exit here means the page actually disagreed with the measurement, not
just that this test's assumptions are stale.

    .venv/bin/pytest tests/test_pages.py
"""

from __future__ import annotations

import pathlib
import re

import pytest
from conftest import SNAPSHOT_DIR, species_rows
# The frame list is the one file that says how many field sites there are, and
# reading it lives with the other checks that hold a number to its source.
from test_shared_constants import frame_list_sites

REPO = pathlib.Path(__file__).resolve().parents[1]

_LEGEND = re.compile(r'<ul class="status-legend">.*?</ul>', re.S)
_TAG_LABEL = re.compile(r'<span class="tag [^"]*"[^>]*>([^<]*)</span>')


def test_no_page_shows_interval_notation(page):
    """"[0.7,0.8)" is how the CSVs name a confidence band and it is a
    convention a botanist has no reason to know: the half-open bracket is the
    part that carries the meaning. A page says "0.7 to 0.8". CONTEXT.md."""
    html, _, _ = page
    found = re.findall(r"\[\d[\d.]*,\s*\d[\d.]*\)", html)
    assert not found, f"interval notation on the page: {sorted(set(found))}"


@pytest.fixture(scope="session")
def n_species():
    """Independent of every builder: the population size the snapshot's own
    measurement recorded, so this doesn't drift if a builder's row count
    logic breaks in a way that happens to agree with itself."""
    import csv
    with open(SNAPSHOT_DIR / "per_species_health.csv", newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))



# ---------------------------------------------------------------------------
# The build itself
# ---------------------------------------------------------------------------

def test_build_verifies_clean_against_the_snapshot(page):
    _, stdout, carries = page
    verified = [line for line in stdout.splitlines() if "verified" in line]
    if "snapshot" not in carries:
        # The export page reconciles against no snapshot -- it is scoped to
        # one Labelbox export -- and write_page prints a verify line only per
        # check in the list it is handed, so an empty list means no lines.
        assert not verified, (
            "page carries no snapshot to reconcile against but printed a verify line")
        assert "VERIFY FAIL" not in stdout
        return
    assert verified, "build printed no verify lines -- verify_snapshot did not run"
    assert "VERIFY FAIL" not in stdout


def test_a_page_gates_on_exactly_the_send_queue_it_reports(page):
    """The split's load-bearing claim. The external page must build without the
    send-queue CSVs being consistent, because it says nothing about them; the
    other two must not, because they both print queue counts."""
    _, stdout, carries = page
    gated = "send_first_queue.csv" in stdout and "send_batches.csv" in stdout
    assert gated == ("queue_counts" in carries), (
        f"page gates on the send queue: {gated}, "
        f"reports it: {'queue_counts' in carries}")


# ---------------------------------------------------------------------------
# Self-contained
# ---------------------------------------------------------------------------

def test_page_has_no_external_asset_references(page):
    """Nothing the page *loads* may come from off the machine.

    An ``href`` on an anchor is not a load: the review rows deep-link into
    Labelbox so a botanist can open the frame they are being asked about, and
    the reader clicks it or does not. What is banned is a URL the browser
    fetches on its own -- a stylesheet, a script, an image, an iframe -- since
    that would make the page stop rendering correctly offline.
    """
    html, _, _ = page
    assert "<link" not in html
    assert "script src" not in html
    fetched = re.findall(r'(?:src|srcset|@import\s+url\()\s*=?\s*["\'(]?(https?://[^"\'\s)]+)', html)
    assert not fetched, f"page fetches off-machine assets: {fetched[:3]}"
    anchors = set(re.findall(r'<a\s[^>]*href="(https?://[^"]+)"', html))
    assert all(u.startswith("https://app.labelbox.com/projects/") for u in anchors), (
        f"unexpected outbound link: {sorted(anchors)[:3]}")


# ---------------------------------------------------------------------------
# Tag balance
# ---------------------------------------------------------------------------

def test_tags_balance(page):
    html, _, _ = page
    assert html.count("<details") == html.count("</details>")
    assert len(re.findall(r"<table\b", html)) == html.count("</table>")
    assert len(re.findall(r"<section\b", html)) == html.count("</section>")
    assert len(re.findall(r"<tr[ >]", html)) == html.count("</tr>")


# ---------------------------------------------------------------------------
# What a reader sees before clicking anything
# ---------------------------------------------------------------------------

def test_a_page_opens_only_the_panels_that_are_its_deliverable(page):
    """A panel is open only where it is the thing the page exists to hand over.

    The queue page opens the two a labeller works from. The model-health page
    opens none: its answer is the two hero cards, and the species table is a
    lookup tool. Open, that table was 40% of the page's words sitting fourth of
    nine, and the five panels below it were a scroll nobody made.
    """
    expected = {
        "model_health": [],
        "label_queue": ["Where to spend botanist time next",
                        "What to send to the botanist first"],
    }
    html, name, _ = page
    want = next(v for k, v in expected.items() if k in name)
    opened = [re.sub(r"<[^>]+>", "", o).strip() for o in re.findall(
        r"<details[^>]*\bopen\b[^>]*>\s*<summary[^>]*>(.*?)</summary>", html, re.S)]
    assert len(opened) == len(want), f"{name} opens {opened}, expected {want}"
    for got, prefix in zip(opened, want):
        assert got.startswith(prefix), f"{name}: {got!r} does not start {prefix!r}"


# ---------------------------------------------------------------------------
# Species table: one row per scored species, every status explained
# ---------------------------------------------------------------------------

def test_one_species_row_per_scored_species(page, n_species):
    html, _, carries = page
    rows = species_rows(html)
    if "species_status" not in carries:
        assert not rows
    elif "snapshot" in carries:
        # The two corpus pages score every species in the cumulative record.
        assert len(rows) == n_species
    else:
        # The export page scores only what its own export labels, which is a
        # smaller set by design. What matters is that every row it does render
        # carries a status the legend explains.
        assert rows


def test_the_hidden_rows_are_the_ones_the_prose_says_they_are(page, panels, core):
    """The count in the prose, the marked rows and the threshold agree.

    Three things can drift apart: the sentence naming how many species start
    hidden, the ``data-thin`` attributes the JS filters on, and the cut-off in
    ``panels.THIN_MIN_FRAMES``. A reader who unticks the box and counts is
    entitled to find the number the page gave them.
    """
    html, _, carries = page
    marked = re.findall(r'<tr [^>]*data-thin="1"', html)
    if "species_thin" not in carries:
        assert not marked, "page ships no show-all checkbox but hides rows anyway"
        return
    said = re.search(r"<b>(\d+) of these (\d+) species start hidden\.</b>", html)
    assert said, "no sentence saying how many species start hidden"
    assert len(marked) == int(said.group(1)), (
        f"prose says {said.group(1)} species start hidden, "
        f"{len(marked)} rows carry data-thin")
    assert 0 < len(marked) < int(said.group(2)), (
        "every row hidden, or none: the checkbox would have nothing to do")
    # The threshold is stated in the same sentence, so it cannot quietly become
    # a second number beside the status column's own cut-off.
    assert f"fewer than {panels.THIN_MIN_FRAMES} labelled frames" in html
    assert panels.THIN_MIN_FRAMES == core.WELL_SAMPLED_MIN_N


def test_every_row_status_has_a_matching_legend_entry(page):
    """A status tag on a row with no legend entry above it is a colour the
    reader has to guess the meaning of, which is the whole thing a legend is
    there to prevent."""
    html, _, carries = page
    legend = _LEGEND.search(html)
    if "species_status" not in carries:
        assert legend is None, "page carries no species status legend but renders it"
        assert not species_rows(html), "page carries no species status legend but renders its rows"
        return
    assert legend, "no <ul class=\"status-legend\"> block -- legend was not rendered"
    legend_start = legend.start()
    # Not the first <table> in the page -- panels earlier in the document
    # have tables of their own. The species table is the one the filter JS
    # looks up by id.
    table_start = min(i for i in (html.find("id='species-table'"),
                                  html.find('id="species-table"')) if i >= 0)
    assert legend_start < table_start, "legend does not sit above the species table"

    legend_labels = set(_TAG_LABEL.findall(legend.group()))
    assert legend_labels, "legend block has no status labels in it"

    row_labels = set()
    for row in species_rows(html):
        found = _TAG_LABEL.findall(row)
        assert found, "a species row has no status tag"
        row_labels.update(found)

    missing = row_labels - legend_labels
    assert not missing, f"row status labels with no legend entry: {missing}"


# ---------------------------------------------------------------------------
# The frozen read, now published as one correction on the corpus rates
# ---------------------------------------------------------------------------

def test_the_floor_correction_matches_the_frozen_result_file(page):
    """The page must print the gap the scorer wrote, not a gap of its own.

    Nothing recomputes this at build time on purpose -- the stopping rule says
    the read happens once on the complete set -- so the only thing standing
    between the file and the page is the formatting, and that is what this
    checks. The page publishes the paired gap and not the level it came from:
    A2 attaches the already-seen caveat to the crown arm's own accuracy and
    says the paired comparison does not carry it.
    """
    import csv

    html, _, carries = page
    with open(REPO / "input" / "confirmatory_result_2026-08.csv",
              newline="", encoding="utf-8") as f:
        cf = {r["key"]: r["value"] for r in csv.DictReader(f)}
    gap = f'{100 * float(cf["crown_minus_photo"]):+.1f} points'
    if "floor" not in carries:
        assert gap not in html, (
            "a page that does not carry the frozen read prints its correction anyway")
        return
    assert gap in html, f"page does not print the floor correction: {gap}"
    # Population, per CLAUDE.md: a rate alone is not publishable.
    assert f'{int(float(cf["n_frames"]))} frames' in html
    assert f'{int(float(cf["n_sites"]))} sites' in html
    lo = f'{100 * float(cf["crown_minus_photo_site_lo"]):+.1f}'
    hi = f'{100 * float(cf["crown_minus_photo_site_hi"]):+.1f}'
    assert f'between {lo} and {hi} points' in html, (
        "the gap is published without the range around it")


def test_the_level_the_gap_came_from_stays_off_the_page(page):
    """87.3% is not reproducible without a botanist's outlines, and it carries
    the A2 already-seen caveat that the gap does not. Publishing it here would
    drag that caveat back onto a page that no longer explains it."""
    import csv

    html, _, carries = page
    if "floor" not in carries:
        return
    with open(REPO / "input" / "confirmatory_result_2026-08.csv",
              newline="", encoding="utf-8") as f:
        cf = {r["key"]: r["value"] for r in csv.DictReader(f)}
    level = f'{100 * float(cf["crown_top1"]):.1f}%'
    assert level not in html, (
        f"the page prints {level}, the crown-by-crown level. That number carries the "
        f"already-seen caveat and belongs in bci-dashboard-docs/metrics.md, not here.")


METRICS = REPO.parent / "bci-dashboard-docs" / "metrics.md"


def test_the_two_caveats_the_design_requires_live_in_the_writeup(page):
    """Both amendments in hypothesis.md say the writeup must carry their words
    rather than a summary. The writeup is metrics.md, not this page: the page
    publishes a correction and cites the read behind it. So the obligation is
    checked where it now lives, and the page is checked for not carrying a
    number that would re-incur it."""
    if not METRICS.exists():
        pytest.skip("sibling bci-dashboard-docs/metrics.md not present")
    doc = METRICS.read_text(encoding="utf-8")
    verbatim = (
        "But the number was not generated blind.",
        "What this costs, stated plainly.",
    )
    for quote in verbatim:
        assert quote in doc, (
            f"hypothesis.md requires the writeup to carry {quote[:40]!r} in its own "
            f"words, and bci-dashboard-docs/metrics.md no longer does")


HYPOTHESIS = REPO.parent / "bci-dashboard-docs" / "hypothesis.md"


def test_the_writeup_still_quotes_the_design_document_verbatim(external_page):
    """The two amendments are reproduced in metrics.md, so nothing links them to
    hypothesis.md except this test. Both require their words rather than a
    summary, which makes a silent paraphrase a design violation and not just a
    typo. It was the page that carried them until the page was reduced to the
    correction; the obligation moved, the check moved with it.

    ``external_page`` is taken so the anchor assertion below runs on a built
    page: the panel id predates this panel and saved links point at it.
    """
    if not HYPOTHESIS.exists() or not METRICS.exists():
        pytest.skip("sibling bci-dashboard-docs not present")
    doc = HYPOTHESIS.read_text(encoding="utf-8")
    # metrics.md carries the blocks as markdown quotes, so the quote marker and
    # the list bullets are normalised away on both sides before comparing. The
    # words are what the design requires; the formatting around them is not.
    shown = METRICS.read_text(encoding="utf-8").replace("**", "")
    shown = re.sub(r"^>[ \t]?", "", shown, flags=re.MULTILINE)
    shown = re.sub(r"\s+", " ", shown.replace("- ", ""))

    def block(first, last):
        i = doc.index(first)
        j = doc.index(last, i) + len(last)
        # Markdown bold and list bullets are formatting, not words.
        return re.sub(r"\s+", " ", doc[i:j].replace("**", "").replace("- ", "")).strip()

    for quote in (block("What that does and does not undermine:",
                        "The paired comparison and the tiles arm do not."),
                  block("**What this costs, stated plainly.**",
                        "must carry this paragraph, not a summary of it.")):
        assert quote in shown, (
            f"bci-dashboard-docs/metrics.md no longer quotes hypothesis.md verbatim; "
            f"it diverges near {quote[:80]!r}")

    html, _ = external_page
    assert 'id="where-the-headline-comes-from"' in html, (
        "the anchor saved links point at is gone; it belongs on the panel that "
        "explains where the floor correction comes from")


# ---------------------------------------------------------------------------
# Template residue: a forgotten .substitute() or an unformatted placeholder
# ---------------------------------------------------------------------------

def test_no_unrendered_template_residue(page):
    html, _, _ = page
    assert "object at 0x" not in html, "a repr() leaked in (e.g. an un-substituted Template)"
    for placeholder in ("$table_id", "$input_id", "$select_id", "$count_id"):
        assert placeholder not in html, f"Template placeholder {placeholder!r} was not substituted"
    assert not re.search(r"\bNone\b", html)
    assert not re.search(r"\bnan\b", html, re.IGNORECASE)


# ---------------------------------------------------------------------------
# the send-first list
# ---------------------------------------------------------------------------
def test_the_rendered_queue_matches_the_file_it_points_at(internal_page):
    """The page prints the head of send_first_queue.csv and tells the reader to
    open that file for the rest. A different sort in either place would hand a
    botanist two orders and no way to tell which one to work."""
    import csv

    html, _ = internal_page
    with open(SNAPSHOT_DIR / "send_first_queue.csv", newline="", encoding="utf-8") as f:
        expected = [r["global_key"] for r in csv.DictReader(f)]
    shown = re.findall(r'<code class="key">([^<]+)</code>', html)
    assert shown, "the send-first panel renders no photo keys"
    # The CSV keys carry the GT prefix the page strips for display, so the
    # rendered key is the tail of the CSV's rather than equal to it.
    assert all(e.endswith(s) for e, s in zip(expected, shown)), (
        f"rendered order differs from the CSV: {shown[:3]} against {expected[:3]}")


def test_the_camera_note_counts_the_frames_it_describes(internal_page, panels):
    """The note names a camera split read off the frame keys. If the keys stop
    naming a camera the build aborts, so this checks the number that survived
    is the number of keys actually rendered as tele."""
    html, _ = internal_page
    m = re.search(r"They are (\d[\d,]*) of the queue \(([\d.]+)%\)", html)
    assert m, "the camera note is not on the page"
    tele = int(m.group(1).replace(",", ""))
    # The denominator is no longer printed beside the share, so take it from the
    # file the panel ranks: the queue is every row of it.
    import csv

    with open(SNAPSHOT_DIR / "send_first_queue.csv", newline="", encoding="utf-8") as f:
        pool = sum(1 for _ in csv.DictReader(f))
    pct = float(m.group(2))
    assert 0 < tele < pool
    assert abs(100 * tele / pool - pct) < 0.05
    # The note says the scored population is all zoom. If a tele key ever reaches
    # the scored table the sentence beside it becomes false, so check the claim
    # rather than only the arithmetic.
    assert f"No botanist has labelled a frame from {panels.CAMERA_IS['tele']}" in html


def test_only_the_internal_page_renders_the_queue(page):
    """The split moved the send-first list off the page that leaves the lab. A
    queue key reappearing there is the split silently coming undone."""
    html, _, carries = page
    keys = re.findall(r'<code class="key">([^<]+)</code>', html)
    assert bool(keys) == ("queue_keys" in carries), (
        f"page renders {len(keys)} queue keys but carries the list: "
        f"{'queue_keys' in carries}")


def test_the_crop_mismatch_note_says_half_only_while_the_gate_means_half(
        external_page, core):
    """The note counts frames on the wrong side of `core.MIN_CROP_COVERAGE` and
    calls that "less than half the crop". The count follows the constant; the
    word does not, so moving the gate off 0.50 has to move the wording too.

    The model-health page prints it once, under the four corpus rates. It used
    to print the same sentence again under the species table, where what a
    reader needs is not the counts but what they mean for a row."""
    html, _ = external_page
    assert html.count("covers less than half the crop") == 1, (
        "the note is gone, reworded, or back to being said twice")
    assert core.MIN_CROP_COVERAGE == 0.50, (
        f"MIN_CROP_COVERAGE is {core.MIN_CROP_COVERAGE}, so the page's "
        f"'less than half the crop' names a line the gate no longer draws")



def test_a_page_styles_every_class_it_renders(page):
    """The stylesheet is trimmed to the rules a page has something to style, so
    the failure to guard against is a page that loses a rule it needed and
    comes out unstyled. `assets.css_for` is what does the trimming and
    `test_assets.py` holds it to the other direction, the bytes."""
    html, _, _ = page
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL))
    body = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    rendered = {name for group in re.findall(r'class="([^"]+)"', body)
                for name in group.split()}
    styled = set(re.findall(r"\.([A-Za-z][\w-]*)", css))
    assert not rendered - styled, (
        f"the page renders {sorted(rendered - styled)} with no rule for them")


def test_a_page_counting_the_field_sites_counts_the_ones_the_frame_list_holds(page):
    """A page saying "at 12 of the 17 field sites" gives two numbers of
    different kinds. The 12
    is measured, read off the frozen sample. The 17 is typed, and it is the
    size of the whole corpus, which no CSV behind the page carries: the
    builders never open the frame list. So it can only go stale, and the
    sentence it sits in is the page's own statement of what it does not cover.
    """
    html, _, _ = page
    named = re.search(r"of the (\d+) field sites", html)
    if named is None:
        return
    sites = frame_list_sites()
    assert int(named.group(1)) == len(sites), (
        f"the page says {named.group(1)} field sites and the frame list covers "
        f"{len(sites)}: {sorted(sites)}")
