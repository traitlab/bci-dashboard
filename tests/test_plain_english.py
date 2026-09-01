"""What a reader meets on the page, measured rather than asserted by hand.

`tests/test_pages.py` checks that the right figures, panels and warnings are
present. Nothing checked that they are readable. This file does: it pulls the
prose out of a built page and holds two lines that a later edit can only cross
deliberately.

  * no sentence longer than `MAX_SENTENCE_WORDS`, because a sentence a reader
    has to hold in their head is one they stop reading;
  * none of the words `CONTEXT.md` retired, because a glossary that is not
    enforced is a glossary that drifts.

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

import pytest

# The longest sentence either page carries today, so the ceiling is where the
# prose actually is rather than somewhere comfortable above it. A sentence
# that trips this is not necessarily wrong -- it is a sentence someone has to
# read again -- so the fix is to split it, and moving the number up is a
# decision to make out loud.
MAX_SENTENCE_WORDS = 34

# The share of sentences allowed to run long. A hard per-sentence cap alone
# lets the prose fill up with 30-word sentences; this keeps the middle short.
MAX_LONG_SENTENCE_SHARE = 0.15
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


def sentences(blocks: list[str]) -> list[str]:
    """Sentences worth judging: a 1- or 2-word fragment is a label or a
    heading, not something a reader has to parse."""
    return [s for block in blocks for s in _SENTENCE_SPLIT.split(block)
            if len(s.split()) >= 3]


@pytest.fixture(scope="session")
def quoted(panels, core, assets):
    """Text the page reproduces rather than writes: the two blocks
    `hypothesis.md` requires verbatim, and the provenance line the merge
    script wrote to its sidecar. Taken from the modules that render them
    rather than retyped, because retyped they would drift and this file would
    start excluding nothing.
    """
    return (panels.A2_PRIOR_EXPOSURE, panels.A4_WHAT_THIS_COSTS,
            assets.esc(core.gt_provenance()))


@pytest.fixture(scope="session")
def external_prose(external_page, quoted):
    return prose(external_page[0], drop=quoted)


@pytest.fixture(scope="session")
def internal_prose(internal_page):
    return prose(internal_page[0])


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


def test_most_of_the_external_page_is_in_short_sentences(external_prose):
    """A cap on the longest sentence says nothing about the middle of the
    distribution, which is where a page gets heavy."""
    found = sentences(external_prose)
    long = [s for s in found if len(s.split()) > LONG_SENTENCE_WORDS]
    share = len(long) / len(found)
    assert share <= MAX_LONG_SENTENCE_SHARE, (
        f"{len(long)} of {len(found)} sentences run over {LONG_SENTENCE_WORDS} words "
        f"({share:.0%}, ceiling {MAX_LONG_SENTENCE_SHARE:.0%}); "
        f"median is {statistics.median(len(s.split()) for s in found)} words")


@pytest.mark.parametrize("pattern,instead", sorted(RETIRED.items()))
def test_the_external_page_uses_no_word_context_md_retired(
        external_prose, pattern, instead):
    """The glossary is only worth writing if a page cannot quietly leave it.

    Searched on the page's prose and outside the two required quotes, which is
    exactly the text an author controls.
    """
    hits = [block for block in external_prose
            if re.search(pattern, block, re.IGNORECASE)]
    assert not hits, (
        f"'{pattern}' is retired; say {instead}. In CONTEXT.md. Found in:\n"
        + "\n".join(f"  {block[:160]}" for block in hits[:5]))
