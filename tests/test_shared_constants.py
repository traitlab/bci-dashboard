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

import csv
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


def frame_list_sites() -> set:
    """The field sites the tracked frame list covers.

    Not written down in any constant: it falls out of `input/boxes/...csv`, the
    file that defines the population. Anything saying how many sites there are,
    on a page or in CONTEXT.md, is held to this. Add a flight over an
    eighteenth site and every sentence about the draw is off by one.

    The site is pulled out of the frame URL the way draw_confirmatory pulls it,
    by that file's own MISSION_RE, read as text: draw_confirmatory imports
    requests, and a check that needs the fetch stack installed is a check that
    stops running.
    """
    pattern = value_of("MISSION_RE", "predict/draw_confirmatory.py")
    assert pattern.startswith("re.compile(r\"") and pattern.endswith("\")"), (
        f"draw_confirmatory's MISSION_RE is no longer a plain compiled literal "
        f"this can read: {pattern}")
    mission = re.compile(pattern[len("re.compile(r\""):-2])

    frames = (REPO / "input" / "boxes" / "bci_images_for_plantnet_w_split.csv")
    urls = csv.DictReader(frames.read_text(encoding="utf-8").splitlines())
    sites = {found.group(2) for row in urls
             if (found := mission.search(row["image_url"]))}
    assert sites, f"no site name matched {mission.pattern} in {frames.name}"
    return sites


def test_context_counts_the_sites_the_frame_list_actually_holds():
    """CONTEXT.md tells a reader there are 17 sites, and the confirmatory draw
    works its range out by drawing whole sites, so the number is the size of
    the thing being sampled."""
    sites = frame_list_sites()
    context = (REPO / "CONTEXT.md").read_text(encoding="utf-8")
    assert f"There are {len(sites)};" in context, (
        f"the frame list covers {len(sites)} sites and CONTEXT.md says otherwise. "
        f"The sites are {sorted(sites)}.")


# Every file under input/boxes/ that some script or docstring names. The folder
# is tracked, small and rarely touched, which is exactly why a path into it goes
# stale quietly: nothing fails until somebody runs the fetch with no --input.
INPUT_BOXES = [path
               for folder, pattern in (("predict", "*.py"), ("dashboard", "*.py"),
                                       ("labelling", "*.py"), ("bin", "*.sh"))
               for path in sorted((REPO / folder).glob(pattern))]


@pytest.mark.parametrize("source", INPUT_BOXES,
                         ids=lambda s: s.relative_to(REPO).as_posix())
def test_every_input_boxes_path_a_script_names_is_a_file_that_is_there(source):
    """`predict/photo.py` defaulted for months to input/boxes/
    bci_images_for_plantnet.csv, which the repo renamed to ..._w_split.csv. The
    script's docstring said the same missing name, so reading the file could
    not catch it, and a run with no --input opened nothing. Names in comments
    and docstrings count: they are what the next person types."""
    text = source.read_text(encoding="utf-8")
    for name in set(re.findall(r"input/boxes/([A-Za-z0-9_.\-]+\.csv)", text)):
        assert (REPO / "input" / "boxes" / name).exists(), (
            f"{source.relative_to(REPO)} names input/boxes/{name}, which is not "
            f"there. input/boxes holds "
            f"{sorted(p.name for p in (REPO / 'input' / 'boxes').iterdir())}.")


def test_the_fetch_writes_into_the_folder_the_dashboard_reads():
    """`predict/photo.py` takes its output folder from config.yaml and every
    page reads `core.CACHE_DIR`. Those were `data/photos` and
    `data/predictions` for months, so a plain `python predict/photo.py` would
    have spent a credit per photo writing 7,000 JSONs into a directory nothing
    opens, and the pages would have gone on reporting the older numbers.

    Nothing failed while it was wrong, which is why it needs a test rather than
    a comment: the fetch is the one step nobody runs twice by accident."""
    config = (REPO / "config.yaml").read_text(encoding="utf-8")
    m = re.search(r"^\s*single_predictions:\s*(\S+)", config, re.MULTILINE)
    assert m, "config.yaml no longer says where the single-photo fetch writes"
    core = (REPO / "dashboard" / "core.py").read_text(encoding="utf-8")
    parts = re.search(r"CACHE_DIR = os\.path\.join\(BASE,\s*(.+?)\)", core)
    assert parts, "dashboard/core.py no longer builds CACHE_DIR from BASE"
    folder = re.findall(r'"([^"]+)"', parts.group(1))[0]
    assert m.group(1) == f"data/{folder}", (
        f"config.yaml sends the fetch to {m.group(1)} and the pages read "
        f"data/{folder}. A fetch into the wrong one is silent: it costs a "
        f"Pl@ntNet credit per photo and changes no number on any page.")


def test_the_tile_window_is_the_one_the_survey_call_documents():
    """`crown.py` counts sampled crowns smaller than Pl@ntNet's own tile
    window, and the only record of how wide that window is sits in
    `ingest_photos.call_survey`'s docstring, measured against a real frame.
    A reader who changes one has no reason to look at the other, and the count
    would then be reported under a width nothing measured."""
    px = value_of("TILE_WINDOW_PX", "predict/crown.py")
    survey = (REPO / "predict" / "ingest_photos.py").read_text(encoding="utf-8")
    assert f"{px}px window" in survey, (
        f"crown.py counts crowns under {px}px and ingest_photos.py documents a "
        f"different window. One of the two moved.")


# Every tracked script, by the folders that hold them.
SCRIPTS = [path
           for folder, pattern in (("predict", "*.py"), ("dashboard", "*.py"),
                                   ("labelling", "*.py"), ("bin", "*.sh"),
                                   ("tests", "*.py"))
           for path in sorted((REPO / folder).glob(pattern))]

_SCRIPT_PATH = re.compile(
    r"\b(?:predict|dashboard|labelling|bin|tests)/[A-Za-z0-9_.-]+\.(?:py|sh)\b")


@pytest.mark.parametrize("source", SCRIPTS,
                         ids=lambda s: s.relative_to(REPO).as_posix())
def test_every_script_a_file_points_at_is_a_script_that_is_there(source):
    """Files name their neighbours constantly: `crown.py` reuses photo.py's API
    client, the ADRs cite build scripts, docstrings send a reader to the module
    that measured a number. A rename moves the file and leaves every sentence
    about it pointing at nothing, and prose does not fail a build.

    Comments and docstrings count as much as code: they are what the next
    person opens. Retired scripts get named on purpose in `docs/adr/`, which is
    a record of what the repo used to be and is left out of this sweep.
    """
    text = source.read_text(encoding="utf-8")
    for name in sorted(set(_SCRIPT_PATH.findall(text))):
        assert (REPO / name).exists(), (
            f"{source.relative_to(REPO)} points at {name}, which is not there. "
            f"Either the file moved and this mention did not, or the name is a "
            f"typo.")


def test_the_note_over_edge_tolerance_still_counts_the_boxes_it_claims():
    """``crop_overlap.EDGE_TOLERANCE`` is 4 px because a sweep of the box CSV
    found the overhang small and rare, and the comment above it writes that
    sweep down: how many frames overhang, out of how many, and the largest
    coordinate seen. Three measured numbers, in prose, over a file that is
    tracked in the repo. So re-run the sweep and hold the sentence to it. A
    new box export otherwise moves the numbers and the stated reason for the
    constant quietly becomes fiction.
    """
    source = (REPO / "dashboard" / "crop_overlap.py").read_text(encoding="utf-8")
    claim = re.search(
        r"# ([\d,]+) of ([\d,]+) frames have a box edge 1-2 px outside it.*?"
        r"largest coordinate is ([\d,]+) x ([\d,]+)\)", source, re.DOTALL)
    assert claim, ("the note above EDGE_TOLERANCE no longer states its counts "
                   "in a shape this can read")
    said_over, said_frames, said_x, said_y = (
        int(g.replace(",", "")) for g in claim.groups())

    width = int(value_of("FRAME_W", "dashboard/crop_overlap.py"))
    height = int(value_of("FRAME_H", "dashboard/crop_overlap.py"))
    boxes = (REPO / "input" / "boxes" / "crop_bounding_boxes.csv")
    rows = list(csv.DictReader(boxes.read_text(encoding="utf-8").splitlines()))

    frames = {row["base_image"] for row in rows}
    over = {row["base_image"] for row in rows
            if float(row["x_max"]) > width or float(row["y_max"]) > height
            or float(row["x_min"]) < 0 or float(row["y_min"]) < 0}
    largest = (max(float(row["x_max"]) for row in rows),
               max(float(row["y_max"]) for row in rows))

    assert (said_over, said_frames) == (len(over), len(frames)), (
        f"the note says {said_over} of {said_frames} frames overhang and the "
        f"box CSV now has {len(over)} of {len(frames)}")
    assert (said_x, said_y) == largest, (
        f"the note says the largest coordinate is {said_x} x {said_y} and the "
        f"box CSV now reaches {largest[0]:.0f} x {largest[1]:.0f}")
    assert max(largest[0] - width, largest[1] - height) <= int(
        value_of("EDGE_TOLERANCE", "dashboard/crop_overlap.py")), (
        "a box now hangs further outside the frame than EDGE_TOLERANCE "
        "forgives, so the overhang is no longer a rounding artifact")
