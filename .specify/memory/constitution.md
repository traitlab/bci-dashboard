<!--
Sync Impact Report
- Version change: none → 1.0.0 (initial ratification)
- Modified principles: none (first version)
- Added sections: Core Principles I-V, Technology Constraints, Development Workflow & Quality Gates, Governance
- Removed sections: none
- Derived from: README.md objectives (2026-08-12 call), bci-dashboard-docs/metrics.md, tests/, requirements.txt
- Follow-up TODOs: none
-->

# BCI Dashboard Constitution

## Core Principles

### I. Every Number Recomputed Offline

The dashboard MUST be reproducible from disk alone: cached API responses, a Labelbox
export, and the tracked box files. Building a page MUST NOT make a network call, read a
credential, or depend on a service being up. Fetching lives in `predict/` and
`labelling/`; measuring and rendering live in `dashboard/` and consume only what fetching
already wrote down.

Rationale: the pages are shown in meetings and handed to collaborators who have no
Labelbox access and no API key. A number that cannot be recomputed on a plane is not a
number anyone can check.

### II. Provenance Before Presentation

Every published figure MUST carry the population it was computed over, the support count
behind it, and the reason a status was assigned. Where a filter changes the population,
both sides MUST be reported side by side rather than one being chosen silently (the
`T = 0.50` crop-coverage gate is the standing example). A figure whose source cannot be
named in the repo MUST NOT be published, and a figure inferred from a proxy MUST say so.

Rationale: the project's failure mode is not a wrong chart, it is a right-looking number
whose population nobody remembers. Absence of a species in cached top-5 lists is not
evidence the model cannot name it, and the two MUST stay distinguishable.

### III. Score What The Model Saw

A prediction MUST be scored against ground truth drawn over the same pixels the model was
sent. The crop or box geometry MUST be recorded next to the answer it produced, in photo
pixels, at fetch time. Downstream code MUST read that recorded geometry and MUST NOT
recompute it from a constant.

Rationale: predictions come from a fixed centre crop covering 13.7% of the frame while
crowns are drawn anywhere in it. Recomputing the rectangle from a constant makes a frame
that breaks the constant invisible. Recording it makes per-crown and, later, per-tile
scoring the same code path rather than a rewrite.

**Known deviation, recorded 2026-08-20.** This principle states the target, not
the current state. `ingest_photos.py:239` writes a `crop` block, but zero of the
7,699 cached predictions carry one: the stamp postdates the corpus. Meanwhile
`crop_overlap.py:38-41` still reconstructs the rectangle from `FRAME_W=4000`,
`FRAME_H=3000`, `CROP_SIZE=1280`. Closing the gap means re-ingesting, so plans
may cite this deviation instead of resolving it. Plans MUST NOT widen it.

### IV. Test The Joins And The Geometry

Any change to name reconciliation, crop or box geometry, or the GT-to-prediction join MUST
ship with `pytest` cases in `tests/`, runnable as `.venv/bin/pytest`.
Cases MUST use the shapes the real inputs contain, not invented ones. A join that fails
silently, degrading into a plausible diagnostic instead of an error, MUST have a test
pinning the degradation.

Rationale: these are the code paths every published number passes through, and their
failures are quiet by construction.

### V. The Output Is A List Someone Can Act On

The dashboard answers two questions in order: where the model stands today, and what to
label next. The second answer MUST be an ordered queue and species-grouped batches the
labelling team can dispatch, not a chart to interpret. Prioritisation MUST cover both the
head, by prediction confidence, and the tail, by embedding novelty, because confidence
says nothing about species with almost no labels.

Rationale: a dashboard that ends in a figure moves no work. Trend lines were dropped for
this reason: what matters is the state of the model and labels in hand.

## Technology Constraints

- `dashboard/` is **stdlib only**. No pandas, no numpy, no template engine, no web
  framework. Third-party imports there are a breaking change to this constitution.
- `predict/` and `labelling/` MAY use the packages in `requirements.txt`
  (`labelbox`, `requests`, `python-dotenv`, `pyyaml`, `Pillow`; `numpy`/`pandas` only on
  the `aggregate_survey.py` path).
- Secrets live in `.env` and MUST NOT be committed. `PLANTNET_API_KEY` is required only by
  the fetch scripts.
- `data/`, `snapshots/`, and `build/` are generated and gitignored. `input/boxes/` is
  tracked because the frame list defines the population.
- Every path MUST be overridable by environment variable (`BCI_DASHBOARD_REPO`,
  `BCI_DASHBOARD_DATA`, `BCI_DASHBOARD_SNAPSHOTS`, `BCI_WCVP_CACHE`) and MUST default to
  the checkout.
- The end-to-end path stays a single entry point: `bin/refresh.sh` runs
  export → GT merge → measure → rebuild → snapshot.

## Development Workflow & Quality Gates

- Before a change lands: `.venv/bin/pytest` passes, and `bin/refresh.sh`
  completes against a real export if the change touches measurement or rendering.
- A change to what a number means MUST update `bci-dashboard-docs/metrics.md` in the same change. The
  metric definition and its implementation MUST NOT drift.
- Snapshots are dated and immutable. Recomputation writes a new
  `snapshots/model-health-<date>/`; it does not edit an old one.
- Feature work follows the Spec Kit loop: `/speckit-specify` → `/speckit-clarify` →
  `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`, with artifacts in
  `specs/NNN-slug/`. Small fixes and debugging do not require it.
- Spec artifacts are versioned with the code. When intended behaviour changes, the spec
  changes in the same branch as the implementation.

## Governance

This constitution supersedes ad hoc practice in this repository. Where a plan, task list,
or review conflicts with it, this document wins.

- Amendments require a change to this file with an updated Sync Impact Report, a version
  bump, and a one-line rationale.
- Versioning is semantic: MAJOR for removing or redefining a principle, MINOR for adding
  a principle or materially expanding one, PATCH for wording and clarification.
- Every plan produced by `/speckit-plan` MUST include a Constitution Check. Added
  complexity, a new dependency in `dashboard/`, or a number published without its
  population MUST be justified in writing or dropped.
- Runtime development guidance for agents lives in `README.md` and `bci-dashboard-docs/metrics.md`.

**Version**: 1.0.1 | **Ratified**: 2026-08-20 | **Last Amended**: 2026-08-20
