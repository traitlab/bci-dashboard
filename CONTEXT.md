# The words this project uses

One name per thing. Code, page prose and handover notes all use the name in the
left column. If a page needs a word that is not here, add it here first.

The right-hand column is the plain-English wording that goes on a built page.
Where the two differ, the page wins: a reader of the page is not a reader of
this file.

## What we photograph and label

| Term | What it means, and how a page says it |
|---|---|
| **frame** | One 4000x3000 drone photo. The unit everything is counted in. |
| **crown** | One tree canopy a botanist outlined inside a frame. |
| **label** | The species a frame belongs to: the one whose outlined crowns cover the most area in the whole frame. Also called the botanist's label. Never "ground truth" on a page. |
| **centre crop** | The fixed 1280x1280 square from the middle of a frame, 13.65% of it. This is what gets sent to Pl@ntNet on the old path. |
| **labelled frame** | A frame that has a botanist's label. The count of these for one species is how much evidence we have about that species; on a page, "labelled frames", never "support". |
| **unlabelled photo** | A frame with a Pl@ntNet guess and no botanist label. The pool the queue orders. |
| **site** | One field location. There are 17; frames from the same site are alike, which is why a range is worked out by drawing whole sites. |
| **lens** | zoom or tele. Every scored frame so far is zoom. |

## What the model does

| Term | What it means, and how a page says it |
|---|---|
| **Pl@ntNet** | The naming service. It is frozen: it has never seen a BCI label, and labelling does not make it better. |
| **the five candidates** | The five names we ask Pl@ntNet for per photo (`nb-results=5`). Our request setting, not a limit of the model. |
| **first guess** | The top-ranked of those five. Never "top-1" on a page. |
| **right** | The first guess matches the frame's label. Never "hit" on a page. |
| **right name in the list** | The label is somewhere in the five, but not first. Never "top-5" on a page. |
| **confidence** | Pl@ntNet's own score for its first guess, 0 to 1. Trustworthy in bulk, not on rarely-labelled species. |

## The two ways of asking

The whole difference between the two headline numbers. A page names the way of
asking, never calls it an **arm**: that word belongs in `hypothesis.md`.

| Term | What it means, and how a page says it |
|---|---|
| **crown-by-crown** | One Pl@ntNet call per outlined crown, and the answers pooled to the frame by how much of it each crown covers. The same rule the frame's label is built from. Was "region-aligned". |
| **centre crop only** | One Pl@ntNet call on the fixed middle square. The older path, and the one every corpus-wide number on the page still uses. Was "photo arm" or "centre crop, legacy". |
| **tiles** | A third way of asking, cut from the study on 2026-08-27 after its interim number had been seen. It is named on the page because dropping it late is a cost a reader is entitled to weigh. |

## How a number is reported

| Term | What it means, and how a page says it |
|---|---|
| **per species** | Every species counts once, however few frames it has. Was "macro". |
| **per frame** | Every labelled frame counts once, so common species dominate. Was "micro". |
| **the range** | The 95% interval around a rate. On a page: "we are 95% sure the true rate is between X and Y". The word **bootstrap** does not appear on a page; the method is stated as "we re-ran the count 10,000 times, each time drawing whole sites at random". |
| **the frozen sample** | The 300 frames fixed on 2026-08-26, before any of these numbers existed. Was "the confirmatory sample". |
| **fixed in advance** | Every rule was written down in `bci-dashboard-docs/hypothesis.md` before the data existed. Was "pre-registered". |
| **already seen** | Someone had seen a number from the crown-by-crown way, at another unit, before the sample was frozen. Was "prior exposure". |
| **gated / ungated** | With and without the crop-coverage condition. Reported side by side, always. On a page the condition is spelled out rather than named. |

## What the pages are

| Term | What it means |
|---|---|
| **model-health page** | `build/model_health_dashboard.html`. How well Pl@ntNet names what a botanist labelled. The page that leaves the lab. |
| **queue page** | `build/label_queue_dashboard.html`. What to label next. The labelling team's own tool; the deliverable beside it is `send_batches.csv`. |
| **snapshot** | One dated folder under `snapshots/` holding the CSVs a measurement pass wrote. A page is cross-checked against one and refuses to build if it disagrees. |
| **panel** | One collapsible block on a page. Its summary must stand alone when everything is closed. |
| **status** | One of six plain verdicts a species gets: right name in the list, too few labels to judge, wrong even with enough labels, mixed, usually right, never named in five candidates. |
