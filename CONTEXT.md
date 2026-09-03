# The words this project uses

One name per thing. Use the left column in code, page prose and handover notes.
A word not here gets added here first. The right column is the wording a built
page uses; where the two differ the page wins.

## What we photograph and label

| Term | What it means, and how a page says it |
|---|---|
| **frame** | One 4000x3000 drone photo. The unit everything is counted in. |
| **crown** | One tree canopy a botanist outlined inside a frame. |
| **label** | The species whose outlined crowns cover the most area in the whole frame. Never "ground truth" on a page. |
| **centre crop** | The fixed 1280x1280 square from the middle of a frame, 13.7% of it. What the old path sends to Pl@ntNet. |
| **labelled frame** | A frame that has a botanist's label. On a page, "labelled frames", never "support". |
| **unlabelled photo** | A frame with a guess and no label. The pool the queue orders. |
| **site** | One field location. There are 17; frames from one site are alike, so a range is drawn by whole sites. |
| **file naming** | `zoom` and `tele` in frame names. A naming change, not a second camera: all 449 `tele` frames come from missions that also produced `zoom` ones, and their March 2026 date is when the names were written, not when they were flown. Call them file namings or export batches, never cameras and never lenses. Every scored frame carries `zoom`. |

## What the model does

| Term | What it means, and how a page says it |
|---|---|
| **Pl@ntNet** | The naming service. Frozen: it has never seen a BCI label, and labelling does not make it better. |
| **the five candidates** | The five names we ask Pl@ntNet for per photo (`nb-results=5`). Our request setting, not a limit of the model. |
| **first guess** | The top-ranked of the five. Never "top-1" on a page. |
| **right** | The first guess matches the frame's label. Never "hit" on a page. |
| **right name in the list** | The label is in the five but not first. Never "top-5" on a page. |
| **confidence** | Pl@ntNet's score for its first guess, 0 to 1. Trustworthy in bulk, not on rarely-labelled species. |

## The two ways of asking

The whole difference between the two headline numbers. A page names the way of
asking, never "arm".

| Term | What it means, and how a page says it |
|---|---|
| **crown-by-crown** | One call per outlined crown, pooled to the frame by how much of it each crown covers. The rule the frame's label is built from. Was "region-aligned". |
| **centre crop only** | One call on the fixed middle square. The older path, and what every corpus-wide number on the page still uses. Was "photo arm". |
| **tiles** | A third way, cut on 2026-08-27 after its interim number had been seen. Named on the page because a late drop is a cost a reader can weigh. |

## How a number is reported

| Term | What it means, and how a page says it |
|---|---|
| **per species** | Every species counts once, however few frames it has. Was "macro". |
| **per frame** | Every labelled frame counts once, so common species dominate. Was "micro". |
| **the range** | The 95% interval around a rate. On a page: "we are 95% sure the true rate is between X and Y". Never "bootstrap"; the method is "we re-ran the count 10,000 times, each time drawing whole sites at random". |
| **the frozen sample** | The 300 frames fixed on 2026-08-26, before any of these numbers existed. Was "the confirmatory sample". |
| **fixed in advance** | Every rule written down in `bci-dashboard-docs/hypothesis.md` before the data existed. Was "pre-registered". |
| **already seen** | Someone had seen a crown-by-crown number, at another unit, before the sample was frozen. Was "prior exposure". |
| **gated / ungated** | With and without the crop-coverage condition, always side by side. A page spells the condition out, never "gated" or "ungated". |

## Ordering the queue

| Term | What it means, and how a page says it |
|---|---|
| **the confidence line** | The confidence a frame must clear before a rule pushes it down the queue. Never "threshold" on a page. |
| **pushed down the queue** | What the wait rule does to a frame. An ordering, never a label, undone at the next model change. Never "deprioritised", never "revocable". |
| **the labelled-frames condition** | The wait rule's second half: the species needs enough labelled frames already. Spelled out, not called a gate. |
| **queue** | One of four groups the unlabelled pool is sorted into, worked top to bottom. |
| **how a photo looks** | The 768 numbers Pl@ntNet makes from a centre crop. Close numbers mean two photos look alike to the model. A page says "how the photo looks to the model", never "embedding" and never a score. |
| **least like everything already labelled** | The order inside a queue: furthest from every labelled photo first, confidence only breaking ties. Never "farthest-first". `coverage` stays a crop word, as in `coverage_gate.csv`. |
| **the labelled photos it is compared against** | The 1,719 frames already named, all carrying `zoom`. A page names the count and the naming, because a photo from a later export batch can look new for its batch rather than for its species. |
| **held back for grading** | The frames a rule is scored on, kept out of the frames it learns from. A page spells the split out, and may cite which value of `split` in `splits.csv` holds them. |
| **confidence band** | A range of confidence, written "0.7 to 0.8" and "0.9 and up". The CSVs keep `[0.7,0.8)`; a page never shows it. |

## What the pages are

| Term | What it means |
|---|---|
| **model-health page** | `build/model_health_dashboard.html`. How well Pl@ntNet names what a botanist labelled. The page that leaves the lab. |
| **queue page** | `build/label_queue_dashboard.html`. What to label next. The labelling team's own tool; the deliverable is `send_batches.csv` in `build/tables`. |
| **snapshot** | One dated folder under `snapshots/` holding a day's CSVs and pages. A record kept for the trend; no build reads one back. A page is cross-checked against `build/tables` and refuses to build if it disagrees. |
| **panel** | One collapsible block on a page. Its summary must stand alone when everything is closed. |
| **status** | One of seven plain verdicts a species gets: right name in the list not first, too few labels to judge, wrong even with enough labels, mixed, usually right, never returned on any BCI photo, not in the project's own species list. |
