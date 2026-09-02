# BCI dashboard

Two self-contained HTML pages, built from the same measurement pass. Each is a
single file you can open, email, or drop on a share, rebuilt offline from files
already on disk: a Labelbox export of botanist labels, plus cached Pl@ntNet
responses.

1. **How well does Pl@ntNet name BCI trees?** `dashboard/build_external.py`:
   per species, how often the first guess is right, on how many labelled frames,
   how well confidence tracks that, and why the species carries its status. The
   page that leaves the lab.
2. **What to label next.** `dashboard/build_internal.py`: a send-first queue and
   species-grouped batches. The page checks the order; the deliverable is
   `send_batches.csv` beside it, which the labelling script reads.

`dashboard/build_export_only.py` scores one Labelbox export on its own, so a new
batch never mixes into the running total. A spot check on a delivery, not a page
anyone publishes.

`CONTEXT.md` names every term the pages use and the plain words a page says
instead. `tests/test_plain_english.py` checks that page prose follows it.

## How a page gets made

```
   fetch side                          build side
   needs API keys                      needs only disk + stdlib

   predict/    ─┐
   labelling/   ├─>  files  ─> measure.py ─> nine CSVs ─> build_*.py ─> HTML page
   (Pl@ntNet,  ─┘    on disk    (score        (snapshot)   (render and
    Labelbox)                    every                      cross-check)
                                 photo)
```

Fetching needs a key and the network; measuring and building need neither, so the
same files always give the same page. Each builder re-reads the snapshot CSVs and
aborts on any number that disagrees.

## What a number on a page means

- Every published number carries its population and its support count.
- **The headline is measured crown by crown**, not on the centre crop: one
  identify call per labelled crown, pooled to the frame by box area, over 300
  frames frozen before the numbers existed
  (`input/confirmatory_result_2026-08.csv`; `bci-dashboard-docs/hypothesis.md`
  fixed the design in advance). Per frame, 72 species, crowns drawn by the
  botanist, so it is the cost of naming trees already found. The page states all
  three limits beside the number.
- **A photo prediction comes from a fixed 1280x1280 centre crop**, 13.7% of a
  4000x3000 frame, while a botanist draws crowns anywhere in it. The
  crop-coverage gate (`MIN_CROP_COVERAGE`, 0.50) asks whether the species
  covering most of the *crop* covers half of it, which is not the same question.
  On the dashboard path it is a diagnostic, not a filter: `coverage_gate.csv`
  reports gated beside ungated and the pages score ungated.
  `labelling/next_batch.py` does filter on it.
- Crop and box geometry is read from what the fetch recorded, so the numbers stay
  true if the crop ever changes.
- A miss counts only within a known population. `predict/fetch_checklist.py`
  decides whether a species is out of scope or in the checklist, and a species
  missing from a cached list of five names is unproven either way.

Every published number is defined in the sibling
`bci-dashboard-docs/metrics.md`, with the camera-gap decomposition and the trend
caveats.

## What the pages score today

One row per photo, grouped by confidence and by how many labelled frames a
species has. Three other analyses write output `dashboard/core.py` never reads:

| Analysis | Writes |
|---|---|
| Crown-level scores (`predict/crown_accuracy.py`) | scores cut from the crown boxes in `data/crowns_export/` |
| Embedding-ranked queue (`labelling/rank_unsent.py`) | a CoreSet order in `data/next_batch/queue_ranked.csv` |
| Crop-coverage gate (`dashboard/measure.py`) | gated vs ungated in `coverage_gate.csv` |

## Layout

| | |
|---|---|
| `dashboard/` | measure, score, and build the pages. Stdlib only |
| `predict/` | Pl@ntNet calls: per photo, per crown box, embeddings, checklist. The only side that needs an API key |
| `labelling/` | Labelbox side: fold an export into the labels, rank and send batches, fold results back |
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

Or one export on its own, with no snapshot and no corpus total:

```bash
python3 dashboard/build_export_only.py --export path/to/export.ndjson
```

## Configure

Copy `.env.example`. `.env` is gitignored and is the only place a key belongs.
`predict/` needs `PLANTNET_API_KEY`; `labelling/` needs `LABELBOX_API_KEY` too.

Which Labelbox workspace those scripts point at is not secret, so it sits in
`config.yaml`, visible before a run touches anything. `LABELBOX_DATASET_ID` and
`LABELBOX_PROJECT_ID` override it. Paths default to the checkout:
`BCI_DASHBOARD_REPO`, `BCI_DASHBOARD_DATA`, `BCI_DASHBOARD_SNAPSHOTS`,
`BCI_WCVP_CACHE`.

## Test

```bash
uv pip install -r requirements-dev.txt          # once, into .venv
.venv/bin/pytest
```

Name the interpreter. Tests covering `predict/` skip themselves when `PIL`,
`yaml` or `dotenv` is absent, so a system interpreter runs about two thirds of
the suite and still reports a pass. `-ra` is on, so every skip prints its
reason.
