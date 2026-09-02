"""Every page builder, end to end: build a real page, assert invariants.

Nothing exercised `build_external.py` or `build_internal.py` before this file,
so every cleanup pass over them had to be verified by hand-diffing 185KB of
HTML. `assets.py` is exercised by `test_assets.py` instead of here, and
`build_export_only.py` is exercised here alongside the other two builders.
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
from conftest import (
    GT_KEY_PREFIX,
    PAGES,
    SNAPSHOT_DIR,
    build_page,
    corpus_keys_with_species_gt,
    require_buildable,
    species_rows,
    write_export_ndjson,
)

REPO = pathlib.Path(__file__).resolve().parents[1]

_LEGEND = re.compile(r'<ul class="status-legend">.*?</ul>', re.S)
_TAG_LABEL = re.compile(r'<span class="tag [^"]*"[^>]*>([^<]*)</span>')






# ---------------------------------------------------------------------------
# The export page: no NDJSON export is tracked in the repo, so one is built at
# test time from the repo's own real inputs rather than being fixture data
# that would make this page skip on every machine.
# ---------------------------------------------------------------------------

def _gt_from_export():
    """Import labelling/gt_from_export.py by path, the same trick
    build_export_only.py's own `_load_gt_from_export` uses: labelling/ is not
    a package on the normal import path."""
    import importlib.util
    path = REPO / "labelling" / "gt_from_export.py"
    spec = importlib.util.spec_from_file_location("_gt_from_export", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_generated_export_is_in_the_shape_export_dominants_parses(export_fixture):
    """The hard part this suite exists to get right: nothing guarantees the
    NDJSON shape invented above is the shape the real merge script accepts.
    This calls `export_dominants` on the generated file directly and checks it
    recovers exactly the species that were put in, rather than trusting the
    shape by construction."""
    path, keys, gt = export_fixture
    dominants, _, _ = _gt_from_export().export_dominants(path)
    assert dominants, "export_dominants returned nothing -- the NDJSON shape is wrong"
    for gk in keys:
        stem = gk[len(GT_KEY_PREFIX):]
        assert dominants.get(stem) == gt[gk], (
            f"export_dominants did not recover the species put in for {gk}")


def test_build_renders_the_no_score_note_when_nothing_joins(tmp_path_factory):
    """The branch nothing else here covers: every labelled key in the export
    has no cached Pl@ntNet prediction, so nothing can be scored. Real keys
    again -- the corpus's own GT rows with no file under
    data/predictions/cache -- not a fabricated gap."""
    require_buildable()
    _, without_cache, gt = corpus_keys_with_species_gt()
    assert without_cache, (
        "no GT key on this machine lacks a cached prediction -- nothing to build this from")
    path = tmp_path_factory.mktemp("export_nocache") / "export.ndjson"
    write_export_ndjson(path, without_cache, gt)
    html, _ = build_page(tmp_path_factory, *PAGES["export_only_page"][:2], export=str(path))
    assert ("No photo in this export both carries a species label and has a "
            "cached Pl@ntNet prediction") in html
    assert not re.search(r"\d+\.\d%", html), "an accuracy percentage was printed anyway"


def test_the_export_funnel_accounts_for_every_row(export_only_page):
    """The funnel exists to say where the rows that are not in the accuracy
    rate went. It once dropped the genus-only frames: the counts on screen did
    not add up, and a reader who checked found rows missing. Steps, in order:
    rows, labelled, joined to a cached answer, named a species, stopped at the
    genus, no cached answer."""
    html, _ = export_only_page
    funnel = re.search(r'<ul class="todo">(.*?)</ul>', html, re.DOTALL)
    assert funnel, "the export page rendered no funnel"
    counts = [int(x.replace(",", ""))
              for x in re.findall(r'<span class="n">([\d,]+)</span>', funnel.group(1))]
    assert len(counts) == 6, f"expected six funnel steps, got {counts}"
    rows, labelled, joined, species, genus, no_cache = counts
    assert labelled <= rows
    assert joined + no_cache == labelled, (
        f"labelled {labelled} is not joined {joined} plus un-joined {no_cache}")
    assert species + genus == joined, (
        f"joined {joined} is not species {species} plus genus-only {genus}")


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

    The queue page opens the two a labeller works from. The export-only page is
    a 19-species spot check and opens both of its own. The model-health page
    opens none: its answer is the two hero cards, and the species table is a
    lookup tool. Open, that table was 40% of the page's words sitting fourth of
    nine, and the five panels below it were a scroll nobody made.
    """
    expected = {
        "model_health": [],
        "label_queue": ["Where to spend botanist time next",
                        "What to send to the botanist first"],
        "export_only": ["Where these numbers come from", "Look up one species"],
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
# The frozen confirmatory read
# ---------------------------------------------------------------------------

def test_the_published_headline_matches_the_frozen_result_file(page):
    """The page must print the numbers the scorer wrote, not numbers of its own.

    Nothing recomputes this at build time on purpose -- the stopping rule says
    the confirmatory read happens once on the complete set -- so the only thing
    standing between the file and the headline is the formatting, and that is
    what this checks.
    """
    import csv

    html, _, carries = page
    with open(REPO / "input" / "confirmatory_result_2026-08.csv",
              newline="", encoding="utf-8") as f:
        cf = {r["key"]: r["value"] for r in csv.DictReader(f)}
    headline = f'{100 * float(cf["crown_top1"]):.1f}%'
    legacy = f'{100 * float(cf["photo_top1"]):.1f}%'
    if "confirmatory" not in carries:
        assert headline not in html or legacy not in html, (
            "a page that does not carry the frozen read prints its headline anyway")
        return
    assert headline in html and legacy in html, (
        f"page does not print both region arms: {headline}, {legacy}")
    # Population and support, per CLAUDE.md: a rate alone is not publishable.
    assert f'{int(float(cf["n_frames"]))} frames' in html
    assert f'{int(float(cf["n_sites"]))} sites' in html
    assert f'{int(float(cf["crown_hits"]))} of {int(float(cf["crown_n"]))} frames right' in html


def test_a_bootstrap_p_of_zero_is_never_printed_as_zero(page):
    """0 of 10,000 resamples is a resolution limit, not a p of exactly zero."""
    html, _, _ = page
    assert "p = 0.00000" not in html


def test_the_two_caveats_the_design_requires_travel_with_the_headline(page):
    """Both amendments in hypothesis.md say the writeup must carry their words
    rather than a summary. The page publishes the number, so the page is the
    writeup, and a paraphrase here would break the design's own condition."""
    html, _, carries = page
    verbatim = (
        "But the number was not generated blind.</strong> An operator has seen "
        "crown-arm accuracy, at another unit and on a wider population, before this freeze.",
        "What this costs, stated plainly.</strong> The arm was dropped after its "
        "interim number had been seen, and no amount of reasoning removes that ordering.",
    )
    for quote in verbatim:
        assert (quote in html) == ("confirmatory" in carries), (
            f"page carries the frozen read: {'confirmatory' in carries}, "
            f"but the quote {quote[:40]!r} is present: {quote in html}")


HYPOTHESIS = REPO.parent / "bci-dashboard-docs" / "hypothesis.md"


def test_the_quoted_amendments_still_match_the_design_document(external_page):
    """The two quotes are stored as HTML literals in panels.py, so nothing links
    them to hypothesis.md except this test. Both amendments require their words
    rather than a summary, which makes a silent paraphrase a design violation
    and not just a typo."""
    import html as htmllib

    if not HYPOTHESIS.exists():
        pytest.skip("sibling bci-dashboard-docs/hypothesis.md not present")
    doc = HYPOTHESIS.read_text(encoding="utf-8")
    html, _ = external_page
    start = html.find('id="where-the-headline-comes-from"')
    assert start >= 0, "the panel carrying the quotes is not on the page"
    shown = re.sub(r"\s+", " ",
                   htmllib.unescape(re.sub(r"<[^>]+>", " ", html[start:])))

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
            f"the page no longer quotes hypothesis.md verbatim; it diverges near "
            f"{quote[:80]!r}")


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

    The model-health page is the one that prints it, twice: under the species
    table and again under the four corpus rates."""
    html, _ = external_page
    assert html.count("covers less than half the crop") == 2, (
        "the note is gone or reworded")
    assert core.MIN_CROP_COVERAGE == 0.50, (
        f"MIN_CROP_COVERAGE is {core.MIN_CROP_COVERAGE}, so the page's "
        f"'less than half the crop' names a line the gate no longer draws")
