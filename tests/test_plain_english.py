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
    # "top-1" and "top-5" were retired here on 2026-09-01 and brought back on
    # 2026-09-03: the reviewer asked for the metric's own name on the call, and a
    # page that never names it leaves a reader translating in their head. The
    # plain-English sentence stayed as the gloss under the name, so nothing was
    # lost. If you are retiring them again, change CONTEXT.md in the same edit.
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


# How much a reader is asked to read before they reach the thing they came for.
#
# Two caps, both on the page rather than on the source, and both counted in
# sentences because that is the unit a reader gives up in.
#
#   * A `<p class="note">` is an aside. Four sentences is an aside; the fifth
#     is a second paragraph wearing the first one's clothes.
#   * A panel's intro is every paragraph between the panel's summary and its
#     first table. Eight sentences in total, because the table is what the
#     panel is for and a reader who has to scroll past a page of prose to
#     reach it reads neither.
#
# Text worth keeping and over a cap goes into a `<details class="more">` block,
# which this skips: a reader who wants the long version opens it, and a reader
# who does not is not charged for it. That is the one escape, and it is an
# escape from the length rule only. Everything inside such a block is still
# prose and is still held to every other rule in this file.
MAX_NOTE_SENTENCES = 4
MAX_PANEL_INTRO_SENTENCES = 8

# The notes the sentence cap does not reach, each named by how it opens and
# each with the reason it is here. A guard is not an aside: it exists to stop
# one specific misreading, it has to name both populations it is separating,
# and a guard a reader has to open is not a guard. Cutting one to four
# sentences would cost a sentence a reader needs to not subtract one rate from
# the other. This list is the place that decision is made out loud. Do not add
# to it to get a long note past the cap: the cap is the rule, and `more()` is
# the escape.
GUARD_NOTES = (
    "Does the test score lean on flights the labels already know?",
)

_MORE = re.compile(r'<details class="more".*?</details>', re.DOTALL | re.IGNORECASE)
_NOTE = re.compile(r'<p class="note"[^>]*>(.*?)</p>', re.DOTALL | re.IGNORECASE)
_PANEL_SUMMARY = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.DOTALL | re.IGNORECASE)


def _without_the_long_version(html: str) -> str:
    """The page minus every block a reader has to open to read."""
    return _MORE.sub(" ", html)


def test_no_note_on_a_public_page_runs_past_four_sentences(public_page):
    """An aside is four sentences. The fifth is a paragraph in disguise."""
    name, html = public_page
    over = []
    for body in _NOTE.findall(_without_the_long_version(html)):
        found = sentences(prose(f"<p>{body}</p>"))
        if found and found[0] in GUARD_NOTES:
            continue
        if len(found) > MAX_NOTE_SENTENCES:
            over.append((len(found), " ".join(found)))
    assert not over, (
        f"{name}: {len(over)} note(s) over {MAX_NOTE_SENTENCES} sentences. Cut them, "
        f"or move the long version into a <details class=\"more\"> block:\n"
        + "\n".join(f"  [{n} sentences] {t[:200]}" for n, t in sorted(over, reverse=True)))


def test_the_long_version_is_still_prose_every_other_rule_reads(public_page):
    """The escape is from the sentence count, and from nothing else.

    A block a reader has to open is the one place on the page where a sentence
    could be parked out of reach: the two caps skip it, and if `prose` skipped
    it too, a retired word or a 40-word sentence would live there unmeasured.
    So this holds the other direction. Every block carries a summary line a
    reader can decide on, it carries prose behind it, and every sentence of
    that prose is in what `prose` returns for the whole page, which is what
    every other check in this file reads.
    """
    name, html = public_page
    reads = set(prose(html))
    for block in _MORE.findall(html):
        title = _PANEL_SUMMARY.search(block)
        assert title and _text(title.group(1)), (
            f"{name}: a <details class=\"more\"> block with no summary line. A reader "
            f"decides whether to open it on that line, so it has to say what is inside.")
        body = sentences(prose(_PANEL_SUMMARY.sub(" ", block)))
        assert body, (
            f"{name}: <details class=\"more\"> block \"{_text(title.group(1))}\" holds no "
            f"prose. Either it is empty or its text is outside a paragraph, and text "
            f"outside a paragraph is text no check in this file reads.")
        unread = [s for s in body if not any(s in block for block in reads)]
        assert not unread, (
            f"{name}: {len(unread)} sentence(s) behind \"{_text(title.group(1))}\" are "
            f"invisible to prose(), so the retired words and the sentence length are "
            f"unmeasured there:\n" + "\n".join(f"  {s[:160]}" for s in unread[:5]))


def test_no_panel_on_a_public_page_buries_its_table_under_its_intro(public_page):
    """What a panel is for is its table. The prose above it is the toll."""
    name, html = public_page
    over = []
    # Split rather than match a closing tag: panels nest, and the intro is
    # everything from this panel's own summary to the first table under it.
    for chunk in _without_the_long_version(html).split('<details class="panel"')[1:]:
        if "<table" not in chunk:
            continue
        intro = chunk.split("<table", 1)[0]
        title = _PANEL_SUMMARY.search(intro)
        found = sentences(prose(_PANEL_SUMMARY.sub(" ", intro)))
        if len(found) > MAX_PANEL_INTRO_SENTENCES:
            over.append((len(found), _text(title.group(1)) if title else "?"))
    assert not over, (
        f"{name}: {len(over)} panel intro(s) over {MAX_PANEL_INTRO_SENTENCES} "
        f"sentences before the table the panel exists for:\n"
        + "\n".join(f"  [{n} sentences] {t}" for n, t in sorted(over, reverse=True)))


# What a backticked span on a public page is allowed to be.
#
# A `<code>` span is how this repository writes an identifier: a repository
# path, a script name, a command flag, a CSV column. Every one of those is a
# thing a reader outside the team cannot open, cannot run and cannot look up,
# so on a public page it is a dead end dressed as a detail. Two kinds survive.
#
#   * A CSV the page itself links, because `bin/publish_pages.sh` copies every
#     file a published page links with an `href` and it therefore resolves on
#     the site. The allowlist is read off each page's own links rather than
#     typed, so a CSV that stops being linked stops being allowed in the same
#     edit.
#   * A species name, which is backticked on some pages to set a Latin
#     binomial off from the sentence around it. A reader can look one up.
#
# Anything else is fixed in the source that wrote it, not added here. The team
# copy of the queue page is deliberately not checked: it exists to carry the
# commands and column names the public page drops.
_CODE_SPAN = re.compile(r"<code\b[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE)
_LINKED_CSV = re.compile(r'href="([A-Za-z0-9_]+\.csv)"')
# Genus, species, and at most one more word for an author abbreviation or a
# subspecies rank. Latin binomials are the only two-word identifier here.
_SPECIES_NAME = re.compile(r"^[A-Z][a-z-]+ [a-z-]{2,}( [a-z.]+)?$")


@pytest.fixture(params=("external_page", "internal_page"))
def public_page(request):
    """The two pages published to the site, one at a time."""
    return request.param, request.getfixturevalue(request.param)[0]


def test_no_public_page_backticks_something_a_reader_cannot_open(public_page):
    """A public page names no repository path, script, flag or column."""
    name, html = public_page
    served = set(_LINKED_CSV.findall(html))
    body = _NOT_PROSE.sub(" ", html)
    spans = {_text(span) for span in _CODE_SPAN.findall(body)}
    stray = sorted(s for s in spans - served
                   if s and not _SPECIES_NAME.match(s))
    assert not stray, (
        f"{name} backticks {stray}, which a reader outside the team cannot open, "
        f"run or look up. Say it in words, or link the copy the site serves. Only "
        f"a CSV this page links ({sorted(served)}) or a species name may stay.")


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
