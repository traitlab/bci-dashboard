# Preregistered hypothesis: region-aligned evaluation

Written 2026-08-26T19:57Z, before any API call for this experiment was made.
Nothing below may change once the first frame is fetched. A change after that
point makes the result exploratory, and it must be labelled exploratory.

## Why this experiment exists

Every headline accuracy number the dashboard has published so far scores a
1280x1280 square cut from the centre of a 4000x3000 frame against a label that
describes the whole frame.

- Ground truth for a frame is the species whose outlined crowns cover the
  largest summed raw box area over the whole frame
  (`labelling/gt_from_export.py:102`).
- The prediction that number scores is an identify call on the centre square,
  which is `crop_rect(4000, 3000, 1280) = (1360, 860, 2640, 2140)`, 13.65% of
  the frame area.

The two regions are different and no code path compares them. On the 3,777
record population the labelled species fills under half the centre square on
1,377 frames, fills none of it on 207, and no labelled box touches the square at
all on 175. The published crop coverage gate does not catch this, because it
gates on the crop dominant's share and not on the labelled species' share.

This experiment does not repair that number. It replaces it with two arms whose
region of prediction is the same as the region the label describes, and measures
them under a design fixed in advance.

## Population and frozen sample

Draw pool, all conditions required:

1. a species-level ground truth for the frame,
2. a known frame URL,
3. an existing centre-crop prediction, so the legacy arm stays reportable
   alongside the region-aligned ones,
4. no tiles cache entry as of the draw. The 146 frames already fetched were
   scored in an earlier session, so their result has been seen and they cannot
   carry a confirmatory claim,
5. at least one labelled crown of at least 128 px on both sides in
   `data/export_boxes.csv`, the same box export the ground truth is computed
   from. The tracked 2024 file `input/boxes/crop_bounding_boxes.csv` holds three
   times as many boxes, but the July 2026 botanist revision is what defines the
   label, and a crown arm cut from a different revision is not aligned with the
   label it is scored against.

That pool is 1,607 frames over 12 sites, and it is committed as
`input/confirmatory_pool_2026-08.csv`. The pool is written to a manifest rather
than re-derived, because condition 4 reads the tiles cache and the Phase 2 fetch
fills it, so a check that re-derived the pool would start failing the moment the
fetch began.

The sample is 300 frames, drawn by `predict/draw_confirmatory.py` with seed
20260826, stratified by site, proportional within site, any one site capped at
25% of the sample. The frozen list is
`input/confirmatory_frames_2026-08.csv`, sha256

    4a47a992915f7d72483de5cfa80f018dbc27d36222142b4ec4b0f3f1e6bc3406

It covers 12 sites, 38 flight days and 953 labelled crowns.
`python predict/draw_confirmatory.py --verify` re-draws it and exits non-zero on
any drift.

## Arms

All three arms score the same 300 frames against the same frame-level label.

| arm | what is sent | region seen | aligned with the label |
|---|---|---|---|
| `tiles` | quadrat endpoint, 518 px window at stride 259, 140 sub-queries | the whole frame, 94.1% covered | yes |
| `crown` | one identify call per labelled crown, the crown's own pixels | the labelled crowns | yes |
| `photo` | one identify call on the 1280 px centre square | 13.65% of the frame | no, reported as the legacy reference only |

The `photo` arm is not a competitor here. It is carried so the size of the
region defect can be read off the same 300 frames, and it is never described as
region-aligned.

## Aggregation, fixed now

Ground truth names one species per frame: the one whose labelled crowns hold
the largest summed raw box area over the whole frame. Each arm must therefore
produce one species per frame, and each arm's rule mirrors that criterion as
closely as its own output allows.

- **tiles.** Top-1 is the species with the largest `coverage` value the quadrat
  response returns, which is that species' share of the frame. Ties break on the
  highest single tile score, then alphabetically. The full ranking for top-5 is
  the same ordering.
- **crown.** Each crown's identify call gives a ranked species list. A crown
  votes with its own raw box area `w * h`, unclipped, for its top-1 species.
  The frame's prediction is the species with the largest summed vote. Ties break
  on the highest single crown score, then alphabetically. The top-5 ranking is
  the same ordering over summed vote. Only crowns of at least 128 px on both
  sides vote, matching the fetch rule.
- **photo.** Top-1 is the highest `max_score` species, unchanged from what the
  dashboard already publishes.

Every arm's name is canonicalised through the WCVP crosswalk before it is
compared, the same normalisation the dashboard already applies.

## Primary endpoint

Frame-level top-1 accuracy on the frozen 300: the share of frames where the
arm's top-1 species equals the frame's ground truth species.

The primary comparison is `crown` against `tiles`, paired on the frame.

## Predictions

Directional, committed before any of this data exists.

- **P1.** `crown` beats `tiles` on top-1. The crown arm's unit of prediction is
  the unit of ground truth, while the tiles arm must also see trees nobody
  labelled and can be marked wrong for naming a real one. Prior evidence: an
  earlier crown pilot read 85.4% on zoom frames.
- **P2.** Both region-aligned arms beat 50% top-1 on the frozen 300.
- **P3.** The `photo` arm's top-1 on these same 300 frames falls below `crown`'s.
  Its region is 13.65% of the label's region, so it should be the weakest of the
  three.
- **P4.** The `tiles` arm's disadvantage against `crown` is larger on frames
  where the labelled crowns cover less of the frame. This is the mechanism
  behind P1, so it should show up as a gradient rather than a flat offset.

P1 is the primary. P2 to P4 are secondary and are reported with the same
intervals but are not the basis for the headline claim.

## Tests, fixed now

- **Primary test.** Two-sided exact McNemar on the discordant pairs of
  `crown` and `tiles`, an exact binomial with p = 0.5 on the `crown`-only and
  `tiles`-only counts. Significance at alpha = 0.05.
- **Cluster unit.** Site, 11 in the frozen sample. Site is the coarser of the
  two candidate units, since a flight day is a mission at one site, so
  clustering on site is the more conservative choice and it is the unit at which
  species composition actually repeats.
- **Intervals.** Per-arm accuracy is reported with a cluster bootstrap interval:
  resample sites with replacement, 10,000 draws, seed 20260826, percentile
  interval at 95%. Eleven clusters is too few for a sandwich estimator to be
  trusted, which is why the bootstrap is used rather than a cluster-robust
  standard error.
- **Sensitivity, pre-specified.** The same bootstrap clustered on flight day
  instead of site, and a cluster bootstrap p-value for the paired accuracy
  difference. If the exact McNemar and the cluster bootstrap disagree on the
  sign or on significance, the cluster bootstrap is reported as the answer,
  because the exact test assumes independent pairs and the pairs are clustered.
- **Unclustered Wilson intervals are reported too**, side by side and labelled
  as too narrow, so a reader can see the cost of the clustering.

## Stopping rule

- The sample is 300 frames. No frame is added, dropped or replaced after this
  file is committed.
- No interim analysis. The scoring script is not run against the confirmatory
  set until both arms hold all 300 frames.
- If a fetch fails on a frame after three attempts, that frame is reported as a
  fetch failure with its reason, and the analysis runs on the remainder with the
  loss stated in the writeup. It is not replaced by another draw.
- The quadrat quota is 20,000 per day and the tiles arm costs 42,000 credits, so
  that fetch spans three calendar days. The crown arm is already cached and
  costs nothing (see amendment A2). A partial-set analysis run before both arms
  are complete is exploratory and must be labelled exploratory.

## What would falsify the headline claim

If `crown` does not beat `tiles` at alpha = 0.05 on the exact McNemar, P1 is not
supported, and the writeup says so in those words. A null result here is a
result: it would mean that seeing the whole frame recovers what crown-level
cropping buys, which would make the operational arm, the one that needs no
botanist's box, the one to deploy.

## What is explicitly exploratory

Anything not named above. In particular: per-site and per-camera breakdowns, the
tiles arm's own coverage as a box-free gate, top-5 accuracy, and any threshold
tuned after the numbers are seen. The tele camera is fully confounded with
mission, 0 of 27 missions carry both cameras, so no camera claim can be made
from this design at all.

## Amendments

Every change to this file after it was first committed, with the reason and
the state of the data at the time. Nothing here was written after an outcome
was scored.

### A1, 2026-08-26, the crown arm was cut from the wrong box revision

**Found before**: any frame was scored in any arm. Nine quadrat frames had been
fetched and none had been read.

**The error.** Condition 5 of the first draw read
`input/boxes/crop_bounding_boxes.csv`, the tracked 2024 geometry, because that
is what `predict/crown.py` defaults to. Ground truth is computed from
`data/export_boxes.csv`, the July 2026 botanist revision
(`labelling/gt_from_export.py:41`). Only 142 of the first 300 frames carried a
box in the revision that defines their label, so the crown arm would have been
cut from a different set of crowns than the label it was scored against. That is
the same region-misalignment defect this whole experiment exists to remove.

**The fix.** Condition 5 now reads `data/export_boxes.csv`. The pool falls from
2,685 to 1,607 frames and gains a twelfth site. The sample was redrawn from the
same seed. The nine frames already fetched fall out of the pool under condition
4 and are not in the new list; the credits spent on them are lost.

**What this costs.** Nothing in the analysis. No outcome had been computed. The
predictions, the endpoint, the tests and the stopping rule are unchanged.

### A2, 2026-08-26, the crown arm is not blind, and is labelled so

`data/crowns_export/cache` already holds all 953 crown predictions for the
frozen 300, cut from `data/export_boxes.csv`, fetched in an earlier session
before this freeze. The crown arm therefore costs zero credits, and it is also
not blind.

What that does and does not undermine:

- **The tiles arm is blind.** Condition 4 excludes every frame with a quadrat
  result, so no frame in this sample has ever been scored in that arm.
- **The frame-level aggregation is new.** The area-weighted crown vote defined
  above has never been computed on any sample. What was reported earlier was a
  per-crown top-1 accuracy of 85.4% over the whole corpus, on a different unit
  and a different population.
- **The sample is new.** These 300 frames were not chosen by looking at crown
  results.
- **But the number was not generated blind.** An operator has seen crown-arm
  accuracy, at another unit and on a wider population, before this freeze.

The writeup must say this in those words. The crown arm's own accuracy carries a
prior-exposure caveat. The paired comparison and the tiles arm do not.

### A3, 2026-08-26, an interim look was taken on the incomplete tiles arm

**State of the data.** The tiles arm held 129 of 300 frames, the crown and photo
arms held 300. The operator asked what the day's credits had bought, and the
scorer was run and read.

**What was seen.** The full EXPLORATORY report, including P1, P2 and P4.

**What changed as a result.** Nothing. The sample, the arms, the aggregation
rules, the endpoints, the tests, the cluster units and the stopping rule are as
committed, and the frozen list still matches the sha256 above. The design is not
reachable from the outcome without a commit that says so.

**Why the number seen is not a preview.** The 129 fetched frames cover 7 of the
12 sites, and four of those seven are complete while five sites hold nothing.
The interim tiles figure and its site-clustered interval are computed on a
site-biased subset, not on a random 43% of the sample.

**What the writeup must say.** That this look happened, on which arms, at what
completeness, and that no design element moved.

## Provenance

- Draw script: `predict/draw_confirmatory.py`, seed 20260826.
- Frozen list: `input/confirmatory_frames_2026-08.csv`, sha256 above.
- Pool manifest: `input/confirmatory_pool_2026-08.csv`, 1,607 rows, sha256
  80fb498f480a56210343146266e9f119b5bc742276a3266f94dbbb6eee8168ec
- Crown boxes and ground truth both from `data/export_boxes.csv`.
- Ground truth: July 2026 botanist revision, Labelbox project 2024_bci,
  exported 2026-08-06, not yet reviewed
  (`data/gt_dominant_taxon.provenance.txt`).
- Quadrat price, measured 2026-08-26: 140 credits per frame, exactly one per
  sub-query. Identify price: 1 credit per crown. The two quotas are separate.
