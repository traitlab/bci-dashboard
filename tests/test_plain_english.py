"""What a reader meets on the page, measured rather than asserted by hand.

`tests/test_pages.py` checks that the right figures, panels and warnings are
present. Nothing checked that they are readable. This file does: it pulls the
prose out of a built page and holds two lines that a later edit can only cross
deliberately.

  * no sentence longer than `MAX_SENTENCE_WORDS`, because a sentence a reader
    has to hold in their head is one they stop reading;
  * none of the words `CONTEXT.md` retired, because a glossary that is not
    enforced is a glossary that drifts.

`README.md` is held to the same two lines. It is the first thing anyone
reads, so a page that says "the right name in the list" while the front page
says "top-5" has retired the word in the one place it is measured and kept it
in the one place it is met.

Both checks run on the page's own prose, not on the source: what matters is
what a reader sees, and the same sentence can be assembled from three
f-strings. Tables, the species list and the inline script are excluded -- a
186-row table is data, not prose, and scoring it as prose swamps every real
sentence. So is anything in a `<code>` span: `nb-results=5` and
`identify/k-central-america` are identifiers a reader looks at rather than
reads, and counting them as words makes a short sentence look long.

Two kinds of quoted text are excluded, and deliberately.
`bci-dashboard-docs/hypothesis.md` requires those paragraphs in their own
words, so they are the one place on the page where the study's vocabulary is
load-bearing and a paraphrase would be a defect. Every one of them carries a
plain-English gloss immediately above it; the gloss is prose and is checked.
The other is the provenance line, which `labelling/gt_from_export.py` writes
to a sidecar at merge time and the page reproduces: it is a record of which
export the labels came from, not a sentence anyone on the page wrote.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path

import pytest

# The longest sentence any page carries today, so the ceiling is where the
# prose actually is rather than somewhere comfortable above it. A sentence
# that trips this is not necessarily wrong -- it is a sentence someone has to
# read again -- so the fix is to split it, and moving the number up is a
# decision to make out loud. It has come down from 31: the one sentence that
# needed 31 was a clause, and it reads as two.
MAX_SENTENCE_WORDS = 30

# The share of sentences allowed to run long. A hard per-sentence cap alone
# lets the prose fill up with 25-word sentences, so this keeps the middle
# short. Both pages are inside it today: 0.0% and 1.1%, and the one sentence
# left over the cap is a comma-list of ten species names, not a clause a
# reader has to hold open.
MAX_LONG_SENTENCE_SHARE = 0.02
LONG_SENTENCE_WORDS = 25

# Retired by CONTEXT.md, each with what a page says instead. The message is
# the whole value of the check: a failure has to tell the next person what to
# write, not just that they wrote the wrong thing.
RETIRED = {
    r"\barms?\b": "way of asking / ways of asking",
    r"\bregion-aligned\b": "crown-by-crown, or 'a botanist outlined the trees first'",
    r"\bbootstrapp?e?d?\b": "the range, and how it was worked out in plain words",
    r"\bmacro\b": "per species",
    r"\bmicro\b": "per frame",
    r"\btop-?1\b": "first guess",
    r"\btop-?5\b": "right name in the list",
    r"\bground truth\b": "label",
    r"\bpre-?registered\b": "fixed in advance / written into the plan",
    r"\bprior[- ]exposure\b": "already seen",
    r"\bconfirmatory\b": "set-aside frames / the frozen sample",
    r"\bdeprioriti[sz]ed?\b": "pushed down the queue",
    r"\brevocable\b": "undone at the next model change",
    r"\b(un)?gated\b": "with, or without, the labelled-frames condition",
    r"\bthresholds?\b": "the confidence line",
    r"\bhits?\b": "right, or a right first guess",
    r"\bsupport\b": "labelled frames",
    r"\bembeddings?\b": "how the photo looks to the model",
    r"\bfarthest-first\b": "least like everything already labelled",
    # The compound adjective is what CONTEXT.md itself uses ("the long-lens
    # one"), so only the bare noun is retired.
    r"(?<!-)\blens(es)?\b": "camera, or the long-lens camera",
}

# Prose lives in these; everything else on the page is data or chrome.
_PROSE_TAG = re.compile(
    r"<(p|li|summary|h1|h2|h3|figcaption)\b[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
_NOT_PROSE = re.compile(
    r"<(script|style|table|select|svg)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_CODE = re.compile(r"<code\b[^>]*>.*?</code>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
           "&rsquo;": "'", "&nbsp;": " ", "&mdash;": " ", "&ndash;": " "}


def _text(fragment: str) -> str:
    out = _TAG.sub(" ", fragment)
    for entity, plain in _ENTITY.items():
        out = out.replace(entity, plain)
    return " ".join(out.split())


def prose(html: str, drop: tuple[str, ...] = ()) -> list[str]:
    """The reader-facing prose of `html`, one string per block.

    `drop` holds fragments to remove before extraction -- the required verbatim
    quotes -- so their sentences are neither counted nor searched.
    """
    for fragment in drop:
        html = html.replace(fragment, "")
    html = _NOT_PROSE.sub(" ", html)
    html = _CODE.sub(" ", html)
    return [text for _, body in _PROSE_TAG.findall(html)
            if (text := _text(body))]


_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_EMPHASIS = re.compile(r"\*{1,2}([^*]+)\*{1,2}")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def markdown_prose(text: str) -> list[str]:
    """The prose of a Markdown file, one string per paragraph or list item.

    Fenced blocks, inline code and table rows are dropped for the same reason
    the page's tables and `<code>` spans are: a file path and a column name are
    identifiers a reader looks at rather than reads, and counting them as words
    makes a short sentence look long. Blocks are kept apart so a bullet list
    after a colon is several sentences and not one very long one.
    """
    text = _FENCE.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _EMPHASIS.sub(r"\1", text)

    blocks, current = [], []
    for line in text.splitlines():
        stripped = line.strip()
        starts_block = stripped.startswith(("-", "*", "|", "#", ">"))
        if current and (not stripped or starts_block):
            blocks.append(" ".join(current))
            current = []
        if not stripped or stripped.startswith(("|", "#", ">")):
            continue
        current.append(stripped.lstrip("-* "))
    if current:
        blocks.append(" ".join(current))
    return [block for block in blocks if block]


def sentences(blocks: list[str]) -> list[str]:
    """Sentences worth judging: a 1- or 2-word fragment is a label or a
    heading, not something a reader has to parse."""
    return [s for block in blocks for s in _SENTENCE_SPLIT.split(block)
            if len(s.split()) >= 3]


@pytest.fixture(scope="session")
def quoted(core, assets):
    """Text the page reproduces rather than writes.

    Only the provenance line remains: `labelling/gt_from_export.py` writes it
    to a sidecar at merge time and the page reproduces it, so it is a record of
    which export the labels came from, not a sentence anyone on the page wrote.
    The two blocks `hypothesis.md` requires verbatim left the page on
    2026-09-02 for `bci-dashboard-docs/metrics.md`; every sentence the page
    carries now is one the page wrote, so every sentence is checked.
    """
    return (assets.esc(core.gt_provenance()),)


@pytest.fixture(scope="session")
def external_prose(external_page, quoted):
    return prose(external_page[0], drop=quoted)


@pytest.fixture(scope="session")
def internal_prose(internal_page):
    return prose(internal_page[0])


@pytest.fixture(params=("external_prose", "internal_prose"))
def page_prose(request):
    """Every page, one at a time, so a retired word cannot be retired on one
    page and left standing on another."""
    return request.param, request.getfixturevalue(request.param)


def _no_long_sentences(blocks, page):
    long = [(len(s.split()), s) for s in sentences(blocks)
            if len(s.split()) > MAX_SENTENCE_WORDS]
    assert not long, (
        f"{page}: {len(long)} sentence(s) over {MAX_SENTENCE_WORDS} words. "
        f"Split them:\n" + "\n".join(f"  [{n} words] {s}" for n, s in sorted(long, reverse=True)))


def test_the_external_page_has_no_sentence_a_reader_has_to_reread(external_prose):
    _no_long_sentences(external_prose, "model_health_dashboard.html")


def test_the_internal_page_has_no_sentence_a_reader_has_to_reread(internal_prose):
    _no_long_sentences(internal_prose, "label_queue_dashboard.html")


def test_most_of_each_page_is_in_short_sentences(page_prose):
    """A cap on the longest sentence says nothing about the middle of the
    distribution, which is where a page gets heavy."""
    name, blocks = page_prose
    found = sentences(blocks)
    long = [s for s in found if len(s.split()) > LONG_SENTENCE_WORDS]
    share = len(long) / len(found)
    assert share <= MAX_LONG_SENTENCE_SHARE, (
        f"{name}: {len(long)} of {len(found)} sentences run over {LONG_SENTENCE_WORDS} "
        f"words ({share:.0%}, ceiling {MAX_LONG_SENTENCE_SHARE:.0%}); "
        f"median is {statistics.median(len(s.split()) for s in found)} words")


@pytest.mark.parametrize("pattern,instead", sorted(RETIRED.items()))
def test_neither_page_uses_a_word_context_md_retired(page_prose, pattern, instead):
    """The glossary is only worth writing if a page cannot quietly leave it.

    Searched on the page's prose and outside the text it only reproduces,
    which is exactly what an author controls.
    """
    name, blocks = page_prose
    hits = [block for block in blocks if re.search(pattern, block, re.IGNORECASE)]
    assert not hits, (
        f"{name}: '{pattern}' is retired; say {instead}. In CONTEXT.md. Found in:\n"
        + "\n".join(f"  {block[:160]}" for block in hits[:5]))


@pytest.fixture(scope="session")
def readme_prose(core):
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
        return markdown_prose(fh.read())


def test_the_readme_has_no_sentence_a_reader_has_to_reread(readme_prose):
    _no_long_sentences(readme_prose, "README.md")


@pytest.mark.parametrize("pattern,instead", sorted(RETIRED.items()))
def test_the_readme_uses_no_word_context_md_retired(readme_prose, pattern, instead):
    """The front page answers to the glossary too.

    It said the pages "score ungated" and that every number carries a "support
    count", both retired, and both in the paragraph that exists to tell a
    newcomer what the numbers mean.
    """
    hits = [block for block in readme_prose if re.search(pattern, block, re.IGNORECASE)]
    assert not hits, (
        f"README.md: '{pattern}' is retired; say {instead}. In CONTEXT.md. Found in:\n"
        + "\n".join(f"  {block[:160]}" for block in hits[:5]))


# The pages set a dash off with " -- " or rewrite it as a comma. A page is
# read next to the other one, and a reader notices the typography before they
# notice why.
LONG_DASHES = ("—", "–", "&mdash;", "&ndash;")


def test_no_page_sets_a_phrase_off_with_a_long_dash(page):
    """Punctuation is part of reading level: a dash a reader has to decide the
    weight of is a pause, and the same pause is available as a comma."""
    html, _stdout, _panels = page
    found = [dash for dash in LONG_DASHES if dash in html]
    assert not found, (
        f"a page carries {found}. Use ' -- ', a comma or two sentences; the "
        f"other pages do.")


# The page test above only sees what a page prints. The dash got onto the page
# from a source file, and the same source files are read by the next person to
# change one. Half the long dashes in this repo were in docstrings and headers,
# where no page test could ever have reached them.
REPO = Path(__file__).resolve().parents[1]
WRITTEN_FOR_PEOPLE = (sorted(REPO.glob("*.md"))
                      + sorted((REPO / "dashboard").glob("*.py"))
                      + sorted((REPO / "predict").glob("*.py"))
                      + sorted((REPO / "labelling").glob("*.py")))


@pytest.mark.parametrize("source", WRITTEN_FOR_PEOPLE,
                         ids=lambda s: s.relative_to(REPO).as_posix())
def test_no_source_file_sets_a_phrase_off_with_a_long_dash(source):
    """Same rule as the pages, one step earlier: comments, docstrings and the
    two front-page documents are prose too, and are where a dash starts."""
    text = source.read_text(encoding="utf-8")
    found = [dash for dash in LONG_DASHES if dash in text]
    assert not found, (
        f"{source.relative_to(REPO)} carries {found}. Use a comma, a colon or "
        f"two sentences.")
