# BCI dashboard

Two self-contained HTML pages, one per audience, built from the same
measurement pass:

1. **How well does Pl@ntNet name BCI drone close-ups today?**
   `dashboard/build_external.py` reports top-1 accuracy per species, each with
   its support count, its calibration, and the reason its status was assigned.
   This is the page that leaves the lab.
2. **Which photos should botanists label next?** `dashboard/build_internal.py`
   reports a send-first queue and species-grouped batches. The page is a way to
   check the order; the deliverable is `send_batches.csv` beside it, which the
   labelling script reads.

`dashboard/build_simple.py` is a third page, a one-screen overview of both for a
reader who wants neither in full.

A page is a single file you can open, email, or drop on a share. It is rebuilt
offline from files already on disk: a Labelbox export of botanist labels, plus
cached Pl@ntNet responses.

## How a page gets made

```
   fetch side                          build side
   needs API keys                      needs only disk + stdlib

   predict/    ─┐
   labelling/   ├─>  files  ─> measure.py ─> ten CSVs ─> build_*.py ─> HTML page
   (Pl@ntNet,  ─┘    on disk    (score        (snapshot)   (render and
    Labelbox)                    every                      cross-check)
                                 photo)
```

Fetching needs a key and the network; measuring and building need neither, so the
same files always give the same page. Each builder re-reads the snapshot CSVs and
aborts on any number that disagrees.

## What a number on a page means

- Every published number carries its population and its support count.
- A photo prediction comes from a fixed 1280x1280 centre crop, 13.7% of a
  4000x3000 frame, while a botanist draws crowns anywhere in the frame. The
  crop-coverage gate (`MIN_CROP_COVERAGE`, 0.50) asks whether the species that
  covers most of the *crop* covers at least half of it, which is not the same
  question as whether the frame's labelled species does. On the dashboard path
  it is a diagnostic reported as a sweep, not a filter behind a headline:
  `coverage_gate.csv` reports gated beside ungated and the pages score the
  ungated population. `labelling/next_batch.py` does use it as a filter when
  choosing candidates.
- The headline this repo publishes is measured region-aligned, not on that crop:
  one identify call per labelled crown, pooled to the frame by box area, on 300
  frames frozen before the numbers existed. `input/confirmatory_result_2026-08.csv`
  holds it and `bci-dashboard-docs/hypothesis.md` fixed the design in advance. It
  is a per-frame rate over 72 species, and the crowns come from the botanist, so
  it is the cost of naming once delineation is done and not what an unaided
  pipeline would score. The page states all three limits beside the number.
- Crop and box geometry is read from what the fetch recorded, so the numbers stay
  true if the crop ever changes.
- A miss counts only within a known population. Out-of-scope species and
  in-checklist misses are separate groups, and `predict/fetch_checklist.py`
  decides which a species belongs to. A species missing from a cached top-5 list
  is unproven either way until it does.

Definitions of every published number, the camera-gap decomposition, and the
trend caveats live in the sibling `bci-dashboard-docs/metrics.md`.

## What the pages score today

The pages score one row per photo, bucketed by confidence and support. Four other
analyses run and write their own output, which `dashboard/core.py` does not read:

| Analysis | Writes | Status |
|---|---|---|
| Crown-level scores (`predict/crown_accuracy.py`) | scores cut from the crown boxes in `data/crowns_export/` | off-page |
| Embedding-ranked queue (`labelling/rank_unsent.py`) | a CoreSet order in `data/next_batch/queue_ranked.csv` | off-page |
| Tiles (`dashboard/score_tiles.py`) | `photo` vs `tiles` vs `tiles@crop` on one ground truth | off-page |
| Crop-coverage gate (`dashboard/measure.py`) | gated vs ungated in `coverage_gate.csv` | off-page |

## Layout

| | |
|---|---|
| `dashboard/` | measure, score, and build the pages. Stdlib only |
| `predict/` | Pl@ntNet calls: per photo, per crown box, tiles, embeddings, checklist. The only side that needs an API key |
| `labelling/` | Labelbox side: fold an export into ground truth, rank and send batches, fold results back |
| `bin/refresh.sh` | the full chain, above |
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
python3 dashboard/build_external.py --out build/model_health_dashboard.html
python3 dashboard/build_internal.py --out build/label_queue_dashboard.html
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
`dotenv`, and skip themselves when those are absent, so a system interpreter
runs about two thirds of the suite and still reports a pass. `-ra` is on by
default, so every skip prints its reason.
