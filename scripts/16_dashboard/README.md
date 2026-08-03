# Per-species model health dashboard

One HTML page that answers a question you cannot get from a single accuracy number: **which BCI
species is Pl@ntNet already good at, which ones need labelling work, and which ones are hopeless?**

```bash
python3 scripts/16_dashboard/16_model_health.py     # measure -> 5 CSVs + run_log.txt
python3 scripts/16_dashboard/16b_dashboard.py       # render  -> model_health_dashboard.html
open output/16_dashboard/model_health_dashboard.html
```

Run them in that order. The first script measures and leaves an audit trail; the second turns the
measurement into something you can put in front of a botanist or a project meeting. The renderer
cross-checks itself against the first script's CSVs and refuses to build if they disagree.

Everything happens offline from files already on disk. No Labelbox key, no Pl@ntNet credits, no
network, no `pip install`. The page opens by double-clicking it, works as an email attachment, and
works in the field with no signal.

## Read this before you read the page

The same model has two accuracy numbers, and knowing why is most of the value here.

| | | |
|---|---|---|
| **81.3%** | per **crown** | Pick a labelled crown at random. This is the chance Pl@ntNet's first guess is right |
| **55.6%** | per **species** | Pick a *species*. This is its average chance, with every species counting once |

Both are correct. The gap is concentration: 26 abundant species account for most of the 2,589
evaluated crowns, so a per-crown average mostly reports how the model does on those few. Give every
species an equal vote and the model looks much weaker.

**The 55.6% is the number a labelling programme exists to move**, so it is the number the page leads
with. Quoting 81.3% is not wrong, it just answers a question nobody in this project is asking.

## What each panel is for

Each panel exists to support one decision. If it does not, it should not be on the page.

| Panel | The decision it supports |
|---|---|
| Hero (4 metrics) | Which headline to quote, and why two of them disagree |
| Accuracy vs labelled crowns | Where the measurement is solid enough to act on |
| Confidence bands | Whether confidence can be used to skip expert review at all |
| Error by support at conf ≥ 0.7 | Why confidence alone is not enough |
| Operating points | Which auto-accept rule to actually deploy |
| Per-species table | Which species to prioritise, and what kind of work each one needs |
| What labelling cannot fix | Which gaps are model limits, so nobody spends expert hours on them |
| Provenance | What was measured, on what, under which assumptions |

### The support curve is about abundance, not training

Accuracy climbs steadily with the number of labelled crowns a species has, from 23.4% at one crown to
86.1% at 25 or more. The obvious reading, "labelling makes the model better," is wrong here.

These predictions come from a **frozen** Pl@ntNet regional model that has never seen a single BCI
label and never will unless someone retrains it. Nothing on this page was trained on anything. What
the horizontal axis actually tracks is how common a species is on the plot, and common species also
tend to be well represented in Pl@ntNet's own reference photos. That is the whole correlation.

What extra labels really buy is **knowledge**. Below about 10 crowns, a per-species accuracy bounces
around too much to act on. Above it, the species becomes eligible for auto-accept, which is the point
at which a label starts saving expert time. The page says this on the panel itself so the chart cannot
be screenshotted into the wrong claim.

### Auto-accept, graded honestly

The recommended first deployment is **confidence ≥ 0.8 AND at least 10 labelled crowns for that
species.**

Why not confidence alone? Because confidence is well calibrated *in aggregate* and badly calibrated
*on rare species*, which is exactly where a wrong auto-accepted label does the most damage. Raising
the threshold does not fix that. Requiring the species to have been measured first does.

The rules are scored out of sample: eligibility (does this species have 10 or more labelled crowns?)
is decided from `train` crowns only, and the error rate is then measured on `test` crowns only. No
rule is graded on the crowns that defined it.

Any auto-accept rule ships with three conditions attached:

1. Accepted labels are tagged machine-accepted.
2. They never enter the evaluation set.
3. Thresholds are re-measured after every retrain, because a species crossing the 10-crown gate
   changes its own eligibility.

### The per-species status taxonomy

Each of the 169 species gets exactly one status. First matching rule wins, and the ordering is
deliberate.

| Status | Rule | What to do about it |
|---|---|---|
| **Model cannot return it** | never appears in any prediction | Nothing. Labelling cannot fix this |
| **Reliable** | 10+ crowns and top-1 ≥ 90% | Eligible for auto-accept. Spot-check only |
| **Ranking problem** | top-5 minus top-1 ≥ 20pp, and top-5 ≥ 60% | The cheapest work on the page. The right answer is already in the returned list, just not first, so this is a confirmation task rather than an identification task |
| **Not yet measurable** | fewer than 10 crowns | Label more before trusting any number for it |
| **Model struggles** | 10+ crowns and top-1 < 70% | Plenty of labels, still wrong. A model limit, not a labelling gap |
| **Adequate** | everything else | Keep in the review queue |

Why that order:

- **Model cannot return it** goes first because no amount of labelling moves it. Spending expert time
  here is pure waste and the page should say so before anything else.
- **Reliable** outranks **Ranking problem** because a species already at 90% does not need re-ranking.
- **Not yet measurable** sits *below* **Ranking problem** on purpose, so a thinly-labelled species
  whose answer is already in the returned list still surfaces as the cheap win it is.

Click any header to sort. Filter by name or by status.

## Why you can trust the numbers

The renderer does not read the CSVs and reformat them. It **recomputes** every number from the source
data, then compares its own results against the committed CSVs from `16_model_health.py`. A mismatch
aborts the build, so the page cannot quietly drift away from the measurement it claims to show:

```
verified  per_species_health.csv: 169 species, support/top-1/top-5 all match
verified  support_buckets.csv: 5 buckets, counts and top-1 match
verified  confidence_calibration.csv: 5 confidence bands match
verified  run_log.txt: the 87-crown never-scoreable ceiling matches
```

That last check earned its place. An earlier version had `87` typed into the page as a literal,
inside the very panel claiming nothing on the page is hardcoded.

Repeated runs are byte-identical (pass `--generated <date>` to freeze the one date stamp). The HTML
contains no URL, no `<link>`, no `<img>` and exactly one inline `<script>`, so it works from a
`file://` path with no network.

## Files

| File | Role |
|---|---|
| `health_core.py` | The data layer, and the only thing that reads the inputs. `load_health()` parses the prediction cache, joins it to ground truth, reconciles names via WCVP, aggregates per species, returns one `Health` record |
| `16_model_health.py` | The measurement. Headline, support buckets, filter simulation, ceiling, calibration. Writes 5 CSVs + `run_log.txt` |
| `16b_dashboard.py` | The page. Calls `load_health()`, verifies itself against the CSVs, emits one HTML file |
| `dashboard_assets.py` | CSS + JS. The CSS is a hand-pruned subset of `labelfirst`'s report styling so both reports look like one family |

One reader, two consumers. That is the point: a number cannot differ between the CSV and the page
because neither one computes it independently.

Both scripts accept `--gt`, `--splits`, `--cache-dir`, `--wcvp-cache`. See `--help`.

## Gotchas

- **`labelfirst`'s CSS is copied, not imported, and not copied whole.** `import labelfirst` drags in
  numpy, scipy, scikit-learn and pandas, and these scripts must run on the stdlib alone. Every rule
  kept is byte-identical to upstream, but 28 lines are dropped for elements this page does not have.
  So a future upstream restyle cannot be picked up by plain copy-paste; the prune has to be reapplied.
- **"Top-5" means the whole returned list, not the best 5 of a longer one.** We asked for
  `nb-results=5`. A correct answer sitting at rank 6 was never returned and is invisible here. For 45%
  of evaluated crowns fewer than 5 candidates came back at all, so for those the cap was not even
  binding.
- **The evaluation set is the historical labelling record, not a random sample.** These rates carry
  over to unlabelled crowns only under an assumption that cannot be tested offline. If you want a
  number that generalises, a random holdout has to be set aside before the next batch goes out, and it
  cannot be reconstructed afterwards.
- **Genus-only crowns are excluded** from every species number. There are 659 of them, 41.9% correct
  at genus level. They are reported separately and never folded in.
- **The predictions come from `identify/k-central-america`**, the Central America regional model, not
  the global one. A regional restriction is therefore already in force, so any proposal to "restrict
  the model to local species" has to start from that fact rather than treat it as a new idea.
