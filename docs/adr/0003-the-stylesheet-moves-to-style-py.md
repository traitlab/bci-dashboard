# ADR 0003: the stylesheet moves out of `assets.py` into `style.py`

- Status: accepted
- Date: 2026-09-02
- Supersedes: ADR 0001, in part

## Context

ADR 0001 declined every proposal to split `dashboard/assets.py`, and named one
split in particular as the thing it was protecting against: "splitting the
renderers apart from the stylesheet they render against". Its argument was that
the coupling between a class a renderer writes and the rule that styles it is
real, that today it is local and visible in one diff, and that a split turns it
into "an import edge plus a convention nobody can check".

The file was 631 lines. `CLAUDE.md` says to keep files under 500. Four files in
`dashboard/` were over it, and this was one.

## Decision

`_BASE_CSS`, `_EXTRA_CSS`, `CSS`, `JS` and the five element ids move to
`dashboard/style.py`. `assets.py` keeps the renderers and drops to 331 lines.

The condition attached to this decision is `tests/test_style.py`: every class a
builder writes has a rule, and every rule matches something. Both directions
fail the suite, not the page.

## Rationale

ADR 0001's premise was right and its conclusion no longer follows, because the
thing it called uncheckable is now checked.

Two couplings run between the markup and the stylesheet, and they are not the
same strength. The element ids the script looks up and `filterable_table`
writes were the tighter one: two literals in two places, with nothing tying
them. They are now one definition in `style.py` that `assets.py` imports, so
the import edge ADR 0001 warned about is what removed the drift, not what
created it. The class names are the looser one, and `tests/test_style.py`
holds both ends of it.

"Visible in the same diff" was never a check. It is a claim about who edits
what, and it holds only while one person edits both halves in one sitting. The
evidence ADR 0001 cites, the `build_simple.py` retirement, is a case where that
happened, not a mechanism that makes it happen. A test is a mechanism.

The interface test ADR 0001 applies still passes after the split, because the
split is not the four-way one it was written against. `assets.py` has one job in
one sentence, produce the page's markup, and `style.py` has one, hold the
stylesheet and the script, which are vendored text rather than functions. Two
modules, not four, and the boundary falls where the maintenance actually
differs: `_BASE_CSS` is a hand-kept subset of labelfirst's, reapplied by hand
when upstream moves, and none of the renderers are.

## What this ADR does not cover

ADR 0002 stands. `explain.py` is unaffected.

The rest of ADR 0001 stands too. This is not a licence to split the renderers
by kind of output. Tables, SVG, layout and escaping stay in `assets.py`, and
the deletion-test argument against separating them is unchanged: those
functions share `_text_w`, share the status vocabulary, and would gain four
import lists for one implementation.
