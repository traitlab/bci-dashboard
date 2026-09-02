"""One number, written down in two files, with nothing comparing the copies.

Each pair below is a fact two scripts have to agree on. Where one of them
already imports the other, the copy was deleted instead and no pair appears
here: `labelling/next_batch.py` and `predict/crown.py` both read
`core.GT_KEY_PREFIX`. What is left are pairs across
directories that share no import, where deleting a copy would cost an import
edge for one integer. So the copies stay and this file holds them level.

The comparison is on the source text, not on imported modules: these scripts
pull in requests, numpy and pandas, and a test that needs the fetch stack
installed to notice a drifted threshold is a test that stops running.

    .venv/bin/pytest tests/test_shared_constants.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# (constant, file, file, what breaks when the two drift apart)
PAIRS = [
    ("MIN_BOX_SIDE", "predict/crown.py", "predict/draw_confirmatory.py",
     "the frozen sample's stated rule is 'a labelled crown at least this many "
     "pixels on both sides'. If the fetcher and the draw disagree, the sample "
     "holds crowns the frozen manifest never certified, and --verify does not "
     "catch it: it compares the draw against the committed CSV, not against "
     "the rule that produced the pool."),
    ("DEFAULT_MAX_CALLS", "predict/crown.py", "predict/photo.py",
     "both scripts spend from one 10,000/day identify quota. Raise the cap in "
     "one and the pair can cross it, so the second run dies on HTTP 429 partway "
     "through the corpus."),
    ("EMBEDDING_DIMS", "predict/embed.py", "predict/aggregate_survey.py",
     "both use it as an equality filter, not an assertion. If Pl@ntNet's vector "
     "width moves and one file follows, aggregate_survey collects nothing, "
     "prints 'Embeddings: 0 photos' and exits 0."),
]

# Not the same name on both sides, so it gets its own row.
CONFIDENCE_CUT = [
    ("CONF_CUT", "predict/crown_accuracy.py"),
    ("CONTRADICTION_MIN_SCORE", "labelling/next_batch.py"),
]


def value_of(name: str, relative: str) -> str:
    """The right-hand side of a module-level assignment, as written."""
    source = (REPO / relative).read_text(encoding="utf-8")
    found = re.search(rf"^{name} = (.+)$", source, re.M)
    assert found, f"{relative} no longer defines {name}"
    return found.group(1).strip()


@pytest.mark.parametrize("name,left,right,breaks", PAIRS,
                         ids=[p[0] for p in PAIRS])
def test_the_two_copies_say_the_same_thing(name, left, right, breaks):
    assert value_of(name, left) == value_of(name, right), (
        f"{left} and {right} disagree about {name}. Because {breaks}")


def test_the_calibration_and_the_queue_use_one_confidence_cut():
    """crown_accuracy prints "top-1 correct when score >= CONF_CUT" as the
    evidence for the contradiction queue's cut. Move one and the published
    calibration stops describing the queue botanists are actually sent, while
    both scripts keep running."""
    (name_a, file_a), (name_b, file_b) = CONFIDENCE_CUT
    assert value_of(name_a, file_a) == value_of(name_b, file_b), (
        f"{file_a}'s {name_a} and {file_b}'s {name_b} are the same cut written "
        f"twice, and they no longer agree.")
