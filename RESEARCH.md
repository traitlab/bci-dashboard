# How each research check works

The table in the README says which script writes which file. This file says what each check does. Every check starts from the 768 numbers Pl@ntNet makes per centre crop: close numbers mean two photos look alike to the model.

## On the queue page

**Does the order beat a random order?** `rank_queue.py --audit` replays labelling on the labelled frames. Each replay starts from 200 random labelled frames and adds 20 rounds of 20 photos. It counts the rare species found, meaning those with 5 labelled frames or fewer. The order and a random order each run from 8 random starts. labelfirst compares the two curves and gives a range and a p-value. First, `predict_al_benefit` asks if any order can help: how often does a labelled frame's nearest neighbour have the same species?

**Is it finding plants, or places?** A photo can look new because it comes from a new site or export batch, not a new species. `rank_queue.py --confound` holds the site or the export batch fixed and asks if "looks new" still goes with "rare species". It shuffles the frames inside each group 5,000 times to see how often chance does as well. The page says the link holds, is partly the batch, or is mostly the batch.

**Species found per photo.** `rank_queue.py --backtest` puts the labelled frames in order without reading their labels. It compares the species found against 16 random orders, and the queue page draws the curve.

## On the model-health page

`assess_species.py` writes four assessments into `data/model_health/`. The page does not build when one is missing or stale, and it names the command that fixes it.

**What would help each species?** Hide the labels on half of the labelled frames. The 5 closest labelled frames vote on the name of each hidden frame. Do this 8 times, with a different half each time. Then, per species:

- Right 90% of the time or more: "no gap found".
- Less than 10% of its frames kept a label: "more labels".
- Else: "better model".

The page shows how many of the 8 draws agree, and stays blank under 10 frames.

**Why do the two names differ?** crownfirst lists the frames where Pl@ntNet's top prediction is not the label. It sorts each one as two different species, one species under two names, or a label that stops at genus or family.

**How many plausible names?** A plain classifier learns from how the photos look, in 5 folds. For each frame it lists the names it cannot rule out, built to hold the right name 90% of the time. For lists of 1, 2, 3, 5 and 10 names, it reports how many frames get one and how often the first name is right. A second run keeps each flight whole in one fold. This classifier is not Pl@ntNet.

**How many species are still unlabelled?** labelfirst's `estimate_richness` counts the species seen once and seen twice. From those counts it estimates how many species no label names yet (Chao1).

## Behind every grade

**Flights held back whole.** Frames from one flight are near-copies of each other. `draw_holdout.py` holds back 1 flight in 5, and every species with two or more flights keeps one for training. Training frames from another flight within 30 m of a held frame are dropped too. The queue never sends a held frame, and the model-health page grades Pl@ntNet again on them.

## Other uses

- `labelling/rank_arms.py` tests two more orders against a random order, with labelfirst's ordering rules.
- `labelling/measure_similarity_range.py` measures how far apart two photos must be before they stop looking alike.
- `predict/ingest_photos.py` and `predict/aggregate_survey.py` use labelfirst to pool the results per tile into one vector and one species score per photo.
- When `data/crownfirst/plantclef2024_tile2x2_max.json` exists, the refresh adds a second view to the atlas page. It shows how the photos look to a crownfirst test model.

