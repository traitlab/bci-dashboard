# BCI dashboard

Botanists outline tree crowns in drone photos of BCI and name each species in Labelbox. Pl@ntNet, a plant-naming service, guesses the species in the same photos. This repo turns those two sources into self-contained HTML pages that answer two questions:

1. **How well does Pl@ntNet name BCI trees?** The model-health page, for anyone outside the lab.
2. **Which photo should a botanist label next?** The queue page, for the labelling team.

## How it fits together

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}}}%%
flowchart LR
    frames["Drone frames<br/>4000x3000 photos"]
    frames --> lb["Labelbox<br/>botanists outline crowns<br/>and name them"]
    frames --> pn["Pl@ntNet<br/>five candidates<br/>per centre crop"]
    lb -- "weekly export" --> disk[("Files on disk<br/>labels and<br/>cached answers")]
    pn -- "cached answers" --> disk
    disk --> measure["dashboard/measure.py<br/>scores every photo"]
    measure --> tables[("build/tables<br/>twelve CSVs")]
    tables --> ext["build_external.py"] --> health["Model-health page"]
    tables --> int["build_internal.py"] --> queue["Queue page<br/>and send_batches.csv"]
    queue -- "dispatch_round.py<br/>sends one batch" --> lb
```

Both pages read one measurement pass, so they cannot disagree. The builders read only files on disk, so the same files always give the same page. Each builder recomputes every number it prints and stops if `build/tables` disagrees, batch assignment included.

## The pages

The site publishes these pages from `docs/`:

- the model-health page, by `dashboard/build_external.py`: per species, how often the first guess is right, on how many labelled frames, and why the species carries its status
- the queue page, by `dashboard/build_internal.py`
- the photo explorer, by `dashboard/build_explorer.py` from `labelling/export_explorer.py`
- the photo atlas (drone map and similar photos), by `dashboard/build_embedding_atlas.py` from `labelling/project_atlas_tsne.py`
- the crown-first atlas, by `dashboard/build_embedding_atlas.py`
- the index and about pages, by `dashboard/build_index.py`

## What to label next

The queue page orders every unlabelled photo that has a cached Pl@ntNet answer.

### A rule picks the queue

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}}}%%
flowchart LR
    photo["Unlabelled photo<br/>first guess: species S<br/>confidence: c"]
    photo --> t1{"S has fewer than 10 labelled frames,<br/>or is right less than 70% of the time?"}
    t1 -- yes --> q1["Queue 1: long_tail<br/>Species we barely have,<br/>or barely get right"]
    t1 -- no --> t2{"S is right at least 90% of the time,<br/>but c is under 0.50?"}
    t2 -- yes --> q2["Queue 2: low_conf_known<br/>A usually-right species,<br/>guessed weakly"]
    t2 -- no --> t3{"c is 0.80 or more?"}
    t3 -- yes --> q4["Queue 4: can_wait<br/>Confident on a<br/>well-covered species"]
    t3 -- no --> q3["Queue 3: normal<br/>Worth a look"]
```

`send_first_queue.csv` lists the queues in order 1, 2, 3, 4. A photo that reaches the third test belongs to a species with 10 or more labelled frames, so a confident guess there is enough to push it down the queue. The two-part wait rule behind queue 4 is measured on frames held back for grading, and the queue page shows every confidence line it was compared against.

The numbers are `dashboard/core.py` constants and the rule is `queues.queue_of_prediction`. The page prints both from the same source.

A frame held back for grading (it carries a split in `data/splits.csv`) never enters a queue, and neither does a frame Pl@ntNet returned no answer for. The page counts both.

### Inside a queue, the least familiar photo goes first

Pl@ntNet turns each centre crop into 768 numbers that describe how the photo looks to the model. Two photos with close numbers look alike. `labelling/rank_queue.py` uses those numbers to order each queue:

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}}}%%
flowchart LR
    covered["Every labelled photo<br/>counts as covered"] --> pick["Pick the queued photo<br/>least like everything covered"]
    pick --> add["Add the pick<br/>to the covered set"]
    add --> pick
```

A photo very like one just picked drops back. Confidence only breaks a tie. The picking is `greedy_kcenter` from labelfirst, and no label or prediction steers it.

On the frames a botanist has already named, the order covers half of their species in far fewer photos than a random order, on every seed. `labelling/rank_queue.py --backtest` is the check, and the queue page prints the current figures and draws its curve.

The ranking lands in `data/next_batch/queue_novelty.csv`. The weekly refresh writes it and `bin/refresh.sh` does not. `dashboard/build_internal.py` refuses to build when the file is missing or ranks none of the queued photos.

### Batches carry each species whole

`send_batches.csv` packs the ordered queue into batches of 100, or `BCI_BATCH_SIZE`. A species ships at the place of its highest-ranked photo, with every other photo of that species beside it. The first batch gives 15% of its places (`CONTROL_FRACTION`) to photos drawn at random from the whole pool, as a comparison for the queue.

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}}}%%
flowchart LR
    q["send_first_queue.csv<br/>queue, then rank"] --> g["Group photos by species,<br/>placed at its<br/>highest-ranked photo"]
    g --> p["Pack the groups<br/>into batches of 100"]
    p --> b1["Batch 1<br/>plus the random<br/>comparison photos"]
    p --> bn["Batches 2, 3, and on"]
    b1 --> d["dispatch_round.py<br/>--batch N"]
    bn --> d
    d --> lb["Labelbox"]
```

So the queues mix in send order. A queue 4 photo ships with its species' photos from queue 2 or 3. Only a species with no photo in queues 1 to 3 waits for the last batches.

## What a number means

Three things to know before reading a number:

- **The headline is measured crown by crown.** One call goes to Pl@ntNet per labelled crown, pooled to the frame by box area, on 300 frames frozen before the numbers existed. `input/confirmatory_frames_2026-08.csv` is that list. It is the cost of naming trees already found, not of finding them.
- **Every other rate comes from a fixed 1280x1280 centre crop**, 13.7% of the frame, while a botanist draws crowns anywhere in it. The pages score every frame with no coverage condition applied. `MIN_CROP_COVERAGE` (0.50) asks a different question: does the frame's own label fill half of the *crop* the model was sent. The pages only report it, in `coverage_gate.csv`. `labelling/next_batch.py` filters on it.
- **A miss counts only inside a known population.** A species missing from a cached list of five names is unproven either way.

Box geometry comes from the labels. The fetch records the crop it sent (`ingest_photos.stamp_geometry()`), but the cached predictions carry none, so `crop_overlap.crop_rect()` reconstructs it from the frame constants.

## Build the pages

Run the measurement pass first, or use the local refresh:

```bash
python3 dashboard/measure.py --out-dir build/tables   # the measurement pass
python3 dashboard/build_external.py                   # writes build/model_health_dashboard.html
python3 dashboard/build_internal.py                   # writes build/label_queue_dashboard.html,
                                                      # plus send_first_queue.csv and send_batches.csv beside it
bin/refresh.sh                                        # local: export, measure, both pages, snapshot
bin/refresh.sh path/to/export.ndjson                  # a named export instead of the newest
```

`bin/refresh.sh` takes the newest export in `data/exports` or `~/Downloads` when given no path.

`dashboard/build_external.py` refuses to build when `data/model_health/` is missing or older than the labels. Regenerate it with `labelling/assess_species.py` in the crownfirst virtualenv, or set `CROWNFIRST_PYTHON` so `bin/refresh.sh` does it.

`bin/publish_thumbs.sh` builds the 480px thumbnail release the atlases and the explorer load.

## The weekly refresh

`.github/workflows/weekly-refresh.yml` runs `bin/refresh_snapshot.py`. It downloads the Sunday export from the Arbutus bucket (variables `ARBUTUS_S3_ENDPOINT`, `BCI_LABELBOX_EXPORTS`, `BCI_LABELBOX_PROJECTS`; secrets `ARBUTUS_S3_ACCESS_KEY`, `ARBUTUS_S3_SECRET_KEY`) and runs these steps:

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}}}%%
flowchart LR
    ex["Sunday export"] --> merge["Merge labels<br/>gt_from_export.py"]
    merge --> embed["Embed every<br/>named frame"]
    embed --> assess["Assess species<br/>assess_species.py"]
    assess --> rank["Rank the queue<br/>rank_queue.py"]
    rank --> measure["measure.py"]
    measure --> build["Build and<br/>cross-check pages"]
    build --> publish["Publish docs/<br/>and save a snapshot"]
```

A dated `snapshots/` folder records a day the labels moved. No build reads one back.

## Where things live

- `predict/` calls Pl@ntNet, caches its answers, and makes the 768 numbers per centre crop (`predict/embed.py`).
- `labelling/` talks to Labelbox: it merges exports into labels, ranks the queue, sends batches, and writes the species assessments and the atlas inputs.
- `dashboard/` holds `measure.py` and the page builders.
- `bin/` holds the local and weekly refresh and the publish scripts.
- `docs/` is the published site, with the CSVs its pages link.

Three of the twelve CSVs in `build/tables` are evidence a person opens rather than page input: `filter_gain.csv`, `name_reconciliation.csv` and `coverage_gate.csv`. `measure.NOT_READ_BACK_BY_A_BUILD` names them.

`input/boxes/` is tracked, unlike the other data folders, because the frame list in it defines the population every number is counted over. Each module's docstring says why it is shaped the way it is.

## Configure

Copy `.env.example`. `.env` is gitignored and is the only place a key belongs: `PLANTNET_API_KEY` for `predict/`, plus `LABELBOX_API_KEY` for `labelling/`.

The Labelbox workspace IDs are not secret, so they sit in `config.yaml`. `LABELBOX_DATASET_ID`, `LABELBOX_PROJECT_ID` and the `BCI_DASHBOARD_*` path variables override them.

## Test

```bash
uv pip install -r requirements-dev.txt          # once, into .venv
.venv/bin/pytest
```

Name the interpreter. Tests covering `predict/` skip themselves when `PIL`, `yaml` or `dotenv` is missing, so a system interpreter runs two thirds of the suite and still reports a pass. `-ra` is on, so every skip prints why.
