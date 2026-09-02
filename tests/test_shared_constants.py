"""One number, written down in two files or three, with nothing comparing
the copies.

Each row below is a fact several scripts have to agree on. Where one of them
already imports the other, the copy was deleted instead and no row appears
here: `labelling/next_batch.py` and `predict/crown.py` both read
`core.GT_KEY_PREFIX`. What is left are copies across directories that share no
import, where deleting one would cost an import edge for one integer. So the
copies stay and this file holds them level.

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

# (constant, the files that write it down, what breaks when they drift apart)
COPIES = [
    ("MIN_BOX_SIDE", ["predict/crown.py", "predict/draw_confirmatory.py",
                      "dashboard/score_confirmatory.py"],
     "the frozen sample's stated rule is 'a labelled crown at least this many "
     "pixels on both sides'. The three files fetch the crowns, draw the sample "
     "and score it. If they disagree, the sample holds crowns the frozen "
     "manifest never certified, or the score reads a different set of crowns "
     "than the draw certified, and --verify does not catch it: it compares the "
     "draw against the committed CSV, not against the rule that produced the "
     "pool."),
    ("DEFAULT_MAX_CALLS", ["predict/crown.py", "predict/photo.py"],
     "both scripts spend from one 10,000/day identify quota. Raise the cap in "
     "one and the pair can cross it, so the second run dies on HTTP 429 partway "
     "through the corpus."),
    ("EMBEDDING_DIMS", ["predict/embed.py", "predict/aggregate_survey.py"],
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


@pytest.mark.parametrize("name,files,breaks", COPIES,
                         ids=[c[0] for c in COPIES])
def test_every_copy_says_the_same_thing(name, files, breaks):
    written = {f: value_of(name, f) for f in files}
    assert len(set(written.values())) == 1, (
        f"the files disagree about {name}: {written}. Because {breaks}")


def test_the_calibration_and_the_queue_use_one_confidence_cut():
    """crown_accuracy prints "top-1 correct when score >= CONF_CUT" as the
    evidence for the contradiction queue's cut. Move one and the published
    calibration stops describing the queue botanists are actually sent, while
    both scripts keep running."""
    (name_a, file_a), (name_b, file_b) = CONFIDENCE_CUT
    assert value_of(name_a, file_a) == value_of(name_b, file_b), (
        f"{file_a}'s {name_a} and {file_b}'s {name_b} are the same cut written "
        f"twice, and they no longer agree.")


# The function is nine words of string formatting, but it is the name of a file
# on disk: predict/crown.py writes data/crowns/cache/<crown_id>.json, and
# dashboard/score_confirmatory.py reads it back. dashboard/ is stdlib only and
# crown.py imports requests, so the reader cannot import the writer.
CROWN_ID = ["predict/crown.py", "dashboard/score_confirmatory.py"]


def body_of(name: str, relative: str) -> str:
    """A function's body, comments and docstring dropped, blank lines dropped."""
    source = (REPO / relative).read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(source) if line.startswith(f"def {name}(")]
    assert starts, f"{relative} no longer defines {name}"
    body = []
    for line in source[starts[0] + 1:]:
        if line and not line.startswith((" ", "\t")):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", '"""')):
            body.append(stripped)
    return "\n".join(body)


def test_the_writer_and_the_reader_spell_the_crown_cache_name_alike():
    """One drifted character and score_confirmatory finds no file for any
    crown. It counts those as absent and reports the frame on the frames that
    are left, so the run stays green and the crown arm quietly thins out."""
    writer, reader = CROWN_ID
    assert body_of("crown_id", writer) == body_of("crown_id", reader), (
        f"{writer} names the crown cache files and {reader} looks them up. "
        f"They no longer build the name the same way.")



# What README.md and CONTEXT.md state as a number, and where the code keeps it.
# These two files are the first thing anyone reads and the last thing anyone
# reruns: every one of these numbers was typed out once and then left alone.
# Each entry is (what it is, the file, a function that builds the phrase the
# file has to contain).
def _crop_size():
    return value_of("CROP_SIZE", "dashboard/crop_overlap.py")


def _crop_share():
    size = int(_crop_size())
    frame = (int(value_of("FRAME_W", "dashboard/crop_overlap.py"))
             * int(value_of("FRAME_H", "dashboard/crop_overlap.py")))
    return f"{100 * size * size / frame:.1f}%"


# The README draws the chain as a diagram and counts the files at one step in
# words. measure.OUTPUTS is the list, and it is read here rather than imported
# so this file keeps needing nothing installed.
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


def _measure_csv_count():
    source = (REPO / "dashboard" / "measure.py").read_text(encoding="utf-8")
    block = source[source.index("OUTPUTS = ("):]
    return WORDS[block[:block.index(")")].count(".csv")]


DOC_NUMBERS = [
    ("the crop", "README.md", lambda: f"{_crop_size()}x{_crop_size()}"),
    ("the crop's share of the frame", "README.md", _crop_share),
    ("the coverage gate", "README.md",
     lambda: f"`MIN_CROP_COVERAGE` ({value_of('MIN_CROP_COVERAGE', 'dashboard/core.py')})"),
    ("the frozen sample", "README.md",
     lambda: f"{value_of('N', 'predict/draw_confirmatory.py')} frames"),
    ("how many CSVs a run writes", "README.md",
     lambda: f"{_measure_csv_count()} CSVs"),
    ("the crop", "CONTEXT.md", lambda: f"{_crop_size()}x{_crop_size()}"),
    ("the crop's share of the frame", "CONTEXT.md", _crop_share),
    ("the frozen sample", "CONTEXT.md",
     lambda: f"{value_of('N', 'predict/draw_confirmatory.py')} frames"),
    ("the resample count", "CONTEXT.md",
     lambda: f"{int(value_of('BOOTSTRAP_DRAWS', 'dashboard/score_confirmatory.py')):,} times"),
]


@pytest.mark.parametrize("what,doc,build", DOC_NUMBERS,
                         ids=[f"{d[1]}-{d[0]}" for d in DOC_NUMBERS])
def test_the_docs_still_state_the_numbers_the_code_holds(what, doc, build):
    """A reader who never opens the code takes these files at their word. A
    constant moved in the code and left standing here is a claim nothing
    checks and nobody notices. CONTEXT.md is the wording the pages answer to,
    so a number stale there is a number stale on a page."""
    phrase = build()
    text = (REPO / doc).read_text(encoding="utf-8")
    assert phrase in text, (
        f"{doc} no longer states {what} as {phrase!r}. Either the code moved "
        f"and the file did not, or the sentence was reworded and this check "
        f"has to follow it.")
