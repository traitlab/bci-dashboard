# ADR 0002: `dashboard/explain.py` stays a separate module

- Status: accepted
- Date: 2026-09-01

The line counts and line numbers below are the ones this was argued from. Today
`explain.py` is 293 lines and `panels.py` is 427, since the queue page's panels
moved to `queue_panels.py`. The argument does not turn on the exact figures:
absorbing one into the other still puts a single module past the 500-line
convention.

## Context

`dashboard/explain.py` is 230 lines and nothing imports it except
`dashboard/panels.py`. That is the textbook shape of a hypothetical seam: one
adapter, not two. An architecture review will keep proposing to dissolve it into
`panels.py` on exactly that reasoning, and a sweep of `dashboard/` did propose
it.

The interface is four symbols on one import line, `panels.py:32`:
`candidates_panel`, `weighting_panel`, `method_panel` and `BAND_SHORT`. The
three functions are each wrapped by a one-line adapter in `panels.py`, at lines
855, 875 and 885, which does nothing but pull the arguments off the prepared
context. `explain.py` imports `core` and `assets` and does not import `panels`,
so the dependency runs one way with no cycle.

Four symbols in front of 230 lines is a deep module by the definition this
project uses. The proposal inverts the usual argument: it would delete a module
whose interface is already small relative to its implementation.

The receiving module is the problem. `panels.py` is 1,017 lines against a
workspace convention of 500. Absorbing `explain.py` takes it to roughly 1,247.

## Decision

`dashboard/explain.py` stays a separate module. Proposals to dissolve it into
`panels.py` are declined unless the facts above change.

## Consequences

Apply the deletion test: would deleting `explain.py` concentrate complexity or
just move it? It moves it. The 230 lines land unchanged in a file that is
already twice the size the convention allows, and they stop being
distinguishable from their new neighbours. The three panels in `explain.py`
answer "how was this number made"; the panels in `panels.py` report the number.
That distinction is the module boundary, and it is the reason a reader can find
the weighting explanation without reading 1,000 lines of assembly.

The one-adapter rule still applies, and it points the other way here. A single
adapter is evidence a seam might be imaginary when the module behind it is thin.
When the module behind it is 230 lines of self-contained prose rendering with no
back edge, the single adapter is evidence the seam is doing its job: nothing
else has needed to reach across it.

If the direction of travel is ever to reduce module count in `dashboard/`, the
candidate is `panels.py`, not `explain.py`.

## What this ADR does not cover

- **`BAND_SHORT`.** It is the one symbol crossing the seam that is not a panel.
  `panels.py` reads it at lines 605 and 618 for two panels that report support
  bands rather than explain them. That is a genuine leak and this ADR does not
  bless it. Moving the band vocabulary somewhere both modules can read it
  without one importing the other is open.
- **Splitting `panels.py`.** Four ways by audience was proposed and deferred as
  a naming call. This ADR says only that merging into it is wrong, not that
  splitting it is right.
- **`explain.py`'s own contents.** The known colour-ramp limitation recorded in
  its `BAND_COLOR` comment, that the ramp carries no order without hue, is a
  palette question and is untouched here.

## Later: 2026-09-02

`candidates_panel` is gone. The "Why only five guesses per photo" panel was
dropped from the external page, and with no page carrying it the function and
its adapter went too. The interface is now three symbols, `weighting_panel`,
`method_panel` and `BAND_SHORT`, in front of a correspondingly smaller module.

This weakens the ratio the decision rested on without reversing it: the seam is
still one-way, still small relative to what it hides, and merging into
`panels.py` would still buy nothing. If a second panel leaves, the argument is
worth reopening rather than assumed.
