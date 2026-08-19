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

## 4. What I cannot do, and why

I cannot rank the 3,269 unsent photos by value. Three things are missing.

**Predictions.** No cached Pl@ntNet result exists for any of the 3,269 photos.
The local cache covers the legacy corpus only. I can run the predictions.
That is 3,269 API calls. Tell me if you want that.

**Embeddings.** You said the embeddings are available. They are, but not to me.
An embedding is readable only through an export task.
The key I have cannot create one. This is not a role problem: the key reports
`org role: Admin` in the LEFO organization. Export still fails, for the dataset
as well as for the project:
`AuthorizationError: Insufficient permissions to perform this action`.
So please check the scopes on that key, or issue one with export enabled.

**Crown identity.** I cannot tell a new tree from a tree that was photographed before.
I tested three methods. All three fail. Section 5 gives the numbers.

---

## 5. Three tests that failed

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

## 6. What I need from you

**A. The waypoint table.** These are waypoint flights.
Somebody made a flight plan that points the camera at chosen crowns.
That plan holds the link between the waypoint number and the crown.
That link is the missing piece. Please send me the table, or tell me who has it.
This is faster than a photogrammetric reconstruction, and more accurate.

**B. Export permission on the project and the dataset.**
Read-only is enough to list the data rows. It is not enough to read an embedding.
Without an export I cannot use the embeddings for active learning.

**C. A decision on the predictions.**
Say yes and I run Pl@ntNet on the 3,269 unsent photos. Then the ranking becomes possible.

---

## 7. How to run it

```sh
python3 labelling/fetch_dataset.py                       # read-only, ~45 s, 5201 rows
python3 labelling/next_batch.py \
    --export "Export  project - 2024_bci - 8_6_2026.ndjson"
```

Outputs, in `data/next_batch/`:

| File | Rows | Use |
|---|---|---|
| `queue_contradictions.csv` | 76 | 5 are real. The `verdict` column says which. |
| `queue_missions.csv` | 32 | The unsent flights, largest first. |
| `queue_photos.csv` | 3,269 | Dispatch order only. Not a priority ranking. |
| `report.txt` | - | Every number on this page, with its test. |

`queue_photos.csv` sorts by flight, then by camera, then by file size.
The file size is a proxy for detail. I did not test it on these photos.
Do not read it as a measure of value.
