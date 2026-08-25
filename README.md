# BCI dashboard

How Pl@ntNet is doing on BCI drone close-ups right now, and which photos to send
to botanists next. Two self-contained HTML pages, rebuilt offline from a Labelbox
export you drop on disk plus cached API responses. Building a page makes no
network call, reads no credential, and imports nothing outside the stdlib.

## The two questions

1. **How does the model stand today?** Top-1 per species, with support counts,
   calibration, and the reason each status was assigned.
2. **What should be labelled next?** A send-first queue and species-grouped
   batches, so the answer is a list the labelling team can act on rather than a
   chart.

## Rules every number on the pages follows

- A published number carries its population and its support count.
- A photo prediction comes from a fixed 1280x1280 centre crop, 13.7% of a
  4000x3000 frame, while a botanist draws crowns anywhere in the frame. The
  crop-coverage gate (`MIN_CROP_COVERAGE`, 0.50) admits a frame only when its
  dominant labelled species covers at least half the crop. It is computed into
  `coverage_gate.csv` and reported gated against ungated there; the pages score
  the ungated population.
- Crop and box geometry is read from what the fetch recorded, never recomputed
  from a constant.
- Absence from a cached top-5 list is not evidence Pl@ntNet cannot name a
  species. Out-of-scope and in-checklist misses are different populations; only
  `predict/fetch_checklist.py` settles which is which.
- Scores are cross-checked against the committed CSVs from `dashboard/measure.py`
  on every build. A mismatch aborts the build, so a page cannot disagree with the
  measurement it was built from.

Definitions of every published number, the camera-gap decomposition, and the
trend caveats live in the sibling `bci-dashboard-docs/metrics.md`, kept out of
this repo so a stale note cannot be read as current.

## Measured, not yet on the pages

Three analyses run and write their own output, but `dashboard/core.py` does not
read them, so the pages do not show them. Do not assume otherwise:

- **Crown-level scores.** `predict/crown_accuracy.py` scores predictions cut from
  the crown boxes in `data/crowns_export/`. The pages still score one row per
  photo.
- **Embedding-ranked queue.** `labelling/rank_unsent.py` writes a CoreSet order to
  `data/next_batch/queue_ranked.csv`. The queue the pages show is bucketed by
  confidence and support instead.
- **Tiles.** `dashboard/score_tiles.py` compares `photo`, `tiles` and
  `tiles@crop` against one ground truth. Nothing on the pages reads it.
- **The crop-coverage gate.** `dashboard/measure.py` writes gated against ungated
  to `coverage_gate.csv`. Neither page shows the comparison.

## Layout

| | |
|---|---|
| `dashboard/` | measure, score, and build the pages. Stdlib only |
| `predict/` | Pl@ntNet calls: per photo, per crown box, tiles, embeddings, checklist. The only side that needs an API key |
| `labelling/` | Labelbox side: fold an export into ground truth, rank and send batches, fold results back |
| `bin/refresh.sh` | export -> GT merge -> measure -> rebuild -> snapshot |
| `input/boxes/` | crown boxes and the frame list. Tracked: the frame list defines the population |
| `data/`, `snapshots/`, `build/` | generated, gitignored |

Every module carries a docstring saying what it does and `--help` saying how to
run it.

## Run

```bash
bin/refresh.sh                          # newest export in data/exports or ~/Downloads
bin/refresh.sh path/to/export.ndjson
```

Or the measurement pass and one page alone:

```bash
python3 dashboard/measure.py --out-dir snapshots/model-health-$(date +%F)
python3 dashboard/build_simple.py --out build/simple_dashboard.html
```

## Configure

Copy `.env.example`. `.env` is gitignored and is the only place a key belongs.
The fetch scripts under `predict/` need `PLANTNET_API_KEY`; those under
`labelling/` need `LABELBOX_API_KEY` too.

Which Labelbox workspace those scripts point at is not secret, so it sits in
`config.yaml` where a reader can see what a run will touch before it runs.
`LABELBOX_DATASET_ID` and `LABELBOX_PROJECT_ID` override it.

Paths default to the checkout: `BCI_DASHBOARD_REPO`, `BCI_DASHBOARD_DATA`,
`BCI_DASHBOARD_SNAPSHOTS`, `BCI_WCVP_CACHE`.

## Test

```bash
uv pip install -r requirements-dev.txt          # once, into .venv
.venv/bin/pytest
```

Name the interpreter. The tests covering `predict/` import `PIL`, `yaml` and
`dotenv` and skip themselves when those are absent, so a system interpreter
reports a pass on two thirds of the suite. `-ra` is on by default, so every skip
prints its reason.
