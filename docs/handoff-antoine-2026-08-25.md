# What I found in the 2024_bci dataset

For Antoine, on your return. Written 2026-08-19.

You told me the goal: know which picture in the dataset to send to the project.
I read the dataset with your API key. I did not write anything to Labelbox.
This page gives the result, the parts that do not work, and what I need from you.

---

## 1. What the dataset holds

The dataset `2024_bci` (`cmon3zoss00wu0705ertl0vd7`) holds 5,201 data rows.
The rows are in two groups. The groups have different global key formats.

| Group | Global key format | Rows | In the project? |
|---|---|---|---|
| Legacy | `migrated/DJI_...zoom.JPG` | 1,719 | All 1,719. All `DONE`. |
| Current | `<flight folder>/DJI_...tele.JPG` | 3,482 | Only 213. |

The project export holds 1,932 rows. That is 1,719 legacy rows plus 213 current rows.
The 213 rows are one flight: `20260402_bci50haplot_wptse2_m3e`.
Their status is 172 `IN_REVIEW`, 32 `TO_LABEL`, 8 `DONE`, 1 `IN_REWORK`.

So 3,269 photos are in the dataset but not in the project.
They come from 32 flights of the 2026 season.
The median flight has 106 photos. The pilot batch of 213 photos is still in review.
The unsent pool is about 15 such batches.

---

## 2. Why my batch list did not work

You said some pictures were in the old project and some in the new one.
The cause is more simple. There are three global key formats for the same photo:

- `comb_DJI_...zoom.JPG` in my local files
- `migrated/DJI_...zoom.JPG` in the dataset, for legacy rows
- `<flight folder>/DJI_...tele.JPG` in the dataset, for current rows

Only the file name is common to all three. My list used the bare file name.
Four of the nine keys I sent you resolve to a dataset row. Five do not.
The five are photos that the migration did not move into `2024_bci`.
Nobody can put them in a batch from the dataset. This is not a permission problem.

The code now does this join in one function (`basename` in `labelling/next_batch.py`).

---

## 3. The contradiction review is ready

Helene asked for a review of the crowns where the field label and Pl@ntNet disagree.
I built the queue from the cached predictions and the botanist labels.

Most of the disagreements are not disagreements. Pl@ntNet was sent a fixed
1280x1280 centre crop, which is 13.7% of the 4000x3000 frame. The field label
comes from a crown box that can be anywhere in that frame. So the model often
named a different tree, and named it correctly.

- 3,277 crowns have a species-level field label and a prediction.
- 673 crowns have a top-1 prediction that differs from the field label.
- 149 of those have a top-1 score of 0.5 or more.
- 76 of the 149 resolve to a data row that is in the dataset now.
- Of those 76, only 5 are a real disagreement about one tree.

I proved this. I sent Pl@ntNet the crown box pixels instead of the centre crop,
for 216 crowns, with no errors. The result separates cleanly:

| Verdict | Checked | Agreed after re-run | Still disagrees |
|---|---|---|---|
| Real disagreement | 5 | 0 | 5 |
| Label covers less than half the crop | 3 | 1 | 2 |
| Crop shows a different labelled tree | 6 | 6 | 0 |

Example: the field says `hura crepitans`; the centre crop gave
`fridericia candicans` at 0.98; the crown box gave `Hura crepitans` at 0.90.

Section 3 numbers above rest on `input/boxes/crop_bounding_boxes.csv`, which is
out of date. It predates the July 2026 revision. Compared against the boxes in
your export, on the 1,218 frames that both cover: the old file holds twice as
many boxes per frame (6 against 3), only 35% of them are the same crown, and
20% of even those carry a different species name. So I am rebuilding the queue
from the export geometry, which matches current ground truth on 100% of frames.

The file is `data/next_batch/queue_contradictions.csv`.
It holds the global key, the data row id, the field label, the prediction, and the score.
`labelling/dispatch_round.py` accepts this file. You or I can send it as a batch.
This is the one thing Fernando can start on immediately.

---

## 4. The ranking is ready. This is the answer to your question

`data/next_batch/queue_ranked.csv` puts all 3,269 unsent photos in order.
Send them from the top. This replaces `queue_photos.csv`, which was a dispatch
order and not a ranking.

**How the order is made.** I give each photo to Pl@ntNet and get back a list of
768 numbers that describes what the photo looks like. Then I take the photo that
looks least like everything already chosen, and I repeat. The method is the
CoreSet rule in the `speciesfirst` package.

**The order uses no species name.** It cannot, because no unsent photo has a
label yet. This is also what makes the test below honest.

**The test.** I did the same thing to the 1,719 old photos that *do* have a
botanist label. The selector saw only the numbers. I then used the labels to
count how fast each order finds new species. The labels score the order.
They never choose it.

| To cover | Ranked order | Random order | Gain |
|---|---|---|---|
| Half of the 155 species | 129 photos | 346 photos | **2.7x fewer** |
| 90% of the 155 species | 467 photos | 1,288 photos | **2.8x fewer** |

The ranked order won against every random draw, not only the average.

**It also works on the new photos.** The 3,269 have no labels, so I score with
the Pl@ntNet prediction instead. This is weaker evidence, but it points the same way:
the first 200 ranked photos hold 124 different predicted species; 200 random photos
hold 83. The first 500 hold 195 against 127.

**One more thing the order does by itself.** In the whole pool, 49% of photos get a
top score below 0.3. In the first 500 ranked photos, 69% do. So the order finds the
photos the model is least sure about, and it does this without ever reading a score.
That matters, because section 5 shows the score cannot be trusted on this camera.

**What this means for the botanist.** To see most of the species on the island,
Fernando does not label 3,269 photos. He labels the first few hundred in this order.

### The accuracy numbers are about a different group of photos

Read this with section 5. It changes how much you can trust that table.

The photos in the queue and the photos behind the accuracy numbers are not the
same group. They are different in two ways.

**The camera.** All 3,269 photos in the queue come from the tele camera. All
5,388 labelled crowns that give the 86% come from the zoom camera. The 461 tele
crowns give the 52%.

**The aircraft.** The queue holds two aircraft:

| Aircraft | Photos in the queue | Labelled crowns |
|---|---|---|
| `m3e` | 2,003 | all of them |
| `m3t` | 1,266 | **zero** |

Every labelled photo in the project comes from `m3e`. No photo from `m3t` has a
botanist label. So 1,266 photos in the queue, 39% of it, come from an aircraft
the model has never been measured on.

**What this means.** The accuracy numbers are the best evidence I have. They are
also evidence about a different group of photos. I do not give a number for
`m3t`, because there is not one.

**This does not change the order.** The ranking reads only the 768 numbers from
the photo itself. It does not use accuracy, and it does not use a score. So the
order is still correct. What you cannot do is read the 86% or the 52% as a
promise about what the botanist will see in these photos.

**What fixes it.** Label a small sample from each group. A few dozen crowns from
`m3t` gives that group its own number. Until then, each figure must say which
group it came from.

### Two things that are still open

**Export permission.** Pl@ntNet gives me the 768 numbers, so the ranking no longer
waits for Labelbox. But an export is still the only way to read labels back without
a hand-saved file. Please check the key scopes.

**Crown identity.** I cannot tell a new tree from a tree that was photographed before.
I tested three methods. All three fail. Section 6 gives the numbers.

---

## 5. The model is much weaker on the tele camera

This is the most important number on this page. Read it before you plan the next batch.

I sent Pl@ntNet the crown box pixels, for every crown that has a botanist label.
Then I split the result by camera.

**First, what `tele` and `zoom` mean.** They are two capture setups. The ingest
adds the name to the file name. The drone does not. Both write an ordinary
colour photo of 4000x3000 pixels, and both file names carry `_V_`, so neither
one is a thermal camera.

The two are close in framing. The median labelled crown fills 12.5% of a tele
frame and 10.2% of a zoom frame. So a tree is a little larger in a tele frame,
about 1.11 times in each direction. **Tele is not further away.** What differs
is when they were flown: the zoom corpus is 1,719 frames from missions between
2024-09 and 2026-01, the tele corpus is 116 frames from missions in 2026-04.
Both are the `m3e` aircraft.

Nothing on disk records the focal length, the flying height, or the ground
sample distance. So I cannot give you the optical difference between the two.
I can tell you that the crowns come out about the same size, and that the model
is much worse on one of them.

| Camera | Crowns | Species | Top-1 | Top-5 | Genus |
|---|---|---|---|---|---|
| zoom, legacy corpus, labels `DONE` | 5,388 | 152 | **86.1%** | 94.3% | 87.9% |
| tele, 2026 pilot, labels `IN_REVIEW` | 461 | 45 | **51.8%** | 69.0% | 62.0% |

All 3,269 unsent photos come from the tele camera. So the accuracy that matters
for the next batch is 52%, not 86%.

I tried to remove the difference. I could not.

- **Different species?** No. Use only the 32 species that both cameras show: 92.1% against 60.6%.
- **Smaller crowns?** No. The tele crown boxes are larger (971 px against 807 px, median short side).
  Compare boxes of the same size, 512 px and up: 92.1% against 60.8%.
- **A smaller tree in the picture?** No, the opposite. The median tele crown fills
  12.5% of its frame; the median zoom crown fills 10.2%.
- **Old box geometry?** No. All 5,388 zoom crowns and all 461 tele crowns come from
  the boxes in your export. Both rows of the table are now cut from one cache,
  on one geometry.
- **Wrong label on the wrong box?** No. In frames with two or more crowns, 217 tele
  predictions are wrong. **Zero** of them name a different labelled crown in the same frame.

**The confidence score also stops working.** When the top-1 score is 0.5 or more,
the zoom prediction is correct 94.3% of the time. The tele prediction is correct
only 71.7% of the time. The median top-1 score falls from 0.884 to 0.587.
So you must not re-use a threshold that was set on the 2024 photos.
The 0.5 cut in the contradiction queue is one of these thresholds.

**The model fails per species, almost completely.**
It is correct for Jacaranda copaia (70 of 70), Hieronyma alchorneoides (30 of 30),
and Poulsenia armata (13 of 13). It is wrong for Apeiba tibourbou (0 of 20),
Protium tenuifolium (0 of 24), and Apeiba membranacea (3 of 46).
The errors repeat: `Apeiba membranacea` becomes `Quararibea stenophylla` 24 times,
and `Protium tenuifolium` becomes `Protium stevensonii` 17 times.
These species are the best first task for Fernando.

**One warning about this table.**

The 461 tele crowns carry `IN_REVIEW` labels. A botanist has not confirmed
them. Bad labels make the model look worse than it is. They cannot explain a
difference of 34 points, and they do not explain the confidence problem. But
measure this again after Fernando confirms that batch.

Reproduce the whole table, offline, with
`python3 predict/crown_accuracy.py --cache-dir data/crowns_export/cache`.

---

## 6. Three tests that failed

I write these down so that nobody repeats them.

**Test 1. Is the `polygon` metadata a tree id?** No.
Two photos with the same `polygon` value are 1,333 m apart at the median.
Two random photos are 1,327 m apart. The values are the same.
The `polygon` value is the number in the file name. It is a waypoint index in one flight.
A different flight uses the same numbers for different trees.

**Test 2. Does the drone position identify the crown?** No.
I grouped the photos by GPS position. I scored each group against the botanist labels.
At a 5 m radius, only 27% of the groups hold one species.
At 10 m the figure is 19%. At 20 m it is 6%.
The GPS point is where the aircraft was, not where the tree is.

**Test 3. Is `polygon` a census tag in the crown map?** No.
I used `combined_crownmaps_2025.gpkg`, which holds 7,688 crowns with a `Tag` field.
Where the `Tag` equals the `polygon` value, the photo is 2,577 m from the crown at the median.
The nearest crown of any tag is 897 m away. The tag match is worse than no match.
I also limited the match to the plot of the flight. Only 72 of 1,744 photos resolve.
Those are still 315 m from the crown.

A point-in-polygon join is the correct method. It needs the camera footprint on the ground.
To compute the footprint you need the gimbal yaw, the gimbal pitch, the focal length,
the height above ground, and a canopy height model. The drone GPS point alone is not enough.

---

## 7. What I need from you

**A. The waypoint table.** These are waypoint flights.
Somebody made a flight plan that points the camera at chosen crowns.
That plan holds the link between the waypoint number and the crown.
That link is the missing piece. Please send me the table, or tell me who has it.
This is faster than a photogrammetric reconstruction, and more accurate.

**B. Export permission on the project and the dataset.**
Read-only is enough to list the data rows. It is not enough to read an annotation
or an embedding that Labelbox holds. The ranking no longer needs this, because
Pl@ntNet computes the embedding for me. But an export is still the only way to
read labels back without a hand-saved NDJSON file, so please fix the scopes.

**C. Nothing. The predictions are done.**
I did not need a decision here. All 3,269 identify calls are complete, and the
embeddings cost no identify credits at all.

---

## 8. How to run it

```sh
python3 labelling/fetch_dataset.py                       # read-only, ~45 s, 5201 rows
python3 labelling/next_batch.py \
    --export "Export  project - 2024_bci - 8_6_2026.ndjson"

python3 predict/embed.py                                 # 768 numbers per photo, no identify credits
python3 labelling/rank_unsent.py                         # writes queue_ranked.csv
python3 predict/crown_accuracy.py                        # the table in section 5, offline
```

Every one of these resumes. Stop it at any time and run it again.
`predict/embed.py` and `predict/crown.py` skip whatever is already cached, so a
stop on quota costs nothing.

**Two facts about the Pl@ntNet quota.** The allowance is 10,000 `identify`
requests each day, and it resets at 00:00 UTC, not at local midnight. Work done
in the evening here already counts against the next UTC day. Do not poll before
the reset, because the count cannot move. Wait for the time in the `Retry-After`
header of the 429 response.

Do not trust `/v2/quota/daily`. It reported 10,000 requests remaining at the same
moment that `identify` returned 429 with `remaining: 0`. The true figures are
`remainingIdentificationRequests` in the body of an `identify` response, and the
`Retry-After` header. `predict/embed.py` does not use the identify allowance at
all, so the ranking can be rebuilt on any day.

Outputs, in `data/next_batch/`:

| File | Rows | Use |
|---|---|---|
| `queue_ranked.csv` | 3,269 | **Send from the top.** The ranking in section 4. |
| `queue_contradictions.csv` | 76 | 5 are real. The `verdict` column says which. |
| `queue_missions.csv` | 32 | The unsent flights, largest first. |
| `queue_photos.csv` | 3,269 | Dispatch order only. Superseded by `queue_ranked.csv`. |
| `report.txt` | - | Every number on this page, with its test. |

Use `queue_ranked.csv`. The older `queue_photos.csv` sorts by flight, then by
camera, then by file size. The file size is a proxy for detail. I did not test it
on these photos. Do not read it as a measure of value.
