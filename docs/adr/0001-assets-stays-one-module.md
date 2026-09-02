# ADR 0001: `dashboard/assets.py` stays one module

- Status: superseded in part by ADR 0003
- Date: 2026-09-01

The stylesheet and the script left this module on 2026-09-02, under the
condition that `tests/test_style.py` checks the coupling this ADR said
nobody could. The rest of it stands: the renderers are not split by kind
of output.

## Context

`dashboard/assets.py` is 648 lines. It looks like a grab bag, and an architecture
review will keep proposing to split it: escaping and formatting in one module,
tables in another, inline SVG in a third, layout in a fourth. The split is
tempting because the functions have no calls between them. Sixteen of the
seventeen are leaf renderers.

The 648 lines are not what they look like. Lines 31 to 209, 204 of them, are
`_BASE_CSS`, `_EXTRA_CSS` and `JS`: one stylesheet and one script, emitted once
into every page. The remaining lines are the renderers that produce markup
against that stylesheet. `table` writes `class="tscroll"`, `panel` writes
`class="panel"` and an `id` that the rule `details.panel:target>summary` selects
on, `status_tag` writes the status classes `status_legend` documents, and
`svg_hbar` and `svg_weight_pair` size their geometry with `_text_w`, a shared
font metric that has to agree with the font the stylesheet sets.

## Decision

`dashboard/assets.py` stays one module. Proposals to split it by kind of output,
tables, SVG, layout, escaping, are declined.

This is not a rule against ever moving anything out of the file. It is a rule
against splitting the renderers apart from the stylesheet they render against.

## Rationale

Apply the deletion test to the split: does it concentrate complexity, or move it?

It moves it. The coupling between a renderer and its CSS class is real and it
does not go away. Today it is local: the class a function emits and the rule
that styles it are in one file, so dropping an unused rule is a one file edit
and an unstyled element is visible in the same diff. Split the module and that
coupling turns into an import edge plus a convention nobody can check. The
markup lives in `tables.py` and the class it needs lives in `styles.py`, and
nothing fails when the two drift. The retirement of `build_simple.py` on this
branch is the evidence: deleting `threshold_card` also deleted the
`.rule-card`, `.chip` and `.rule-badge` rules, in the same file, in one edit,
and the byte comparison of the rendered pages proved nothing else moved. That
edit is a cross module refactor under the split.

The split also fails the interface test. `assets.py` has one job stated in one
sentence, produce the page's markup and the stylesheet it needs, and its
interface is seventeen small pure functions. Four modules with four import
lists is a wider interface describing the same implementation. That is the
definition of making a module shallower.

The functions not calling each other is the wrong signal to read. Leaf
renderers sharing one stylesheet is what a rendering module looks like when it
is working.

## What this ADR does not cover

`weight_pair_ok` at `assets.py:635` is not a rendering primitive. It answers a
question about the data, and `history.verify_snapshot` calls it. It does not
belong in this module and moving it out is not the split this ADR declines.

Nothing here argues against `assets.py` growing tests. It had none when this was
written, and the absence was a reason architecture reviews kept reaching for the
knife: an untested module reads as an unowned one.
