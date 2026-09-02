"""The README quotes six numbers, and prose cannot import a constant.

Every one of them is a setting or a count that lives somewhere in the tree:
the crop size, the share of the frame it covers, the coverage gate, how many
names we ask Pl@ntNet for, how many CSVs a measurement pass writes, and how
many frames were frozen for the experiment. Written out in Markdown they are
copies, and a copy that nobody compares is how a front page ends up
describing the settings of a year ago.

Each test names the one definition it checks against, so a failure says which
file moved rather than only that the README is wrong.
"""

from __future__ import annotations

import csv
import os
import re

import pytest


@pytest.fixture(scope="session")
def readme(core):
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
        return fh.read()


def test_the_crop_size_and_its_share_of_the_frame(readme, crop_overlap):
    share = 100 * crop_overlap.CROP_SIZE ** 2 / (crop_overlap.FRAME_W
                                                 * crop_overlap.FRAME_H)
    assert f"{crop_overlap.CROP_SIZE}x{crop_overlap.CROP_SIZE} centre crop" in readme, (
        f"crop_overlap.CROP_SIZE is {crop_overlap.CROP_SIZE}; the README names a "
        f"different centre crop.")
    assert f"{share:.1f}% of the" in readme, (
        f"the crop is {share:.1f}% of the frame and the README says otherwise. "
        f"`panels.CROP_SHARE` computes the same figure for the page.")


def test_the_coverage_gate(readme, core):
    assert f"`MIN_CROP_COVERAGE` ({core.MIN_CROP_COVERAGE:.2f})" in readme, (
        f"core.MIN_CROP_COVERAGE is {core.MIN_CROP_COVERAGE}; the README quotes "
        f"another value. labelling/next_batch.py filters on this one.")


def test_the_candidate_list_length(readme, core):
    words = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
             9: "nine", 10: "ten"}
    assert f"list of {words[core.N_CANDIDATES]} names" in readme, (
        f"core.N_CANDIDATES is {core.N_CANDIDATES}; the README's closing "
        f"argument about unproven misses names a list of another length.")


def test_how_many_csvs_a_measurement_pass_writes(readme, measure):
    csvs = [name for name in measure.OUTPUTS if name.endswith(".csv")]
    words = {7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
             12: "twelve"}
    assert f"{words[len(csvs)]} CSVs" in readme, (
        f"measure.OUTPUTS writes {len(csvs)} CSVs and the diagram in the README "
        f"says a different number.")


def test_how_many_frames_were_frozen(readme, core):
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    frozen = os.path.join(root, "input", "confirmatory_frames_2026-08.csv")
    with open(frozen, encoding="utf-8") as fh:
        n = sum(1 for _ in csv.DictReader(fh))
    assert re.search(rf"\b{n} frames frozen before", readme), (
        f"{frozen} holds {n} frames and the README says another number. That "
        f"count is the sample size behind the headline.")


def test_the_layout_table_names_the_key_each_directory_reads(readme, core):
    """The README's layout table says which side needs which credential. It
    once said `predict/` was "the only side needing a key" three lines above a
    Configure section that asks for a Labelbox key too. Read the keys out of
    the source instead."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    rows = {line.split("|")[1].strip(): line
            for line in readme.splitlines() if line.startswith("| `")}
    for directory in ("predict/", "labelling/", "dashboard/"):
        read = set()
        folder = os.path.join(root, directory)
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                read |= set(re.findall(r"environ(?:\.get\(|\[)\"([A-Z_]+_API_KEY)\"",
                                       fh.read()))
        row = rows.get(f"`{directory}`")
        assert row, f"the README's layout table no longer has a {directory} row"
        for key in read:
            assert key in row, (
                f"{directory} reads {key} and the README's row for it does not "
                f"say so: {row.strip()}")
        if not read:
            assert "API_KEY" not in row, (
                f"the README's {directory} row names a key nothing in it reads: "
                f"{row.strip()}")


# Prefixes both files name that a fresh checkout does not have. Everything under
# them is generated and gitignored, and both files say so where they name them,
# so a checkout missing one is the normal state, not a broken link.
GENERATED = ("data/", "snapshots/", "build/", ".env")


@pytest.mark.parametrize("doc,least", [("README.md", 15), ("CONTEXT.md", 4)])
def test_every_path_the_docs_point_at_is_there(doc, least, core):
    """The front page is a map, and a map to a moved file is worse than none.

    Six numbers in the README are held to the code. The paths were not: rename a
    module or drop an ADR and the file keeps pointing at it, which the reader
    finds out one failed `cat` later. CONTEXT.md is the same promise in glossary
    form. The sibling `-docs` files count too, since both send the reader to
    them for what every number means.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    with open(os.path.join(root, doc), encoding="utf-8") as fh:
        text = fh.read()
    named = set(re.findall(r"`([\w./-]+/[\w./-]*|\.env[\w.]*|config\.yaml|"
                           r"requirements[\w-]*\.txt)`", text))
    assert len(named) >= least, (
        f"{doc} names only {len(named)} paths; the regex broke")
    missing = []
    for path in sorted(named):
        if path.startswith(GENERATED):
            continue
        full = (os.path.join(os.path.dirname(root), path)
                if path.startswith("bci-dashboard-docs/")
                else os.path.join(root, path))
        if not os.path.exists(full):
            missing.append(path)
    assert not missing, (
        f"{doc} points at {missing}, which is not in the checkout. Either the "
        f"file moved and {doc} did not, or it is generated and belongs under one "
        f"of the GENERATED prefixes with the reason.")


# The claim in metrics.md, and the column of per_species_health.csv that
# settles it. Both files are outside the tracked tree in a fresh clone, so
# this skips rather than fails when either is missing.
METRICS_CLAIMS = (
    (r"\*\*79\.46%\*\* \| per \*\*frame\*\*", "per_frame_top1", 0.7946),
    (r"\*\*50\.28%\*\* \| per \*\*species\*\*", "macro_top1", 0.5028),
    (r"scores\s+([\d,]+) frames over ([\d,]+) species", "frames_and_species", None),
)


def test_the_headline_rates_metrics_md_quotes_are_the_ones_the_snapshot_holds(core):
    """`metrics.md` is the sibling file that says what each number means.

    It leads with 79.46% per frame and 50.28% per species over 3,277 frames
    and 186 species, all quoted from the 2026-08-24 snapshot. Prose cannot
    import a CSV, so those four figures are copies. This recomputes them from
    `per_species_health.csv` the way the measurement does: micro is correct
    top-1 over labelled crowns, macro is the mean of the per-species rates.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    doc = os.path.join(os.path.dirname(root), "bci-dashboard-docs", "metrics.md")
    table = os.path.join(root, "snapshots", "model-health-2026-08-24",
                         "per_species_health.csv")
    for path, what in ((doc, "sibling bci-dashboard-docs/metrics.md"),
                       (table, "the 2026-08-24 snapshot")):
        if not os.path.exists(path):
            pytest.skip(f"{what} not present")
    with open(doc, encoding="utf-8") as fh:
        text = fh.read()
    with open(table, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    crowns = sum(int(r["n_labelled_crowns"]) for r in rows)
    micro = sum(int(r["n_correct_top1"]) for r in rows) / crowns
    macro = sum(float(r["top1_accuracy"]) for r in rows) / len(rows)
    for pattern, what, expected in METRICS_CLAIMS[:2]:
        assert re.search(pattern, text), (
            f"metrics.md no longer quotes {expected:.2%} as the {what} rate; "
            f"the snapshot gives {micro if 'frame' in what else macro:.4f}.")
    assert round(micro, 4) == 0.7946, f"per-frame top-1 is now {micro:.4f}"
    assert round(macro, 4) == 0.5028, f"per-species top-1 is now {macro:.4f}"

    said = re.search(METRICS_CLAIMS[2][0], text)
    assert said, "metrics.md no longer says how many frames and species it scores"
    assert int(said.group(1).replace(",", "")) == crowns, (
        f"metrics.md says {said.group(1)} frames, the snapshot holds {crowns}.")
    assert int(said.group(2).replace(",", "")) == len(rows), (
        f"metrics.md says {said.group(2)} species, the snapshot holds {len(rows)}.")


def test_metrics_md_cites_symbols_that_exist_and_no_line_numbers(core):
    """A line number in prose is a citation with a shelf life.

    `metrics.md` pointed at crop_overlap.py lines 136 to 138 for the definition
    of `coverage` and at next_batch.py lines 394 to 399 for the one place the
    gate filters. Both had drifted: the second is now the middle of an
    output-table list. A symbol name survives an edit above it, so the rule is
    that the file cites `module.symbol`, and this checks each one is real. The
    same rule is applied to the two front-page documents, which is why the
    line-number check reads a list of files rather than one.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    doc = os.path.join(os.path.dirname(root), "bci-dashboard-docs", "metrics.md")
    if not os.path.exists(doc):
        pytest.skip("sibling bci-dashboard-docs/metrics.md not present")
    with open(doc, encoding="utf-8") as fh:
        text = fh.read()

    numbered = []
    for path in (doc, os.path.join(root, "README.md"),
                 os.path.join(root, "CONTEXT.md")):
        with open(path, encoding="utf-8") as fh:
            numbered += re.findall(r"`([\w./]+\.py:[\d-]+)`", fh.read())
    assert not numbered, (
        f"the docs cite {numbered} by line number, which goes stale on the "
        f"next edit above it. Cite `module.symbol` instead.")

    modules = {}
    for where in ("dashboard", "predict", "labelling"):
        folder = os.path.join(root, where)
        for name in os.listdir(folder):
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    modules[name[:-3]] = fh.read()
    missing = []
    # A call or an upper-case constant. Anything else with a dot in it is a
    # filename: `history.csv` is not the `csv` member of a `history` module.
    cited = (re.findall(r"`(\w+)\.(\w+)\(\)`", text)
             + re.findall(r"`(\w+)\.([A-Z][A-Z_0-9]+)`", text))
    for module, symbol in cited:
        if module not in modules:
            continue
        if not re.search(rf"^(?:def|class) +{symbol}\b|^{symbol} *=",
                         modules[module], re.MULTILINE):
            missing.append(f"{module}.{symbol}")
    assert not missing, (
        f"metrics.md cites {missing}, which the module no longer defines.")


# The five rows of the crop-coverage table in metrics.md, in the order they
# are printed, each as (regex over the row, expected count).
CROP_TABLE = (
    (r"covers <50% of the crop \| ([\d,]+) \|", "lt50"),
    (r"covers 0% of the crop \| ([\d,]+) \|", "zero"),
    (r"no labelled box touches the crop at all \| ([\d,]+) \|", "untouched"),
    (r"of ([\d,]+) with a crop dominant\) \| ([\d,]+) \|", "dominant_disagrees"),
    (r"admits it anyway \| ([\d,]+) \|", "admitted"),
)


def test_the_crop_coverage_table_in_metrics_md_still_recomputes(core):
    """The provenance table nobody could check without running the pipeline.

    3,777 records, and five counts under it saying how often the whole-frame
    label is not what the centre crop shows. They were computed once, by hand,
    and written into prose. Recomputing them takes about a second: join the
    boxes to the crop rectangle, add up each species' share, and compare with
    the labelled species. The one thing that is easy to get wrong is the name
    mapping. Comparing raw box names gives 1,409 / 253 / 143 / 49; the table's
    numbers only appear once `Health.canon` folds synonyms first, which is the
    same mapping every published rate uses.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    doc = os.path.join(os.path.dirname(root), "bci-dashboard-docs", "metrics.md")
    if not os.path.exists(doc):
        pytest.skip("sibling bci-dashboard-docs/metrics.md not present")
    health = pytest.importorskip("health")
    crop_overlap = pytest.importorskip("crop_overlap")
    if not os.path.exists(crop_overlap.BOXES_CSV):
        pytest.skip("the tracked box list is not in this checkout")
    with open(doc, encoding="utf-8") as fh:
        text = fh.read()

    h = health.load_health()
    frames = crop_overlap.load_boxes(crop_overlap.BOXES_CSV)
    rect = crop_overlap.crop_rect()
    got = dict.fromkeys(("lt50", "zero", "untouched", "dominant_disagrees",
                         "admitted", "with_dominant"), 0)
    for rec in h.records:
        key = rec["global_key"].removeprefix(health.GT_KEY_PREFIX)
        share = {}
        for species, part in crop_overlap.frame_coverage(frames[key], rect).items():
            name = h.canon(species)
            share[name] = min(share.get(name, 0.0) + part, 1.0)
        labelled = share.get(h.canon(rec["gt"]), 0.0)
        got["lt50"] += labelled < core.MIN_CROP_COVERAGE
        got["zero"] += labelled == 0.0
        if not share:
            got["untouched"] += 1
            continue
        got["with_dominant"] += 1
        dominant, covered = max(share.items(), key=lambda kv: kv[1])
        if dominant != h.canon(rec["gt"]):
            got["dominant_disagrees"] += 1
            got["admitted"] += covered >= core.MIN_CROP_COVERAGE

    said = re.search(r"Measured on the ([\d,]+) evaluated records", text)
    assert said and int(said.group(1).replace(",", "")) == len(h.records), (
        f"metrics.md measures the table on {said and said.group(1)} records; "
        f"the pipeline joins {len(h.records)}.")
    for pattern, what in CROP_TABLE:
        found = re.search(pattern, text)
        assert found, f"metrics.md no longer prints the {what} row"
        if what == "dominant_disagrees":
            assert int(found.group(1).replace(",", "")) == got["with_dominant"], (
                f"metrics.md says {found.group(1)} frames have a crop dominant, "
                f"the boxes give {got['with_dominant']}.")
        printed = int(found.groups()[-1].replace(",", ""))
        assert printed == got[what], (
            f"metrics.md prints {printed} for {what}; recomputing from the "
            f"boxes gives {got[what]}.")
