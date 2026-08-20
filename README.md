# BCI dashboard

How Pl@ntNet is doing on BCI drone close-ups right now, and which photos to send
to botanists next. Standalone: no Labelbox access, no network calls, no pandas.
Every number is recomputed offline from cached API responses and a Labelbox
export you drop on disk.

Extracted from the workshop pipeline it grew in, keeping only the dashboard's
own history.

## What it is for

Two questions, in this order:

1. **How does the model stand today?** Top-1 on labelled crowns, per species,
   with support counts, calibration, and the reasons a status was assigned.
2. **What should be labelled next?** A send-first queue and species-grouped
   batches, so the answer is a list the labelling team can act on rather than a
   chart.

## Objectives (2026-08-12 call)

- **Score only what the model saw.** Predictions come from a fixed 1280x1280
  centre crop, 13.7% of a 4000x3000 frame; ground truth comes from crowns drawn
  anywhere in it. A frame is admitted only if its dominant labelled species
  covers at least `T` of the crop. `T = 0.50` agreed, gated and ungated reported
  side by side because they are different populations.
- **Per crown, not per photo.** Scoring each crown box directly removes the
  problem instead of filtering around it (`predict/crown.py`). Built and run:
  7,967 crown predictions cached across `data/crowns/` and `data/crowns_export/`,
  each carrying the box it was cut from, scored by `predict/crown_accuracy.py`.
  Not the primary number yet: `dashboard/core.py` still evaluates one row per
  photo against a per-photo dominant taxon, so nothing joins the crown cache
  into the pages.
- **Tiles, built and measured.** `predict/tiles.py` calls the Pl@ntNet quadrat
  endpoint, which slides the window itself: 518 px, stride 259, 140 sub-queries
  per 4000x3000 frame. `dashboard/score_tiles.py` scores three arms against the
  same ground truth, `photo`, `tiles`, and `tiles@crop`, the third holding the
  region fixed so only the pooling changes. 143 frames cached. The tiles carry
  per-tile positions but no per-tile embeddings, so the liana route is measured,
  not yet delivered.
- **Predictions cover the head, embeddings cover the tail.** Confidence-based
  prioritisation works for species the model already knows. For the ~282 species
  with almost no labels it says nothing, so ranking unlabelled photos by
  embedding novelty is the other half, not a nice-to-have. Built and run:
  `predict/embed.py` fetched 768-dim embeddings for all 3,269 unsent photos and
  1,719 labelled ones, at no cost in identify credits, and
  `labelling/rank_unsent.py` ranks the unsent pool by CoreSet coverage into
  `data/next_batch/queue_ranked.csv`. The pages do not read it: the queue they
  show is still bucketed by confidence and support in `dashboard/core.py`.
- **"Pl@ntNet never names it" is two things.** Species outside the project
  checklist are out of scope, not errors; species inside it that never reach the
  top 5 are real misses. Reported separately. Today the pages cannot tell them
  apart: absence is inferred from the cached top-5 lists, which hold 1,567 of
  the model's names corpus-wide. Of the 957 binomials carried by species-level GT
  crowns, 143 are visible only because rank 5 was included. The 143 is measured
  over those 957, not over the 1,567. `predict/fetch_checklist.py` pulls the label set itself, which is
  what settles it. The 15,919 figure quoted on the call is not documented by
  Pl@ntNet; the count comes from `speciesCount` on `/v2/projects`.
- **No trend line.** Dropped by request: what matters is where things stand with
  the model and labels in hand. Dated snapshots are still written, so a trend
  can come back without recomputation.

## Layout

```
dashboard/            the pages, stdlib only
  measure.py          measurement pass -> CSVs + run_log.txt
  build_full.py       full HTML page
  build_simple.py     one-page companion
  build_export_only.py  scores a single export in isolation
  core.py             loading, joining, scoring, queues
  crop_overlap.py     what the model actually saw, per frame
  assets.py explain.py history.py
predict/              Pl@ntNet calls
  photo.py            per photo, centre crop
  crown.py            per crown box
  ingest_photos.py    bulk ingest: predictions + embeddings -> data/predictions/cache
  aggregate_survey.py
labelling/            Labelbox side
  gt_from_export.py   fold an export into the ground truth
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
`PLANTNET_API_KEY` in `.env` and the packages in `requirements.txt`.

See `docs/metrics.md` for what each number means and how it is
computed.
