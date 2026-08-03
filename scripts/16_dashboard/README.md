# Per-species model health dashboard

One HTML page that answers: **how is Pl@ntNet doing on each BCI species, and what should we do about it?**

Everything is computed offline from files already on disk. No Labelbox API key, no Pl@ntNet
credits, no network call, no `pip install`. The page opens by double-clicking it.

```bash
python3 scripts/16_dashboard/16_model_health.py     # measure  -> 5 CSVs + run_log.txt
python3 scripts/16_dashboard/16b_dashboard.py       # render   -> model_health_dashboard.html
open output/16_dashboard/model_health_dashboard.html
```

The first script is the measurement and its audit trail. The second turns it into something
you can hand to a botanist or a project meeting. Run the first one first: the dashboard
cross-checks itself against its CSVs and refuses to build if they disagree.

## The one thing to understand before reading the page

Two numbers describe the same model:

| | |
|---|---|
| **81.3%** | accuracy per **crown** |
| **55.6%** | accuracy per **species** |

Both are correct. The gap is concentration: 26 abundant species carry most of the 2,589
evaluated crowns, so a per-crown average mostly reports how well the model does on those.
Averaged over species, where each species counts once regardless of how common it is, the
model is much weaker. **The second number is the one the labelling programme has to move**,
and it is the number the page leads with.

## What each panel is for

| Panel | The decision it supports |
|---|---|
| Hero (4 metrics) | Which headline to quote, and why they differ |
| Accuracy vs labelled crowns | Where the measurement is trustworthy enough to act on |
| Confidence bands | Whether confidence can be used to skip expert review at all |
| Error by support at conf ≥ 0.7 | Why a confidence-only rule is unsafe |
| Operating points | Which auto-accept rule to actually deploy |
| Per-species table | Which species to prioritise, and what kind of work each needs |
| What labelling cannot fix | Which gaps are a model limit, so nobody spends expert time on them |
| Provenance | What was measured, on what, under which assumptions |

### Read the support curve as abundance, not as training signal

Accuracy rises with the number of labelled crowns per species, and it is tempting to read
that as "labelling makes the model better." It does not. These predictions come from a
**frozen** Pl@ntNet regional model that has never seen a single BCI label. What the
horizontal axis really tracks is how common a species is on the plot, and common species
also tend to be better represented in Pl@ntNet's own reference photos.

What extra labels actually buy is **knowledge**: below about 10 crowns a per-species accuracy
is too unstable to act on; above it, the species becomes eligible for auto-accept. That is
the operational payoff, and the page says so on the panel itself.

### Operating points are measured out of sample

The auto-accept rules are graded honestly: eligibility (does this species have ≥10 labelled
crowns?) is decided from `train` crowns only, and the error rate is then measured on `test`
crowns only. No rule is scored on the crowns that defined it.

The recommended first deployment is **confidence ≥ 0.8 AND ≥10 labelled crowns for that
species**. Confidence alone is well calibrated in aggregate but badly calibrated on rare
species, which is exactly where a wrong auto-accepted label does the most damage. Raising the
threshold does not repair that; requiring the species to be measured first does.

Any auto-accept rule ships with three conditions: accepted labels are tagged
machine-accepted, they never enter the evaluation set, and the thresholds are re-measured
after every retrain (a species crossing the support gate changes its own eligibility).

### The per-species status taxonomy

Each of the 169 species gets exactly one status. First matching rule wins, and the order is
the point.

| Status | Rule | What it means you should do |
|---|---|---|
| **Model cannot return it** | species never appears in any prediction | Nothing. Labelling cannot fix this |
| **Reliable** | ≥10 crowns and top-1 ≥ 90% | Eligible for auto-accept; spot-check only |
| **Ranking problem** | top-5 − top-1 ≥ 20pp and top-5 ≥ 60% | Cheapest work on the page: the right answer is already in the returned list, just not first. A confirmation task, not an identification task |
| **Not yet measurable** | fewer than 10 crowns | Label more before trusting any number for it |
| **Model struggles** | ≥10 crowns and top-1 < 70% | Enough labels, still wrong. A model limit, not a labelling gap |
| **Adequate** | everything else | Keep in the review queue |

`Model cannot return it` outranks everything because no amount of labelling moves it.
`Reliable` outranks `Ranking problem` because a species already at ≥90% does not need a
re-rank. `Not yet measurable` sits *below* `Ranking problem` so that a thinly-labelled species
whose answer is already in the list still shows up as the cheap win it is.

The table sorts by clicking any header and filters by name or by status.

## Why you can trust the numbers

The dashboard does not read the CSVs and reformat them. It **recomputes** every number from
the source data, then compares its own results against the committed CSVs from
`16_model_health.py`. A mismatch aborts the build, so the page cannot silently drift from the
measurement:

```
verified  per_species_health.csv: 169 species, support/top-1/top-5 all match
verified  support_buckets.csv: 5 buckets, counts and top-1 match
verified  confidence_calibration.csv: 5 confidence bands match
```

Repeated runs are byte-identical (pass `--generated <date>` to freeze the one date stamp).
The emitted HTML contains no URL, no `<link>`, no `<img>` and exactly one inline `<script>`,
so it works from a `file://` URL, in an email attachment, and offline in the field.

## Files

| File | Role |
|---|---|
| `health_core.py` | Data layer. `load_health()` loads inputs, parses the prediction cache, joins to GT, reconciles names via WCVP, aggregates per species. Returns a `Health` record |
| `16_model_health.py` | The measurement: headline, support buckets, filter simulation, ceiling, calibration. Writes 5 CSVs + `run_log.txt` |
| `16b_dashboard.py` | The page. Reads `load_health()`, verifies against the CSVs, emits one HTML file |
| `dashboard_assets.py` | CSS + JS. The CSS is vendored verbatim from `labelfirst`'s report substrate so both reports look like one family |

Both scripts take `--gt`, `--splits`, `--cache-dir`, `--wcvp-cache`; see `--help`.

## Gotchas

- **`labelfirst`'s CSS is vendored, not imported.** `import labelfirst` pulls
  numpy/scipy/scikit-learn/pandas, and these scripts must run from the stdlib alone. If you
  restyle `labelfirst`'s reports, the two will drift until someone re-copies `_CSS`.
- **"Top-5" is the whole returned list, not the top 5 of a longer one.** We requested
  `nb-results=5`. A correct answer at rank 6 was never returned and is invisible here. 45% of
  evaluated crowns came back with fewer than 5 candidates, so for those the cap was not even
  binding.
- **The evaluation set is the historical labelling record, not a random sample.** These rates
  transfer to unlabelled crowns only under an assumption that cannot be tested offline.
- **Genus-only crowns are excluded** from every species number (659 of them, 41.9% correct at
  genus level). They are reported separately, never folded in.
- **The predictions are from `identify/k-central-america`**, the Central America regional
  model, not the global one. A regional restriction is therefore already in place; proposals to
  "restrict the model to local species" need to start from that fact.
