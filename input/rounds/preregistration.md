# Round 1 (batches 1 to 4)

Dated 2026-10-29, written before any label arrives.

## Estimand

Top-1 accuracy over the pool of predicted-tree frames in `send_batches.csv`. A frame counts as correct when the model's first guess equals the label. The model sees the centre crop only, the fixed 1280 px square from the middle of the frame (`predict/photo.py`, 13.7% of the frame). The label is as in CONTEXT.md: the species with the largest crown area in the whole frame, which the botanist labels from the whole frame in Labelbox. The two usually agree; when the aim misses, the guess is scored against the largest crown, not the centre one. This matches every published number on the dashboard.

## Estimator

The mean over the labelled control rows (`picked_by == control`), a uniform draw from the pool reserved before packing. Beside it, the PPI++ estimate (Angelopoulos, Duchi and Zrnic 2023), which adds the model's top-1 confidence over the whole pool to narrow the interval. The control stays the only source of truth.

## Interval

Percentile bootstrap over the control frames, B=1000, seed fixed in `labelling/read_round.py`. The control row keeps its Wilson interval. With fewer than 60 labelled control frames (four full batches) the PPI++ estimate is printed without an interval and the Wilson interval is the one to read: on 3,749 labelled frames with a prediction, 200 draws each, the bootstrap covered the pool accuracy 0.875 of the time at 15 control frames and 0.945 at 60.

## Expected precision

Measured the same way, median 95% half-width around a pool accuracy near 0.68: one batch (15 control) Wilson 0.22; four batches (60) Wilson 0.12, PPI++ 0.09; eight batches (120) Wilson 0.08, PPI++ 0.07. Round 1 therefore reads the pool accuracy to about plus or minus 9 points. A pass mark finer than that needs more rounds, not a different estimator.

## Secondary

Per-species accuracy on control rows only, reported with counts. No pass mark.

## Blinding

The batch sent to Labelbox carries no guess, no queue and no control mark, and its rows are in random order. The public site does: `send_first_queue.csv` and the explorer page name Pl@ntNet's first guess for every photo, and `send_batches.csv` marks the control rows. Hiding one file would not change that, since the repo and its Pages are public. So the blinding is a rule, not a lock: the botanist labels from Labelbox alone and does not look a photo up on the site while labelling. The reply that sends batch 1 says so.

## Not claimed

- Accuracy on frames Pl@ntNet calls liana, or on `can_wait` frames: neither is sent, so the pool is the frames worth a botanist's time, not every frame.
- Label noise: there are no repeat labels, since labelling capacity may be one person.

## Pass marks

None in round 1. It is the baseline. Marks are set from round 2 against this number.
