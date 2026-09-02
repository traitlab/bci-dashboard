"""What a reader can click: anchors, jump links, ids and the filter.

Split out of `test_pages.py`, which was over the workspace's 500-line rule and
holds two different kinds of assertion. That file is about whether a builder
produced a correct page. This one is about whether the page a reader opens
navigates: every jump link lands, every id the inline JS reaches for exists,
an anchor still reads as a phrase when it is pasted into a message, and the
filter can see every row.

The fixtures and the page allowlist come from `conftest.py`, so both files
build the same pages the same way.

    .venv/bin/pytest tests/test_page_navigation.py
"""

from __future__ import annotations

import re

from conftest import species_rows

# The status dropdown is the only element the inline JS tolerates missing, so
# the id-presence check below has to know which one it is.
STATUS_SELECT_ID = "status-filter"
# id -> the flag a page must carry for that element to be rendered. Both are
# looked up behind a guard in the JS, so their absence is correct, not a break.
GUARDED_IDS = {STATUS_SELECT_ID: "species_status", "show-thin": "species_thin"}

_GETELEMENTBYID = re.compile(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)")
_ID_ATTR = re.compile(r"""\bid=['"]([^'"]+)['"]""")
_SCRIPT_BODY = re.compile(r"<script>(.*)</script>", re.S)


# ---------------------------------------------------------------------------
# JS <-> HTML id coupling: derived from the JS text, not hardcoded here
# ---------------------------------------------------------------------------

def test_every_id_the_js_looks_up_exists_exactly_once(page):
    html, _, carries = page
    script = _SCRIPT_BODY.search(html)
    assert script, "no inline <script> block -- JS was not embedded"
    ids = _GETELEMENTBYID.findall(script.group(1))
    assert ids, "no getElementById calls found in the inline script"
    counts = {}
    for m in _ID_ATTR.finditer(html):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    found = {eid: counts.get(eid, 0) for eid in ids}
    if "species" in carries:
        for eid, k in found.items():
            # Two lookups are guarded in the JS: the status select, absent on a
            # page with no statuses to offer, and the show-all checkbox, absent
            # on a page that hides no rows. Every other id is dereferenced
            # straight away and has to be there exactly once.
            flag = GUARDED_IDS.get(eid)
            want = 1 if (flag is None or flag in carries) else 0
            assert k == want, (
                f"id {eid!r} (looked up by the inline JS) appears {k} times in the "
                f"page, not {want}")
    else:
        # The whole block guards on the species table and returns early without
        # one, so every id it reaches for has to be absent together. Half of
        # them present is a page that throws on the first keystroke.
        assert set(found.values()) == {0}, (
            f"page carries no species table but wires up part of the filter: {found}")


# ---------------------------------------------------------------------------
# anchors and jump lists
# ---------------------------------------------------------------------------
# These five gate behaviour shipped in fcb0aec (panel anchors, per-section jump
# lists, the table scroll wrapper) and in af4b521 (the status legend). They are
# assertions about the page, not about any builder's internals, so they run
# against every page like everything above.

def test_every_link_into_the_page_lands_on_something(page):
    """The jump lists are generated from the panels, so a broken one means the
    two have drifted apart. Since the split it also catches a link left behind
    pointing at a section that moved to the other page."""
    html, _, _ = page
    targets = set(_ID_ATTR.findall(html))
    for href in set(re.findall(r'href="#([^"]+)"', html)):
        assert href in targets, f"jump link #{href} has no target"


def test_no_anchor_carries_a_number(page):
    """An id built from a summary that states a live count changes on the next
    snapshot, and every saved link to it breaks. `panel()` rejects those, so
    this is the assertion that the guard is actually wired up."""
    html, _, _ = page
    for eid in re.findall(r'<details class="panel" id="([^"]+)"', html):
        assert not any(c.isdigit() for c in eid), f"anchor {eid!r} carries a number"


def test_no_anchor_ends_mid_phrase(page):
    """An id is a link someone pastes into a message, so it has to read as a
    phrase on its own. `slug()` keeps the first eight words, and eight words
    into a summary can land on a joining word: "how this was measured and what
    it does" says the opposite of the panel it points at. The fix is an
    explicit `anchor=` at the call site, not a longer slug."""
    html, _, _ = page
    dangling = {"and", "or", "but", "with", "in", "of", "the", "a", "an", "it",
                "for", "to", "on", "at", "is", "that", "what"}
    for eid in re.findall(r'<details class="panel" id="([^"]+)"', html):
        last = eid.rsplit("-", 1)[-1]
        assert last not in dangling, (
            f"anchor {eid!r} ends on {last!r}, so the link reads as half a "
            f"phrase. Pass anchor= at that panel's call site.")


def test_a_page_only_names_a_section_it_carries(page, pagemod):
    """Prose that says "see X" has to mean a heading on the page in front of
    the reader. The queue page once pointed at "What this cannot tell you",
    which is a section of the model-health page, so the reader hunted for a
    heading that was never going to appear. Naming the other page is fine;
    naming a heading this page does not have is not."""
    html, _, _ = page
    headings = set(re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL))
    for title, _lede in pagemod.SECTIONS.values():
        if title is None or title in headings:
            continue
        assert f"&ldquo;{title}&rdquo;" not in html, (
            f"the page quotes the section heading {title!r}, which is on the "
            f"other page. Point at the page by name instead.")


def test_each_id_is_unique(page):
    html, _, _ = page
    ids = _ID_ATTR.findall(html)
    duplicated = {i for i in ids if ids.count(i) > 1}
    assert not duplicated, f"duplicate ids: {sorted(duplicated)}"


def test_a_wide_table_scrolls_inside_its_own_box(page):
    """Without the wrapper the widest table sets the page width and every
    paragraph scrolls sideways with it on a phone."""
    html, _, _ = page
    assert len(re.findall(r"<table\b", html)) == html.count('class="tscroll"')


def test_the_filter_can_reach_every_row(page):
    """The filter reads the first cell for the name and the row's own status
    tag for the status. A row missing either is invisible to it, which reads as
    a table that loses rows when you type."""
    html, _, carries = page
    tagged = species_rows(html)
    if "species_status" not in carries:
        assert not tagged, "page carries no species status wiring but renders filterable rows"
        return
    assert tagged, "no filterable rows"
    for row in tagged:
        first = re.match(r"<tr\b[^>]*>\s*<td[^>]*>(.*?)</td>", row, re.S)
        assert first and re.sub(r"<[^>]+>", "", first.group(1)).strip(), (
            f"row has no species name to match: {row}")


def test_the_stylesheet_has_no_rule_no_page_uses(external_page, internal_page, style):
    """Dead CSS is invisible bloat: it survives every rewrite because nothing
    fails when it stops matching anything. Two classes did survive that way.

    ``JS_APPLIED`` are set by the sort and filter code at runtime, so they are
    absent from the built HTML and still live."""
    JS_APPLIED = {"asc", "desc", "hidden"}
    styled = set(re.findall(r"\.([a-zA-Z][\w-]*)", style.CSS))
    html = external_page[0] + internal_page[0]
    used = set()
    for group in re.findall(r'class="([^"]+)"', html):
        used.update(group.split())
    dead = sorted(styled - used - JS_APPLIED)
    assert not dead, f"CSS rules nothing on either page carries: {dead}"


def test_every_status_a_row_carries_is_one_the_dropdown_offers(page):
    """The filter compares the dropdown's value against the class on a row's
    status tag. They are two spellings of the same word, so a row spelling its
    status any other way is a row the dropdown can never show.

    Not the other direction: the dropdown offers every status the scoring can
    produce, and a page built from one small export legitimately has rows for
    only some of them."""
    html, _, carries = page
    if "species_status" not in carries:
        return
    offered = {v for v in re.findall(r'<option value="([^"]+)"', html) if v != "all"}
    carried = {c for row in species_rows(html)
               for c in re.findall(r'<span class="tag ([^"]+)"', row)}
    assert carried and carried <= offered, (
        f"rows carry {sorted(carried - offered)}, which the dropdown does not "
        f"offer, so those rows vanish when a reader picks any status")


def test_no_sort_key_ships_a_digit_the_sort_cannot_use(page):
    """`data-sort` exists only for JavaScript's `parseFloat`, which cannot tell
    "0.000000" from "0". The zeros are readable by nobody and were 1.5KB of a
    100KB page, so `assets.sort_key` trims them. This catches a caller that
    formats its own key and puts them back."""
    html, _, _ = page
    padded = [v for v in re.findall(r'data-sort="([^"]*)"', html)
              if "." in v and v.endswith(("0", "."))]
    assert not padded, (
        f"{len(padded)} sort keys end in a zero that changes nothing, "
        f"such as {padded[:3]}. Build them with assets.sort_key.")


def test_every_rounded_species_cell_still_sorts_on_the_figure_behind_it(page):
    """A cell showing 92.9% sorts on 0.928571, carried in `data-sort` on the
    cell itself. Drop the attribute and the table still renders and still
    sorts, on the text "92.9%", so two species rounding alike swap places and
    nothing anywhere says so."""
    html, _, carries = page
    rounded = [row for row in species_rows(html) if "%" in row]
    if "species" not in carries:
        assert not rounded
        return
    assert rounded, "the species table shows no percentage at all"
    for row in rounded:
        for cell in re.findall(r"<td[^>]*>[^<]*%</td>", row):
            assert "data-sort=" in cell, (
                f"{cell} shows a rounded percentage and sorts on the text of "
                f"it, so species that round alike sort arbitrarily")
