#!/usr/bin/env python3
"""Per-species Pl@ntNet-on-BCI health dashboard: one self-contained HTML page.

Answers "how is the model doing, per species, and what do I do about it?" from
data already on disk: the botanist's labels plus cached Pl@ntNet responses. No
network, no API key, no third-party package. The page opens from a file:// URL
with every style, script and chart inlined.

    python3 scripts/16_dashboard/16b_dashboard.py [--out PATH]

Numbers are recomputed here from source rather than read from the CSVs, then
cross-checked against the committed CSVs from 16_model_health.py; a mismatch
aborts the build, so the page cannot disagree with the measurement. Trend comes
from the sibling snapshot folders model-health-<date>/, summarised once into an
append-only history.csv beside the current snapshot's CSVs.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import health_core as hc  # noqa: E402
from dashboard_assets import CSS, JS, esc, panel, pctf, svg_hbar, table  # noqa: E402
from dashboard_history import load_trend, verify_snapshot  # noqa: E402

# A species is "rarely labelled" below this many crowns. Same threshold as the
# deprioritization support gate, so the two panels cannot disagree.
RARE_MAX_SUPPORT = 10
WAIT_SUPPORT_MIN = 10
RECOMMENDED_CONF = 0.8

# key -> (label, what to do about it). Order is the order of the to-do list:
# cheapest useful work first, safe-to-skip last.
STATUS = {
    "ranking": ("Right name in the list, not first",
                "Cheapest work here. Confirm the name from the short list instead of "
                "identifying from scratch"),
    "unmeasured": ("Too few labels to judge",
                   "Label a few more before trusting any number for it"),
    "hard": ("Wrong even with enough labels",
             "More labels will not fix this one. Treat it as a model limit"),
    "adequate": ("Mixed", "Keep it in the normal review queue"),
    "reliable": ("Usually right", "Lowest priority. Spot-check a few and move on"),
    "unreachable": ("Model never names it",
                    "Nothing to do. The model cannot return this species"),
}

HEADLINES = [
    ("macro_top1", "Average across species",
     "per-species top-1: each species counts once, whatever its size"),
    ("micro_top1", "Average across crowns",
     "crown-weighted top-1: one vote per labelled crown"),
    ("macro_top5", "Right name in the list, per species",
     "the best a smarter ranking could reach"),
    ("micro_top5", "Right name in the list, per crown",
     "the list holds at most 5 candidates"),
]


def diagnose(row: dict) -> str:
    """Per-species status. First matching rule wins; the order is the point.

    ``unreachable`` outranks everything because no amount of labelling moves it.
    ``reliable`` outranks ``ranking`` because a species already at >=90% does not
    need a re-rank. ``unmeasured`` sits below ``ranking`` so a thinly labelled
    species whose answer is in the list is still the cheap win it is.
    """
    n, a1, a5 = row["n_labelled_crowns"], row["top1_accuracy"], row["top5_accuracy"]
    if not row["in_corpus_vocabulary"]:
        return "unreachable"
    if n >= WAIT_SUPPORT_MIN and a1 >= 0.90:
        return "reliable"
    if a5 - a1 >= 0.20 and a5 >= 0.60:
        return "ranking"
    if n < WAIT_SUPPORT_MIN:
        return "unmeasured"
    return "hard" if a1 < 0.70 else "adequate"


def build(h, *, generated, verify_dir, fallback_tag, cache_dir):
    sp_recs, per_species = h.sp_recs, h.per_species
    n, n_sp = len(sp_recs), len(per_species)

    def top1(r):
        return r["ranked"][0][0]

    def conf(r):
        return r["ranked"][0][1]

    def cap(s):
        return s[:1].upper() + s[1:]

    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:5]])
    now = dict(macro_top1=sum(d["top1_accuracy"] for d in per_species) / n_sp,
               macro_top5=sum(d["top5_accuracy"] for d in per_species) / n_sp,
               micro_top1=c1 / n, micro_top5=c5 / n)

    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    status = {d["species"]: diagnose(d) for d in per_species}
    counts = defaultdict(int)
    for s in status.values():
        counts[s] += 1

    # --- crowns grouped by how many labels their species has ---
    buckets = {}
    for d in per_species:
        buckets.setdefault(d["support_bucket"],
                           dict(n_species=0, n_crowns=0, c1=0))["n_species"] += 1
    for r in sp_recs:
        b = buckets[hc.bucket_label(support[r["gt"]])]
        b["n_crowns"] += 1
        b["c1"] += top1(r) == r["gt"]

    # --- confidence bands over the whole species-level set ---
    bins_all = [(f"[{lo:.1f},{min(hi, 1.0):.1f})", len(sub),
                 sum(1 for r in sub if top1(r) == r["gt"]))
                for lo, hi in hc.CONF_BINS
                for sub in ([r for r in sp_recs if lo <= conf(r) < hi],)]

    # --- what this evaluation cannot score, and what name matching is worth ---
    # "Never named" = the species name appears nowhere in any cached candidate list, so no
    # threshold can ever score those crowns. Counted twice on purpose: over the evaluated set
    # (the denominator every other number here uses) and over every label, which is the
    # denominator the run log uses. The verifier holds both to the run log.
    never = sorted((d for d in per_species if not d["in_corpus_vocabulary"]),
                   key=lambda d: -d["n_labelled_crowns"])
    never_sp = {d["species"] for d in never}
    never_crowns = sum(d["n_labelled_crowns"] for d in never)
    never_all = h.tier_crowns["e_absent_from_corpus"] + h.tier_crowns["c_genus_only_in_corpus"]
    reach = [r for r in sp_recs if r["gt"] not in never_sp]
    reach1 = sum(1 for r in reach if top1(r) == r["gt"]) / len(reach)
    # Labels and predictions are canonicalised the same way before matching. Scoring the raw
    # names instead says what that is worth, and it is a gain, never a source of error.
    strict1 = sum(1 for r in sp_recs
                  if r["ranked_strict"] and r["ranked_strict"][0][0] == r["gt_strict"])
    short5 = sum(1 for r in sp_recs + h.genus_recs if len(r["ranked"]) < 5)
    n_pred = len(sp_recs) + len(h.genus_recs)

    trend = load_trend(verify_dir, fallback_tag, sp_recs=sp_recs, cache_dir=cache_dir)
    checks = verify_snapshot(
        verify_dir, per_species=per_species, buckets=buckets, bins_all=bins_all,
        trend=trend, n_crowns=n, macro1=now["macro_top1"], micro1=now["micro_top1"],
        never_all=never_all, unscoreable=n - len(reach), strict_hits=strict1)

    # --- why confidence alone is unsafe: error by labelled crowns, at conf>=0.7 ---
    flat = {}
    for r in sp_recs:
        if conf(r) >= 0.7:
            b = flat.setdefault(hc.bucket_label(support[r["gt"]]), [0, 0])
            b[0] += 1
            b[1] += top1(r) != r["gt"]

    # --- queue-ordering rules. Which species clear the gate is decided from train crowns
    # only, then scored on test only, so no rule is graded on the crowns that defined it.
    train_support = defaultdict(int)
    for r in sp_recs:
        if r["split"] == "train":
            train_support[r["gt"]] += 1
    eligible = {s for s, k in train_support.items() if k >= WAIT_SUPPORT_MIN}
    test_recs = [r for r in sp_recs if r["split"] == "test"]
    rare = {s for s, k in support.items() if k < RARE_MAX_SUPPORT}
    n_rare_test = sum(1 for r in test_recs if r["gt"] in rare)

    rules = [(f"confidence &ge; {t}, any species", t, False) for t in (0.7, 0.8)]
    rules += [(f"confidence &ge; {t} and at least {WAIT_SUPPORT_MIN} labelled crowns for "
               f"that species", t, True) for t in (0.7, 0.8, 0.9)]
    ops = []
    for label, thr, gate in rules:
        wait = [r for r in test_recs if conf(r) >= thr and (not gate or r["gt"] in eligible)]
        ids = {id(r) for r in wait}
        rest = [r for r in test_recs if id(r) not in ids]
        ops.append(dict(label=label, thr=thr, gate=gate, n=len(wait),
                        share=len(wait) / len(test_recs) if test_recs else None,
                        err=sum(1 for r in wait if top1(r) != r["gt"]) / len(wait)
                        if wait else None,
                        rare=sum(1 for r in wait if r["gt"] in rare),
                        rare_rest=sum(1 for r in rest if r["gt"] in rare) / len(rest)
                        if rest else None))
    best = next(o for o in ops if o["gate"] and abs(o["thr"] - RECOMMENDED_CONF) < 1e-9)

    gn = len(h.genus_recs)
    gg1 = sum(1 for r in h.genus_recs if hc.genus_of(r["ranked"][0][0]) == r["gt"])

    # --- page ---
    top26 = sorted(per_species, key=lambda d: -d["n_labelled_crowns"])[:26]
    P = ['<h1>Pl@ntNet on BCI: per-species model health</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(trend.latest)} &middot; Pl@ntNet model <code>{esc(trend.tag)}</code> '
         f'&middot; {n:,} labelled crowns &middot; {n_sp} species &middot; computed '
         f'offline, no API key</div>',
         '<p class="intro">This page says where botanist time is worth spending. Pl@ntNet has '
         'already guessed a species for every labelled crown photo and we know the right '
         'answer for those, so we can say per species how often it is right.</p>',
         '<div class="hero">']
    for i, (metric, label, note) in enumerate(HEADLINES):
        P.append(f'<div class="metric{" first" if i == 0 else ""}"><div class="row">'
                 f'<div class="v">{pctf(now[metric])}</div>{trend.spark(metric)}</div>'
                 f'<div class="l">{label}</div><div class="n">{note}</div></div>')
    big = top26[0]
    singles = sum(1 for d in per_species if d["n_labelled_crowns"] == 1)
    P.append(f'</div><p class="note"><strong>The first two numbers are one model scored two '
             f'ways, and both are correct.</strong> The crown-weighted one counts every '
             f'labelled crown once, so species with many crowns pull it hard. The per-species '
             f'one scores each species on its own crowns first, then averages those {n_sp} '
             f'rates, so a species with a single crown counts as much as the biggest one. '
             f'Take the two ends of this dataset: <em>{esc(big["species"])}</em> has '
             f'{big["n_labelled_crowns"]:,} labelled crowns at {pctf(big["top1_accuracy"])}, '
             f'and {singles} species have one crown each. Crown-weighted, that one species '
             f'casts {big["n_labelled_crowns"]:,} votes and each of those {singles} casts one. '
             f'Per species, every one of them casts one. That is the whole gap: the '
             f'{len(top26)} most-labelled species carry '
             f'{sum(d["n_labelled_crowns"] for d in top26):,} of the {n:,} crowns, so the '
             f'crown-weighted number mostly reports how the model does on those. <strong>The '
             f'per-species number is the one a labelling programme exists to move.</strong>'
             f'</p><p class="note"><strong>Of the crowns this evaluation can possibly score, '
             f'{pctf(reach1)} are right: {sum(1 for r in reach if top1(r) == r["gt"]):,} of '
             f'{len(reach):,}.</strong> The other {n - len(reach):,} crowns belong to '
             f'{len(never)} species the model never names, so they are wrong at every '
             f'threshold and no amount of work on our side can score them. That is partly our '
             f'own doing rather than the model\'s limit: we asked for only five candidates per '
             f'photo, so a species Pl@ntNet knows but never ranked in the top five looks '
             f'identical here to one it has never heard of.</p>')

    # ---- to-do list ----
    body = ['<ul class="todo">']
    body += [f'<li><span class="n">{counts[k]}</span> species '
             f'<span class="tag {k}">{esc(lab)}</span> {esc(act)}</li>'
             for k, (lab, act) in STATUS.items()]
    body.append(f'</ul><p class="note">Each of the {n_sp} species sits in exactly one row. '
                f'The numbers behind each status are in the species table below.</p>')
    P.append(panel(f"Where to spend botanist time next: {counts['ranking']} species are a "
                   f"cheap confirmation, {counts['unreachable']} are not worth any time",
                   "<b>Work top to bottom.</b> Rows are ordered cheapest useful work first, "
                   "and the last two rows are work you can skip.",
                   "\n".join(body), open_=True))

    P.append(trend.render())

    # ---- deprioritization ----
    body = (f'<div class="rec"><strong>Suggested rule: leave a crown for later when '
            f'Pl@ntNet is at least {RECOMMENDED_CONF} confident and its species already has '
            f'{WAIT_SUPPORT_MIN} or more labelled crowns.</strong> On held-out test crowns '
            f'that is {best["n"]:,} of {len(test_recs):,} ({pctf(best["share"])}), and the '
            f'first guess is wrong on {pctf(best["err"])} of them.</div>'
            '<p class="note"><strong>Nothing here is a label.</strong> A crown that can wait '
            'keeps whatever ground truth it already has, or none at all. No prediction is '
            'ever written into ground truth by this rule. It only pushes crowns down the '
            "botanist's queue, the same job it does in labelfirst and speciesfirst.</p>"
            f'<p class="note"><strong>The decision expires with the model.</strong> Pl@ntNet '
            f'ships a new model every few months, on its own schedule rather than ours, and '
            f'a crown deprioritized under <code>{esc(trend.tag)}</code> is not deprioritized '
            f'under the next one. Re-run this page after every model change and the queue '
            f're-sorts. Any crown can come back to the top.</p>'
            f'<p class="note">{len(eligible)} species clear the {WAIT_SUPPORT_MIN}-crown gate, '
            f'counted from <code>train</code> crowns only, and the error rate above is then '
            f'measured on the {len(test_recs):,} <code>test</code> crowns only.</p>')
    P.append(panel(f"Which crowns can wait: {best['n']:,} of {len(test_recs):,} test crowns, "
                   f"revocable at the next model change",
                   "<b>Use this to order the queue, not to close crowns.</b> These are the "
                   "crowns to look at last, and the ranking is recomputed from scratch "
                   "whenever Pl@ntNet updates.", body, open_=True))

    # ---- rule comparison ----
    body = table([("rule", False), ("crowns that can wait", True),
                  ("share of the queue", True), ("of those, first guess wrong", True),
                  ("rarely-labelled crowns among them", True),
                  ("rarely-labelled share of what is left", True)],
                 [[f'<strong>{o["label"]}</strong>' if o is best else o["label"],
                   f'{o["n"]:,}', pctf(o["share"]), pctf(o["err"]), f'{o["rare"]}',
                   pctf(o["rare_rest"])] for o in ops])
    body += (f'<p class="note">A species with fewer than {RARE_MAX_SUPPORT} labelled crowns '
             f'counts as rarely labelled: {len(rare)} of {n_sp} species, {n_rare_test} of '
             f'the {len(test_recs):,} test crowns. No rarely-labelled crown can be '
             f'deprioritized under a gated rule, because the gate excludes them, so the last '
             f'column is the gate doing its job rather than separate evidence for it.</p>')
    P.append(panel("How the five candidate rules compare, including the ungated ones",
                   "<b>Read this only if you want to move the threshold.</b> Each row trades "
                   "queue reduction against how often a deprioritized crown was actually "
                   "misidentified.", body))

    # ---- confidence ----
    body = (svg_hbar([(band, k / nn if nn else 0.0,
                       f'{pctf(k / nn) if nn else "n/a"}  ·  {nn:,} crowns', "#2e7d32")
                      for band, nn, k in bins_all],
                     title="how often the first guess is right, by the model's own confidence")
            + '<p class="note">Over all crowns at once the confidence score is trustworthy: '
              'when the model is sure it is almost always right. That is what makes queue '
              'ordering possible at all.</p>'
              '<p class="note"><strong>It is not trustworthy on rarely-labelled '
              'species.</strong> Ordering the queue on confidence alone would push exactly '
              'the species you care about to the bottom:</p>'
            + table([("labelled crowns for that species", False),
                     ("crowns at confidence &ge; 0.7", True),
                     ("of those, first guess wrong", True)],
                    [[f"{lab} crowns", f"{flat[lab][0]:,}",
                      pctf(flat[lab][1] / flat[lab][0])]
                     for lab in hc.BUCKET_ORDER if lab in flat])
            + '<p class="note">Raising the confidence threshold does not repair this. '
              'Requiring the species to have been measured first does, which is why the '
              'suggested rule has two conditions.</p>')
    P.append(panel("Can we trust the model's confidence? In bulk yes, on rare species no",
                   "<b>This is the evidence behind the two-part rule above.</b> Read it if "
                   "someone proposes ordering the queue on confidence alone.", body))

    # ---- labelled crowns vs accuracy ----
    body = (svg_hbar([(f"{lab} crowns", buckets[lab]["c1"] / buckets[lab]["n_crowns"],
                       f'{pctf(buckets[lab]["c1"] / buckets[lab]["n_crowns"])}  ·  '
                       f'{buckets[lab]["n_species"]} spp, {buckets[lab]["n_crowns"]:,} '
                       f'crowns', "#1565c0")
                      for lab in hc.BUCKET_ORDER
                      if buckets.get(lab) and buckets[lab]["n_crowns"]],
                     title="how often the first guess is right, by how many crowns that "
                           "species has")
            + '<div class="warn"><strong>Read this as how common the species is, not as '
              'training data.</strong> These predictions come from a frozen Pl@ntNet '
              'regional model that has never seen a single BCI label, so labelling a species '
              'does not make Pl@ntNet better at it. What this axis really tracks is how '
              'common a species is on the plot, and common species also have more reference '
              'photos inside Pl@ntNet. What extra labels buy is knowledge: below about '
              f'{WAIT_SUPPORT_MIN} crowns a per-species accuracy jumps around too much to '
              f'act on, and above it the species can enter the queue-ordering rule.</div>')
    P.append(panel("Does accuracy rise with more labels? It rises with abundance, and the "
                   "model is frozen",
                   "<b>Use this to see where the measurement is solid enough to act on.</b> "
                   "Do not use it to argue that labelling raises accuracy.", body))

    # ---- per-species table ----
    sp_rows, attrs = [], []
    for d in sorted(per_species, key=lambda x: (-x["n_labelled_crowns"], x["species"])):
        sp, st = d["species"], status[d["species"]]
        sp_rows.append([
            f'<span class="sp" data-sort="{esc(sp)}">{esc(cap(sp))}</span>',
            f'<span data-sort="{d["n_labelled_crowns"]}">{d["n_labelled_crowns"]:,}</span>',
            f'<span data-sort="{d["top1_accuracy"]:.6f}">{pctf(d["top1_accuracy"])}</span>',
            f'<span data-sort="{d["top5_accuracy"]:.6f}">{pctf(d["top5_accuracy"])}</span>',
            f'<span data-sort="{d["mean_top1_confidence"]:.6f}">'
            f'{d["mean_top1_confidence"]:.2f}</span>',
            trend.spark(f"species:{sp}:top1", empty=""),
            f'<span class="tag {st}" data-sort="{esc(STATUS[st][0])}">'
            f'{esc(STATUS[st][0])}</span>'])
        attrs.append(f' data-species="{esc(sp)}" data-status="{st}"')
    body = ('<div class="controls">'
            '<input id="species-filter" type="search" placeholder="filter species&hellip;" '
            'size="28" aria-label="filter species">'
            '<select id="status-filter" aria-label="filter by status">'
            '<option value="all">every status</option>'
            + "".join(f'<option value="{k}">{esc(v[0])}</option>'
                      for k, v in STATUS.items())
            + '</select><span class="count" id="species-count"></span></div>'
            + table([("Species", False), ("Labelled crowns", True),
                     ("First guess right", True), ("Right name in the list", True),
                     ("Model's confidence", True), ("Trend", False), ("Status", False)],
                    sp_rows, tid="species-table", sortable_from=0, row_attrs=attrs))
    P.append(panel(f"Look up one species: all {n_sp}, sortable and filterable",
                   "<b>Find a species you care about and read its status.</b> Click any "
                   "heading to sort, type to filter. The trend column needs two or more "
                   "snapshots before it draws anything.", body))

    # ---- ceiling ----
    body = (f'<p class="note"><strong>{len(never)} species ({never_crowns} of the {n:,} '
            f'evaluated crowns) never appear in any answer the model gave us.</strong> '
            f'Leaving them out raises the per-crown rate from {pctf(c1 / n)} to '
            f'{pctf(reach1)} on {len(reach):,} crowns. Across all {len(h.gt_rows):,} labelled '
            f'crowns the same condition covers {never_all} crowns; this panel uses the '
            f'evaluated set, like every other number here.</p>'
            f'<div class="warn"><strong>This is a limit of the question we asked, not proof '
            f'the model has never heard of these species.</strong> The only test we can run '
            f'offline is whether a species name turns up somewhere in the cached answers, and '
            f'we asked Pl@ntNet for its best five candidates per photo. A species Pl@ntNet '
            f'knows perfectly well, but which never made anyone\'s top five on a BCI photo, '
            f'is indistinguishable here from one it truly cannot return. The five-candidate '
            f'cap is what hides the difference. It did not bite everywhere: on '
            f'{short5:,} of the {n_pred:,} crowns with a cached answer '
            f'({pctf(short5 / n_pred)}) fewer than five candidates came back, so nothing was '
            f'cut off. On the other {n_pred - short5:,} the list was full, and anything the '
            f'model would have ranked sixth or lower is invisible to us. The way to find out '
            f'is to re-run the predictions asking for more candidates per photo. More name '
            f'cleaning will not help, because names are already matched as well as they '
            f'can be.</div>'
            + table([("Species", False), ("Labelled crowns", True)],
                    [[f'<span class="sp">{esc(cap(d["species"]))}</span>',
                      f'{d["n_labelled_crowns"]:,}'] for d in never])
            + f'<p class="note"><strong>Spelling and renamed species are not costing us '
              f'anything.</strong> Labels and predictions are put into the same standard form '
              f'before they are compared, and old names are resolved to current ones. Scoring '
              f'the raw names instead would give {pctf(strict1 / n)} rather than '
              f'{pctf(c1 / n)}, so that matching is worth '
              f'{100 * (c1 - strict1) / n:+.2f} points, or {c1 - strict1} crowns. Treat it as '
              f'a gain already banked, not as a source of error.</p>'
              f'<p class="note"><strong>{gn:,} further crowns carry only a genus '
              f'name</strong> and are left out of every species number above. Scored at '
              f'genus level they reach {pctf(gg1 / gn) if gn else "n/a"}. Whether taking '
              f'them down to species is worth expert time is a prioritisation question, not '
              f'a model question.</p>')
    P.append(panel(f"What labelling cannot fix: {len(never)} species, {never_crowns} crowns "
                   f"the model never named, and why the five-candidate cap may be the cause",
                   "<b>Do not spend expert time renaming or relabelling these.</b> Either the "
                   "model cannot return the species or we never asked for enough candidates "
                   "to find out, and only re-running the predictions can tell the two apart.",
                   body))

    # ---- method ----
    body = ('<ul class="prov">'
            f'<li>Predictions: <code>identify/k-central-america</code>, model run '
            f'<code>{esc(trend.tag)}</code>. The Central America regional model, not the '
            f'worldwide one, so a regional restriction is already in place.</li>'
            f'<li>Request settings: <code>nb-results=5</code> (our choice, not a model '
            f'limit), no reject option, organs detected automatically, on a 1280&nbsp;px '
            f'centre crop of each crown photo. A correct answer at position 6 or beyond was '
            f'never returned and cannot be seen here.</li>'
            f'<li>Evaluated set: {n:,} crowns across {n_sp} species carrying a botanist '
            f'label that names a species rather than only a genus. They are the historical '
            f'labelling record, not a random draw, so these rates carry over to unlabelled '
            f'crowns only under an assumption that cannot be tested offline.</li>'
            f'<li>Trend: one row per snapshot folder and metric in <code>history.csv</code>, '
            f'appended and never rewritten. Each snapshot\'s model tag is read from its own '
            f'<code>run_log.txt</code>, which records the endpoint and the model run '
            f'name.</li>'
            '<li>Every number here is recomputed from the source data at build time and '
            'cross-checked against the committed measurement files:<ul>'
            + "".join(f"<li>{esc(c)}</li>" for c in checks)
            + '</ul>A mismatch aborts the build.</li>'
            '<li>Rebuild: <code>python3 scripts/16_dashboard/16_model_health.py</code> then '
            '<code>python3 scripts/16_dashboard/16b_dashboard.py</code>. Standard library '
            'only, same output every run, no network.</li></ul>')
    P.append(panel("How this was measured, and what it does not tell you",
                   "<b>Read this before quoting any number outside the team.</b> It names "
                   "the model, the request settings, and the one assumption that cannot be "
                   "checked offline.", body))

    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Pl@ntNet on BCI - per-species model health</title>"
            f"<style>{CSS}</style></head><body>" + "\n".join(P)
            + '<div class="footer">generated offline from cached predictions '
              "&middot; no network, no API key</div>"
            f"<script>{JS}</script></body></html>"), checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", default=hc.GT_CSV)
    ap.add_argument("--splits", default=hc.SPLITS_CSV)
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument("--verify-against",
                    default=os.path.join(os.path.dirname(hc.REPO),
                                         "bci_workshop_labelbox_plantnet-docs",
                                         "model-health-2026-08-03"),
                    help="directory holding the committed measurement CSVs to cross-check; "
                         "its siblings model-health-<date>/ are the trend history")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "output", "16_dashboard",
                                                  "model_health_dashboard.html"))
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    args = ap.parse_args()

    h = hc.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=args.verify_against, fallback_tag=args.model_tag,
                         cache_dir=args.cache_dir)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {args.out}  ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
