# Per-species model health dashboard

One HTML page that answers a question you cannot get from a single accuracy number: **which BCI
species is Pl@ntNet already good at, which ones need labelling work, and which ones the model cannot
name at any threshold?**

```bash
python3 dashboard/measure.py      # measure -> 5 CSVs + run_log.txt
python3 dashboard/build_full.py   # render  -> model_health_dashboard.html
open build/model_health_dashboard.html
```

Run them in that order. The first script measures and leaves an audit trail; the second turns the
measurement into something you can put in front of a botanist or a project meeting. The renderer
cross-checks itself against the first script's CSVs and refuses to build if they disagree.

Everything happens offline from files already on disk. No Labelbox key, no Pl@ntNet credits, no
network, no `pip install`. The page opens by double-clicking it, works as an email attachment, and
works in the field with no signal.

## How the page is laid out

It opens as a short summary. Four sections are expanded on arrival, eight are folded away behind a
one-line heading that says what is inside, so nobody has to scroll past a 169-row table to reach the
next decision.

| | Section | The decision it supports |
|---|---|---|
| | Four headline numbers | Which number to quote, and why two of them disagree |
| **open** | Why only 5 guesses per photo | Whether to spend credits on a re-ingest with a longer candidate list |
| **open** | Why one score says 81% and the other 56% | Which of the two headline scores answers the question you are asking |
| **open** | Where to spend botanist time next | What to work on, ordered cheapest useful work first |
| **open** | Trend over N points | Whether a number moved because the model changed or because more crowns were labelled |
| **open** | Which crowns can wait | How to order the review queue |
| | What to send to the botanist first | Which of the unlabelled photos are the next batch: the long tail first, then weak guesses on usually-right species |
| | How the five candidate rules compare | Whether to move the confidence threshold |
| | Can we trust the model's confidence? | Whether confidence alone is enough to order the queue |
| | Does accuracy rise with more labels? | Where the measurement is solid enough to act on |
| | Look up one species | The status of a species you care about |
| | Labels worth a second look | Which labelled crowns to send back for review: confident disagreements between model and botanist |
| | What labelling cannot fix | Which gaps no labelling can close, and which of those need a re-ingest rather than expert hours |
| | How this was measured | What was measured, on what, under which assumptions |

Every section starts with one sentence, before any number, saying what to do with what follows. The
page is written for a reader who knows trees and does not know machine learning, so it says "right
name in the list" rather than "top-5", "labelled crowns" rather than "support", and no section
assumes you read the one above it.

The send-first order comes from the 2026-08-05 call: the two things to focus
labelling on are the long tail (species barely labelled, or wrong even with enough labels) and
low-confidence guesses on species the model usually gets right. Confident disagreements with the
botanist label go back for review only after those queues, scoped on the call as later work: each
one is either a rare confident model error or a label error, and offline there is no way to tell
which, so resolving them costs expert minutes that the long tail spends better first. Junk photos are not auto-filtered (the call was explicit that no rule recognises
them), but the page counts the unlabelled photos whose candidate list came back empty, the one
signal Pl@ntNet gives, so a by-eye sample costs minutes.

## Read this before you read the page

The same model has two accuracy numbers, and knowing why is most of the value here.

| | | |
|---|---|---|
| **81.3%** | per **crown** | Pick a labelled crown at random. This is the chance Pl@ntNet's first guess is right |
| **55.6%** | per **species** | Pick a *species*. This is its average chance, with every species counting once |

Both are correct. Two things make the gap: 26 abundant species hold 1,856 of the 2,589 evaluated
crowns, and accuracy climbs with abundance (23.4% right for species with a single labelled crown,
86.1% for those with 25 or more). So a per-crown average mostly reports how the model does on the few
species it already knows best. Give every species an equal vote and the model looks much weaker. The
page draws this as two bars over the same five groups, one weighted per species and one per crown.

**The 55.6% is the number a labelling programme exists to move**, so it is the number the page leads
with. Quoting 81.3% is not wrong, it just answers a question nobody in this project is asking.

There is a third denominator, and the page states it beside the headline: of the crowns this
evaluation **can possibly score**, 83.41% are right (2106/2525). The remaining 64 crowns belong to 16
species whose name appears in no cached prediction at all, so they are wrong at every threshold. No
tuning and no name cleaning can ever score them.

### The camera gap is reported raw, then decomposed

`predict/crown_accuracy.py` scores crown boxes rather than photos and splits the
result by camera. On the export-geometry cache it reports 86.1% top-1 on 5,388
zoom crowns against 51.8% on 461 tele crowns. Both figures are raw: each is what
those crowns actually scored, and each keeps the headline position.

Raw alone invites the gap to be read as a property of the camera, so the tool
also prints a `decomposition` block. It applies direct standardization: hold the
tele species composition fixed and substitute zoom's per-species accuracy. That
splits the 34.2 points into three named steps.

| Step | Top-1 | Drop | What the step is |
|---|---|---|---|
| zoom, every labelled crown | 86.1% | | 5,388 crowns |
| tele, if each species scored as it does on zoom | 70.6% | 15.5 | species composition |
| tele, observed, species with a zoom baseline | 60.6% | 10.0 | everything else |
| tele, observed, every labelled crown | 51.8% | 8.7 | species zoom has never seen |

The last step is 83 crowns of 13 species with fewer than `MIN_BASELINE_N` zoom
crowns, scoring 12.0%. They are excluded from the standardization because no zoom
rate exists for them, and standardizing over them would invent one.

The middle step carries the confound. All 461 tele crowns come from one mission,
so camera, site, day, light and annotator move together in that 10 points. Zoom's
35 missions with 30 or more crowns span 62.7% to 100%, median 87.1%, so a single
mission at 60.6% sits inside the low part of a known spread rather than outside
it. The decomposition says how large each part is. It does not attribute the
middle part to the camera, and neither should anything quoting it.

Control 1 in the same output subsets to the species both cameras show without
reweighting. It answers a different question and does not detect the composition
step.

### "The model never names it" is a claim about what we asked for

That 64-crown floor is measured against the **corpus vocabulary**: every species name that turns up
somewhere in the cached lists of candidates. It is the only test available offline, and it is weaker
than it looks. We asked Pl@ntNet for its best five candidates per photo. A species Pl@ntNet knows
perfectly well, but which never reached anyone's top five on a BCI photo, is indistinguishable here
from a species it genuinely cannot return.

Two limits cut that list, one at each end, and only one of them is ours. We cut at five from the top.
Pl@ntNet cuts from the bottom: across the 12,754 guesses behind this page not one scores below
0.1%, and the smallest is exactly 0.001, so a list comes back short when fewer than five species
clear that floor. That happened on 1,318 of the 3,248 crowns with a cached answer (40.6%), where
our cap never bit. On the other 1,930 the list was full and anything ranked sixth is invisible.

A short list is not an exhausted one. Pl@ntNet spreads 100% of its confidence over every species it
knows, and the returned scores account for a median 96.7% of it on one-guess photos and 93.2% on
four-guess photos, the remainder being species that each scored under 0.1%. A full list of five
accounts for a median 71.4%, so on those photos roughly 28.6% of the model's confidence sits on
species we never received, and on 589 of the 1,930 (30.5%) more than half of it does. **That** is
the size of the blind spot, and it is measured, not assumed.

**The fix is re-ingesting the predictions with more results requested, not more name cleaning.** A
re-ingest should also pass `detailed=true`, which the same endpoint documents as returning "extra
identification results such as results per family and results per genus" under `otherResults`.
That removes two workarounds at once: genus-only labels are currently scored by chopping the genus
off a predicted binomial, and the 95 family-only labels cannot be scored offline at all, because
the local WCVP cache carries a family only for the 249 BCI names and not for Pl@ntNet's vocabulary.
The page says all of this on its own panel, because "the model never names it" reads like a model
verdict and is not one.

### Name matching is a gain, not a cost

Ground-truth labels and predictions are canonicalised **identically** before they are compared, and
superseded names are resolved to current ones. Scoring the raw strings instead gives 80.15%
(2075/2589) rather than 81.34%, so the matching is worth **+1.20 points, 31 crowns**. Nothing on the
page should be read as spelling mismatch causing error; it is a gain already banked. The renderer
verifies the unreconciled baseline against the run log so the claim cannot drift.

## The trend, and the trap in it

History lives in the snapshot folders `snapshots/model-health-<date>/`. On every build the renderer
globs them, summarises each into `history.csv` next to the current snapshot's CSVs, and draws the
result: a small line beside each headline number, a narrow trend column in the species table, and a
two-series chart in the trend section.

`history.csv` has one row per point, model and metric:

```
snapshot_date,model_tag,n_crowns,metric,value,source
2026-08-03,k-central-america@v7.4-2026-03-27,2589,macro_top1,0.555604,measured
2026-05-25,k-central-america@v7.4-2026-03-27,1250,macro_top1,0.566169,reconstructed
```

It is **append-only**. A point's rows are written the first time it is seen and never
rewritten, so the trend cannot be quietly re-authored by a later run. If a snapshot is re-measured,
delete its rows and rebuild; a verification check makes that failure loud rather than silent.

### Backfilled points

Health was first measured on one day, which would leave one point and no trend. But the predictions
arrived in batches and every cached response carries the day it was fetched, so each evaluated crown
can be attributed to its batch. Scoring the crowns fetched up to each batch date gives the numbers
this page would have printed then, marked `source=reconstructed`. On the current cache that is
two extra points, 2026-05-25 (1250 crowns) and 2026-05-27 (all 2589).

The reconstruction is honest about the data mix and silent about the model: it re-scores old crowns
with today's predictions, so a backfilled point cannot show what an older Pl@ntNet model would have
said. It refuses to run at all if any crown cannot be dated or if every crown shares one date, so a
cache copied without its mtimes shows as no history rather than as a false one. Two checks hold it
down: the newest reconstructed point covers every crown, so it must equal the live measurement, and
every stored reconstructed point must still recompute to its stored value.

What the backfill actually shows here is the composition trap, not progress. Under one frozen model
crown-weighted top-1 rose 76.3% to 81.3% while per-species top-1 fell 56.6% to 55.6%: the second
batch added crowns of species already covered, which lifts the crown-weighted number, plus new rare
species, which drags the per-species one down. Neither move is learning. Pl@ntNet never sees these
labels.

Accuracy axes never draw narrower than 10 points (`RATE_SPAN`), so a one-point wobble reads as a
wobble instead of filling the plot.

**The trap.** Pl@ntNet ships a new model every few months, on its own schedule rather than the
labelling programme's. So a metric that moves can mean a new model **or** more labels, and a page
that plots one line invites the wrong conclusion. Both series are plotted, `n_crowns` and the metric,
each on its own scale. Snapshots where `model_tag` changed are marked with a hollow red ring and a
dashed rule, on the small trend lines as well as the chart, and the caption under a marked step names
how much **each** axis moved and says outright that the step cannot attribute one to the other. A
jump at a model boundary therefore looks different from drift under a constant model.

With one point the section says "first snapshot, no trend yet" and draws nothing.

### `model_tag`

The tag identifies the Pl@ntNet model iteration and is read per snapshot from **that snapshot's own**
`run_log.txt`, which records the endpoint it called and `config.yaml`'s `single_model_run_name`:

```
model_tag = <endpoint slug>@<run name>      e.g. k-central-america@v7.4-2026-03-27
```

Those two strings are the only thing on disk that distinguishes one Pl@ntNet iteration from the next;
the cached response JSONs carry no version field. A snapshot whose log names neither falls back to
`--model-tag`, which defaults to `unknown`. Nothing is invented.

## Which crowns can wait, not which labels are done

The suggested rule is **confidence ≥ 0.8 AND at least 10 labelled crowns for that species.** On
held-out test crowns that covers 182 of 442, and the first guess is wrong on 1.1% of them.

It is a **queue-ordering** rule, the same job it does in `labelfirst` and `speciesfirst`. It says
*these crowns can wait, work on the others first.* It does not say *these labels are done.*

- **Nothing it touches is a label.** A crown that can wait keeps whatever ground truth it already
  has, or none at all. No prediction is ever written into ground truth by this rule.
- **The decision expires with the model.** A crown deprioritised under
  `k-central-america@v7.4-2026-03-27` is not deprioritised under the next iteration. Rebuild after
  every model change and the queue re-sorts. Any crown can come back to the top.

Why two conditions rather than a higher threshold? Because confidence is well calibrated *in
aggregate* and badly calibrated *on rare species*, which is exactly where a wrongly deprioritised
crown does the most damage. Raising the threshold does not fix that. Requiring the species to have
been measured first does.

The rules are scored out of sample: eligibility (does this species have 10 or more labelled crowns?)
is decided from `train` crowns only, and the error rate is then measured on `test` crowns only. No
rule is graded on the crowns that defined it.

### The support curve is about abundance, not training

Accuracy climbs steadily with the number of labelled crowns a species has. The obvious reading,
"labelling makes the model better," is wrong here.

These predictions come from a **frozen** Pl@ntNet regional model that has never seen a single BCI
label and never will unless someone retrains it. Nothing on this page was trained on anything. What
the axis actually tracks is how common a species is on the plot, and common species also tend to be
well represented in Pl@ntNet's own reference photos. That is the whole correlation.

What extra labels really buy is **knowledge**. Below about 10 crowns a per-species accuracy bounces
around too much to act on. Above it, the species can enter the queue-ordering rule, which is the point
at which a label starts saving expert time. The page says this on the chart itself so it cannot be
screenshotted into the wrong claim.

## The per-species statuses

Each of the 169 species gets exactly one status. First matching rule wins, and the "where to spend
botanist time next" panel is ordered cheapest useful work first.

| Status | Rule | What to do about it |
|---|---|---|
| **Right name in the list, not first** | list minus first guess ≥ 20pp, and list ≥ 60% | Cheapest work here. Confirm the name from the short list instead of identifying from scratch |
| **Too few labels to judge** | fewer than 10 crowns | Label a few more before trusting any number for it |
| **Wrong even with enough labels** | 10+ crowns and first guess < 70% | More labels will not fix this one. Treat it as a model limit |
| **Mixed** | everything else | Keep it in the normal review queue |
| **Usually right** | 10+ crowns and first guess ≥ 90% | Lowest priority. Spot-check a few and move on |
| **Model never names it** | never appears in any cached top-5 list | More labelling will not move it. Whether Pl@ntNet can name it at all is unsettled: we hold no project checklist |

The rule order is not the display order, and both are deliberate:

- **Model never names it** is matched *first* because no amount of labelling moves it.
- **Usually right** is matched before **Right name in the list, not first**, because a species already
  at 90% does not need re-ranking.
- **Too few labels to judge** is matched *after* **Right name in the list, not first**, so a thinly
  labelled species whose answer is already in the returned list still surfaces as the cheap win it is.
- The panel then shows them cheapest-first, with the two rows you can skip last.

Click any header in the species table to sort. Filter by name or by status.

## Why you can trust the numbers

The renderer does not read the CSVs and reformat them. It **recomputes** every number from the source
data, then compares its own results against the CSVs `dashboard/measure.py` wrote. Those CSVs are
build outputs and are not tracked in git, so the check binds the page to whatever measurement is on
disk right now; run the measurement script first, or the renderer has nothing to check against. A
mismatch aborts the build, so the page cannot quietly drift away from the measurement it claims to show:

```
verified  per_species_health.csv: 169 species, crowns and both rates match
verified  support_buckets.csv: 5 labelled-crown groups match
verified  confidence_calibration.csv: 5 confidence bands match
verified  run_log.txt: the 86-crown ceiling, the 64 unscoreable evaluated crowns and the 2075-hit unreconciled baseline match
verified  history.csv: 3 point(s), 2 reconstructed from ingest dates; the newest measured and newest reconstructed point both match the live crown count and both headline rates
verified  send_first_queue.csv: 4,420 unlabelled crowns across 4 queues match
verified  send_batches.csv: N rows in M batches, one species and at most 100 rows each
verified  label_review_queue.csv: 33 crowns, 30 confusion pairs match
verified  charts: a rising series is drawn rising and a bigger share is drawn wider
```

The fourth check covers the three figures that live in the run log's prose rather than in any CSV,
because the page states them on denominators the CSVs never use, plus the count of unlabelled
photos whose candidate list came back empty, which lives in the same prose. It earned its place: an
earlier version had the ceiling count typed into the page as a literal, inside the very panel
claiming nothing on the page is hardcoded. The fifth defends the append-only trend store, where a
re-measured snapshot would otherwise leave a stale point behind. The last is geometric rather than
numeric: a sign slip in the pixel scaling flips every chart on the page while leaving every number
on it correct, which is exactly what happened once, so a rising series is now asserted to rise. It
also covers the weighting bars, where a share read off the wrong denominator would draw a bar that
stops short of full width without changing a single printed number.

Repeated runs are byte-identical (pass `--generated <date>` to freeze the one date stamp). The HTML
contains no URL, no `<link>`, no `<img>` and exactly one inline `<script>`, so it works from a
`file://` path with no network.

## Why one HTML file, and not a `labelfirst` report

The readers are botanists and a PI, and most of them have no Python environment. One file that opens
from a `file://` path attaches to an email, sits in a shared folder beside the snapshot it describes,
and still opens in five years. That is the whole requirement, and it decides the format.

It follows that the page cannot import `labelfirst` or `speciesfirst`. `import labelfirst` pulls
numpy, scipy, scikit-learn and pandas; this page needs none of them, and adding them would make the
artifact depend on an environment that has to be resolvable at read time rather than at build time.
So these scripts run on the standard library alone, and `labelfirst`'s report CSS is vendored as a
hand-pruned copy rather than imported. The cost is stated in Gotchas below: an upstream restyle has
to be re-pruned by hand, and the two report families drift until someone does it.

What is shared with `labelfirst` and `speciesfirst` is the decision, not the code. The
deprioritization rule here orders a botanist's queue exactly as it does there, and it never writes a
prediction into ground truth in any of the three.

## Files

| File | Role |
|---|---|
| `dashboard/core.py` | The data layer, and the only thing that reads the inputs. `load_health()` parses the prediction cache, joins it to ground truth, reconciles names via WCVP, aggregates per species, returns one `Health` record. Also holds `queue_of_prediction()`, the send-first queue logic shared by both scripts so they cannot drift apart |
| `dashboard/measure.py` | The measurement. Headline, support buckets, filter simulation, ceiling, calibration, send-first queue, label review queue. Writes 7 CSVs + `run_log.txt` |
| `dashboard/build_full.py` | The page. Calls `load_health()`, recomputes every figure, emits one HTML file |
| `dashboard/history.py` | Everything that reads the measurement *back*. `verify_snapshot()` aborts the build when the page and the snapshot disagree; `load_trend()` reads the `snapshots/` folders, maintains `history.csv`, derives `model_tag`, and renders the sparklines and the two-series chart |
| `dashboard/assets.py` | Presentation only, and nothing here reads data or computes a number: CSS, JS, the collapsible-panel and table helpers, and the inline SVG charts. The CSS is a hand-pruned subset of `labelfirst`'s report styling so both reports look like one family |
| `dashboard/explain.py` | The three panels that are mostly explanation: where the five-candidate limit came from, why the two headline scores differ (with the weighting chart), and how the measurement was made. Its figures are recomputed from the same records as the rest of the page, never hardcoded |
| `dashboard/build_export_only.py` | A one-off, ad hoc page: scores Pl@ntNet only on the crowns one Labelbox export itself labels, ignoring the cumulative GT, the corpus, and the send-first queues entirely. Not part of the daily refresh loop; run it by hand against any export file. See its own docstring for the scope it deliberately excludes |

One reader, two consumers. That is the point: a number cannot differ between the CSV and the page
because neither one computes it independently.

Both scripts accept `--gt`, `--splits`, `--cache-dir`, `--wcvp-cache`. The renderer also takes
`--verify-against <snapshot dir>` (its siblings are the trend history), `--model-tag`, `--generated`
and `--out`. See `--help`.

## Gotchas

- **`labelfirst`'s CSS is copied, not imported, and not copied whole.** `import labelfirst` drags in
  numpy, scipy, scikit-learn and pandas, and these scripts must run on the stdlib alone. Every rule
  kept is byte-identical to upstream, but rules for elements this page does not have are dropped. So
  a future upstream restyle cannot be picked up by plain copy-paste; the prune has to be reapplied.
- **"Right name in the list" means the whole returned list, not the best 5 of a longer one.** We
  asked for `nb-results=5`, sent explicitly on every request from `config.yaml`
  `plantnet.identify_nb_results`. That 5 is inherited: it enters the reference Amazon pipeline
  (`elaliberte/labelbox_plantnet`, `d10364f`, 2026-02-16) and arrives here on 2026-03-26 with the
  first identify script, with no recorded rationale in either repo. It is not an API default either:
  Pl@ntNet documents the parameter as a way to "restrict size of output list of probable species",
  states only that it takes "an integer >= 1", and notes that "fewer results improve response
  time". So no maximum and no default are published, and the real ceiling on a bigger request is how
  many candidates the model has for that photo. A
  correct answer sitting at rank 6 was never returned and is invisible here. On 1,318 of the 3,248
  crowns with a cached answer (40.6%) fewer than 5 candidates came back at all, so for those the cap
  was not even binding; on the other 1,930 it was. This is the same cap that makes "the model never
  names it" unfalsifiable offline, and the page now says so in its own panel.
- **The evaluation set is the historical labelling record, not a random sample.** These rates carry
  over to unlabelled crowns only under an assumption that cannot be tested offline. If you want a
  number that generalises, a random holdout has to be set aside before the next batch goes out, and it
  cannot be reconstructed afterwards.
- **Genus-only crowns are excluded** from every species number. They are reported separately, scored
  at genus level, and never folded in.
- **The predictions come from `identify/k-central-america`**, the Central America regional model, not
  the global one. A regional restriction is therefore already in force, so any proposal to "restrict
  the model to local species" has to start from that fact rather than treat it as a new idea.
- **Re-measuring a snapshot in place needs its `history.csv` rows deleted.** The store is append-only
  by design. The build aborts with a message telling you exactly that.
