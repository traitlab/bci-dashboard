# BCI dashboard

How Pl@ntNet is doing on BCI drone close-ups right now, and which photos to send
to botanists next. Standalone: no Labelbox access, no network calls, no pandas.
Every number is recomputed offline from cached API responses and a Labelbox
export you drop on disk.

## What it is for

Two questions, in this order:

1. **How does the model stand today?** Top-1 on labelled crowns, per species,
   with support counts, calibration, and the reasons a status was assigned.
2. **What should be labelled next?** A send-first queue and species-grouped
   batches, so the answer is a list the labelling team can act on rather than a
   chart.

## What the numbers mean

**Score only what the model saw.** `dashboard/crop_overlap.py` measures this. A photo prediction comes from a fixed
1280x1280 centre crop, which is 13.7% of a 4000x3000 frame. A botanist draws
crowns anywhere in the frame. A frame is admitted only when its dominant labelled
species covers `T` or more of the crop, and `T` is 0.50. The pages report gated
and ungated side by side, because the two are different populations.

**Score per crown, not per photo.** Sending the crown box pixels removes the crop
problem instead of filtering around it. `predict/crown.py` fetches per crown box, and `data/crowns_export/` holds 6,030 crown
predictions cut from the boxes in the current Labelbox export. 5,849 carry a
botanist label, and `predict/crown_accuracy.py` scores those. `dashboard/core.py`
still scores one row per photo, so the pages do not read this cache yet.

**The crown scores split hard by camera, and camera is not the only thing that
splits.** 86.1% top-1 on 5,388 zoom crowns, 51.8% on 461 tele crowns, and every
unsent photo is tele. `crown_accuracy.py` decomposes the 34.2 points into the
species mix (15.5), one flight (10.0), and species the zoom corpus never shows
(8.7). The middle step is confounded: of the 72 missions in
`data/dataset_rows.jsonl`, none carries both classes and no calendar day does
either, so campaign moves with camera. Control 7 prints that sharing, 0 missions
of 40 and 0 days of 34. Control 6 rules out apparent magnification and runs the
opposite way to the words: a crown box is 0.357 of its frame linearly on tele
against 0.319 on zoom, so the camera that scores worse holds the 1.12x larger
tree. A confidence threshold set on zoom does not carry to tele.

**Tiles.** `predict/tiles.py` calls the Pl@ntNet quadrat endpoint, which slides
the window itself: 518 px, stride 259, 140 sub-queries for one 4000x3000 frame.
`dashboard/score_tiles.py` scores `photo`, `tiles` and `tiles@crop` against the
same ground truth. The third arm holds the region fixed, so only the pooling
changes. 143 frames are cached. The tiles carry a position per tile and no
embedding per tile, so the liana route is measured and not delivered.

**Rank by embedding, not by score.** A confidence score prioritises well only for
species the model already knows. It says nothing about the roughly 282 species
with almost no labels. `predict/embed.py` fetched 768-dim embeddings for all
3,269 unsent photos and 1,719 labelled ones, which cost no identify credits.
`labelling/rank_unsent.py` orders the unsent pool by CoreSet coverage into
`data/next_batch/queue_ranked.csv`. The pages do not read that file. The queue
they show is still bucketed by confidence and support in `dashboard/core.py`.

**"Pl@ntNet never names it" is two claims.** A species outside the project
checklist is out of scope. A species inside the checklist that never reaches the
top 5 is a real miss. The pages cannot yet tell them apart, because absence is
inferred from the cached top-5 lists. Those lists hold 1,567 of the model's names
corpus-wide. Of the 957 binomials carried by species-level ground-truth crowns,
143 are visible only because rank 5 was included, measured over the 957 and not
the 1,567. `predict/fetch_checklist.py` pulls the label set itself, which is what
settles the question. The 15,919 figure comes from `speciesCount` on
`/v2/projects` and is documented nowhere by Pl@ntNet.

Dated snapshots are written on every run, so a trend line can come back with no
recomputation.

## Layout

```
dashboard/            the pages, stdlib only
  measure.py          measurement pass -> CSVs + run_log.txt
  core.py             loading, joining, scoring, queues
  build_full.py       full HTML page
  build_simple.py     one-page companion
  build_export_only.py  scores a single export in isolation
  crop_overlap.py     what the model actually saw, per frame
  score_tiles.py      photo vs tiles vs tiles@crop, one ground truth
  assets.py explain.py history.py
predict/              Pl@ntNet calls, the only side that needs a key
  photo.py            per photo, centre crop
  crown.py            per crown box
  crown_accuracy.py   crown scores split by camera, and the gap decomposed
  embed.py            768-dim embeddings, no identify credits
  tiles.py            the quadrat endpoint
  fetch_checklist.py  the project label set
  ingest_photos.py    bulk ingest: predictions + embeddings -> data/predictions/cache
  aggregate_survey.py
labelling/            Labelbox side
  gt_from_export.py   fold an export into the ground truth
  next_batch.py       species-grouped batches
  rank_unsent.py      CoreSet order -> data/next_batch/queue_ranked.csv
  dispatch_round.py   send a batch
  close_round.py      fold the returned labels back in
bin/refresh.sh        export -> GT merge -> measure -> rebuild -> snapshot
input/boxes/          crown boxes and the frame list (tracked)
data/                 GT, splits, cached predictions, WCVP cache (gitignored)
snapshots/            dated model-health-<date>/ folders (gitignored)
build/                the built HTML pages (gitignored)
```

## Run

```bash
bin/refresh.sh                          # newest export in data/exports or ~/Downloads
bin/refresh.sh path/to/export.ndjson
```

Or the measurement pass alone:

```bash
python3 dashboard/measure.py --out-dir snapshots/model-health-$(date +%F)
python3 dashboard/build_simple.py --out build/simple_dashboard.html
```

Paths default to the checkout and can be overridden:
`BCI_DASHBOARD_REPO`, `BCI_DASHBOARD_DATA`, `BCI_DASHBOARD_SNAPSHOTS`,
`BCI_WCVP_CACHE`.

The dashboard needs no API key. The fetch scripts under `predict/` need
`PLANTNET_API_KEY` in `.env` and the packages in `requirements.txt`. The
scripts under `labelling/` need `LABELBOX_API_KEY` there too. Copy
`.env.example` and fill it in; `.env` itself is gitignored and is the only
place a key belongs.

Which Labelbox workspace those scripts point at is not a key and is not
secret: the dataset and project ids open nothing without the API key. They sit
in `config.yaml`, where a reader can see what a run will touch before it runs.
`LABELBOX_DATASET_ID` and `LABELBOX_PROJECT_ID` override them, so a second
workspace needs no edit to a tracked file.

Longer definitions of every published number, handovers and dated progress notes
are kept out of the repo, in the sibling `bci-dashboard-docs/` directory, so a
stale one cannot be read as current.

## Test

```bash
uv pip install -r requirements-dev.txt          # once, into .venv
.venv/bin/pytest
```

Name the interpreter. The tests under `tests/` that cover `predict/` import
`PIL`, `yaml` and `dotenv`, and skip themselves when those packages are absent.
A system interpreter without them reports a pass on two thirds of the suite.
`-ra` is on by default, so every skip prints its own line with the reason and a
short run is visible as a short run.
