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


# Paths the README names that a fresh checkout does not have. All three are
# generated and gitignored, and the README says so in the same table it names
# them in, so a checkout missing them is the normal state, not a broken link.
README_GENERATED = ("data/", "snapshots/", "build/", ".env")


def test_every_path_the_readme_points_at_is_there(readme, core):
    """The front page is a map, and a map to a moved file is worse than none.

    Six numbers in this file are held to the code. The paths were not: rename a
    module or drop an ADR and the README keeps pointing at it, which the reader
    finds out one failed `cat` later. The sibling `-docs` files count too, since
    the README sends the reader to them for what every number means.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    named = set(re.findall(r"`([\w./-]+/[\w./-]*|\.env[\w.]*|config\.yaml|"
                           r"requirements[\w-]*\.txt)`", readme))
    assert len(named) > 15, f"the README names only {len(named)} paths; the regex broke"
    missing = []
    for path in sorted(named):
        if path in README_GENERATED:
            continue
        full = (os.path.join(os.path.dirname(root), path)
                if path.startswith("bci-dashboard-docs/")
                else os.path.join(root, path))
        if not os.path.exists(full):
            missing.append(path)
    assert not missing, (
        f"the README points at {missing}, which is not in the checkout. Either "
        f"the file moved and the README did not, or it is generated and belongs "
        f"in README_GENERATED with the reason.")
