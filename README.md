# BCI dashboard

Two self-contained HTML pages, built from one measurement pass. Each is a single
file you can open, email, or drop on a share. Both are built offline from files
already on disk: a Labelbox export of botanist labels, plus cached Pl@ntNet
responses.

1. **How well does Pl@ntNet name BCI trees?** `dashboard/build_external.py`: per
   species, how often the first guess is right, on how many labelled frames, and
   why the species carries its status. The page that leaves the lab.
2. **What to label next.** `dashboard/build_internal.py`: a send-first queue and
   species-grouped batches. The page checks the order; the deliverable is
   `send_batches.csv`, one of the tables `measure.py` writes, which the
   labelling script reads.

`CONTEXT.md` names every term the pages use and the plain words they say
instead. `tests/test_plain_english.py` holds the pages to it.

## How a page gets made

```
   fetch side                          build side
   needs API keys                      needs only disk + stdlib

   predict/    ─┐
   labelling/   ├─>  files  ─> measure.py ─> nine CSVs  ─> build_*.py ─> HTML page
   (Pl@ntNet,  ─┘    on disk    (score      (build/        (render and
    Labelbox)                    every       tables)        cross-check)
                                 photo)
```

The same files always give the same page. Each builder recomputes every number
it prints and aborts if `build/tables` disagrees. A dated `snapshots/` folder is
a record of a day the labels moved; no build reads one back.

## What a number means

Every number says which frames it covers and how many labelled frames it
rests on. Each one is defined in the sibling `bci-dashboard-docs/metrics.md`.
Three things the pages say out loud, because missing them means reading the
numbers wrong:

- **The headline is measured crown by crown**: one call per labelled crown,
  pooled to the frame by box area, on 300 frames frozen before the numbers
  existed. `bci-dashboard-docs/hypothesis.md` fixed the design in advance. It
  is the cost of naming trees already found, not of finding them.
- **Every other rate comes from a fixed 1280x1280 centre crop**, 13.7% of the
  frame, while a botanist draws crowns anywhere in it. The pages score every
  frame, with no coverage condition applied. `MIN_CROP_COVERAGE` (0.50) asks a
  different question: does the frame's own label fill half of the *crop* the
  model was sent. A crop filled by some other species answers about that tree
  instead, so it is rejected however full it is. Here the condition only
  reports, in `coverage_gate.csv`. `labelling/next_batch.py` is what filters
  on it, and asks the same two things.
- A miss counts only inside a known population. A species missing from a cached
  list of five names is unproven either way.

Crop and box geometry comes from what the fetch recorded, never a constant.
Three of the nine CSVs are evidence a person opens rather than page input:
`filter_gain.csv`, `name_reconciliation.csv` and `coverage_gate.csv`.
`measure.NOT_READ_BACK_BY_A_BUILD` names them. Every other number a page prints
is recomputed and compared against `build/tables` on every build. So is the
batch assignment in `send_batches.csv`, not just its shape: a change to the
packing rule has to move the file, or the build stops.

## Layout

| | |
|---|---|
| `dashboard/` | measure, score, build the pages. Stdlib only |
| `predict/` | Pl@ntNet calls: per photo, per crown box, embeddings, checklist. Needs `PLANTNET_API_KEY` |
| `labelling/` | Labelbox side: fold an export in, rank and send batches, fold results back. Needs `LABELBOX_API_KEY` |
| `docs/adr/` | decisions taken and declined, with the reasoning. Read before splitting a module |
| `bin/refresh.sh` | the full chain, above |
| `input/boxes/` | crown boxes and the frame list. Tracked: the frame list defines the population |
| `data/`, `snapshots/`, `build/` | generated, gitignored |

## Run

```bash
bin/refresh.sh                          # newest export in data/exports or ~/Downloads
bin/refresh.sh path/to/export.ndjson
```

Or the measurement pass and one page alone:

```bash
python3 dashboard/measure.py --out-dir build/tables
python3 dashboard/build_external.py --out build/model_health_dashboard.html
python3 dashboard/build_internal.py --out build/label_queue_dashboard.html
```

## Configure

Copy `.env.example`. `.env` is gitignored and is the only place a key belongs:
`PLANTNET_API_KEY` for `predict/`, plus `LABELBOX_API_KEY` for `labelling/`.

Which Labelbox workspace the scripts point at is not secret, so it sits in
`config.yaml`, visible before a run touches anything. `LABELBOX_DATASET_ID`,
`LABELBOX_PROJECT_ID` and the `BCI_DASHBOARD_*` path variables override it.

## Test

```bash
uv pip install -r requirements-dev.txt          # once, into .venv
.venv/bin/pytest
```

Name the interpreter. Tests covering `predict/` skip themselves when `PIL`,
`yaml` or `dotenv` is missing, so a system interpreter runs two thirds of the
suite and still reports a pass. `-ra` is on, so every skip prints why.
