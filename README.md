# BCI dashboard

Two self-contained HTML pages, built offline from files already on disk: a
Labelbox export of botanist labels, plus cached Pl@ntNet responses. Each page is
one file you can open, email, or drop on a share.

**How well does Pl@ntNet name BCI trees?** For anyone outside the lab. Per
species, how often the first guess is right, on how many labelled frames, and why
the species carries its status.

```bash
python3 dashboard/build_external.py   # writes build/model_health_dashboard.html
```

**What to label next.** For the labelling team. The send-first queue, the rule
behind it, and the command that ships a batch.

```bash
python3 dashboard/build_internal.py   # writes build/label_queue_dashboard.html,
                                      # plus send_first_queue.csv and send_batches.csv beside it
```

Both read the same measurement pass, so the two pages cannot disagree. Run it
first, or run everything at once:

```bash
python3 dashboard/measure.py --out-dir build/tables   # then either builder above
bin/refresh.sh                                        # export, measure, both pages, snapshot
bin/refresh.sh path/to/export.ndjson                  # a named export instead of the newest
```

`bin/refresh.sh` takes the newest export in `data/exports` or `~/Downloads` when
given no path.

## What to label next

Every unlabelled photo with a cached Pl@ntNet answer falls into one of four
queues, tried in this order, first match winning. The numbers below are
`dashboard/core.py` constants and the rule is `queues.queue_of_prediction`; the
page prints both from the same source.

1. **Species we barely have, or barely get right.** Fewer than 10 labelled
   frames, or right less than 70% of the time.
2. **A usually-right species, guessed weakly.** Right at least 90% of the time
   overall, but confidence under 0.50 here.
3. **Worth a look, confidence under 0.80.** Not in the two queues above, and
   Pl@ntNet is under 0.80 confident here.
4. **Confident on a well-covered species.** Confidence 0.80 or more and 10 or
   more labelled frames already. Look at these last.

Inside a queue the photo least like everything already labelled comes first, and
confidence only breaks a tie. `send_batches.csv` packs that order into batches of
100 with each species kept whole, and `labelling/dispatch_round.py` sends one
batch to Labelbox.

That order is measured. On the 1,719 frames a botanist has already named, it
covers half of their 155 species in 129 photos. A random order needs 329, and
the measured order won on every seed. `labelling/rank_queue.py --backtest` is the
check, and the queue page draws its curve. The two-part wait rule behind
queue 4 *is* measured, on frames held back for grading, and the queue page shows
every confidence line it was compared against.

## What a number means

Every number says which frames it covers and how many labelled frames it rests
on. Three things the pages repeat, because missing them means reading the
numbers wrong:

- **The headline is measured crown by crown**: one call per labelled crown,
  pooled to the frame by box area, on 300 frames frozen before the numbers
  existed. `input/confirmatory_frames_2026-08.csv` is that list. It is the cost
  of naming trees already found, not of finding them.
- **Every other rate comes from a fixed 1280x1280 centre crop**, 13.7% of the
  frame, while a botanist draws crowns anywhere in it. The pages score every
  frame with no coverage condition applied. `MIN_CROP_COVERAGE` (0.50) asks a
  different question: does the frame's own label fill half of the *crop* the
  model was sent. Here it only reports, in `coverage_gate.csv`.
  `labelling/next_batch.py` is what filters on it.
- **A miss counts only inside a known population.** A species missing from a
  cached list of five names is unproven either way.

Crop and box geometry comes from what the fetch recorded, never a constant.

## How a page gets made

```
   fetch side                          build side
   needs API keys                      reads the files on disk

   predict/    ─┐
   labelling/   ├─>  files  ─> measure.py ─> nine CSVs  ─> build_*.py ─> HTML page
   (Pl@ntNet,  ─┘    on disk    (score      (build/        (render and
    Labelbox)                    every       tables)        cross-check)
                                 photo)
```

The same files always give the same page. Each builder recomputes every number
it prints and aborts if `build/tables` disagrees, batch assignment included: a
change to the packing rule has to move `send_batches.csv`, or the build stops.
Three of the nine CSVs are evidence a person opens rather than page input:
`filter_gain.csv`, `name_reconciliation.csv` and `coverage_gate.csv`.
`measure.NOT_READ_BACK_BY_A_BUILD` names them. A dated `snapshots/` folder
records a day the labels moved; no build reads one back.

`input/boxes/` is tracked, unlike the other data folders, because the frame list
in it defines the population every number is counted over. Why a module is
shaped the way it is lives in that module's own docstring, so
`dashboard/queues.py`, `dashboard/assets.py`, `dashboard/style.py` and
`dashboard/explain.py` each open with the argument for their own existence.
Read one before splitting it.

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
