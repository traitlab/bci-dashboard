#!/usr/bin/env python3
"""Per-species Pl@ntNet-on-BCI health dashboard: one self-contained HTML page.

Answers "how is the model doing, per species, and what do I do about it?" from
data already on disk: the botanist's labels plus cached Pl@ntNet responses. No
network, no API key, no third-party package. The page opens from a file:// URL
with every style, script and chart inlined.

    python3 dashboard/build_full.py [--out PATH]

Numbers are recomputed here from source rather than read from the CSVs, then
cross-checked against the CSVs measure.py wrote into the snapshot; a mismatch
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

import core as hc  # noqa: E402
from assets import (CSS, JS, cap, esc, filterable_table, panel, pctf, section,  # noqa: E402
                              status_with_reason, svg_hbar, table)
from explain import (BAND_SHORT, candidates_panel, method_panel,  # noqa: E402
                              weighting_panel)
from history import (  # noqa: E402
    latest_snapshot_dir, load_trend, verify_snapshot)

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
    "unreachable": ("Never named in five candidates",
                    "Nothing to do until we know whether Pl@ntNet carries this "
                    "species at all"),
}

STATUS_REASON = {
    "ranking": "The right name is already in the five, so this is the cheapest confirmation work.",
    "unmeasured": "Fewer than 10 labelled crowns, so the score is too thin to trust yet.",
    "hard": "Enough crowns, but the first guess is still weak, so more labels will not fix it.",
    "adequate": "Mixed results, so keep it in the normal review queue.",
    "reliable": "Usually right, so this species is low priority for extra work.",
    "unreachable": "It never appears in the five candidates we asked for, so labelling will not "
                   "recover it. Whether Pl@ntNet carries the species at all is not known from here.",
}

# A 2x2 grid, not four unrelated numbers: the question asked (rows) crossed with
# how the answer was averaged (columns). Laid out this way because the pair
# 50.3% / 79.5% is unreadable as two adjacent cards -- the reader cannot tell
# whether one supersedes the other. (metric, question, averaged over, note).
HEADLINES = [
    ("macro_top1", "First guess is right", "per species",
     "each of the {n_sp} species counts once, however few crowns it has"),
    ("micro_top1", "First guess is right", "per crown",
     "one vote per labelled crown, so common species dominate"),
    ("macro_top5", "Right name is among the 5 offered", "per species",
     "the ceiling a better ranking could reach without a better model"),
    ("micro_top5", "Right name is among the 5 offered", "per crown",
     "we only ever asked Pl@ntNet for 5 names"),
]

# Sits directly under the grid. Without it the two columns read as a
# contradiction rather than as two questions.
HERO_READING = (
    "Read down a column, not across. <b>Per species</b> is the number to quote for "
    "a species picked off the checklist; <b>per crown</b> is the number to quote for "
    "a photo picked off the drive. Per crown is the higher of the two because the "
    "species with many crowns are the ones Pl@ntNet already knows."
)

# What a reader has to know before any of the four numbers means anything.
HERO_TERMS = (
    "A <b>crown</b> is one tree canopy a botanist outlined in a drone frame. "
    "Pl@ntNet returns a ranked list of at most 5 species names for that crown's "
    "photo; the <b>first guess</b> is the top-ranked name. Right means it matches "
    "the botanist's name for the same crown."
)


def is_family(n: str) -> bool:
    """A one-word label ending in -aceae is a family, not a genus.

    Every botanical family name carries that suffix and no accepted genus does,
    so the test is exact rather than a heuristic. It matters because a family
    label can never equal a predicted genus, so counting those crowns into a
    genus-level rate would report guaranteed misses as measured ones.
    """
    return n.strip().lower().endswith("aceae")


# diagnose lives in core so every dashboard renders the same status for
# the same species. WAIT_SUPPORT_MIN above is deliberately equal to
# hc.WELL_SAMPLED_MIN_N, the threshold diagnose uses.
diagnose = hc.diagnose


def build(h, *, generated, verify_dir, fallback_tag, cache_dir):
    sp_recs, per_species = h.sp_recs, h.per_species
    n, n_sp = len(sp_recs), len(per_species)

    def top1(r):
        return r["ranked"][0][0]

    def conf(r):
        return r["ranked"][0][1]

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

    # --- send-first queue over the unlabelled pool, and labels worth a second look.
    # Both come from the 2026-08-05 call: prioritise the long tail and
    # low-confidence guesses on usually-right species, and send confident disagreements
    # back for review once the cheap work is done. The queue logic itself lives in
    # core so this page and measure.py cannot drift apart.
    acc_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    joined_stems = {stem for _, stem, _ in h.joined}
    queue_counts = {}
    lt_species = defaultdict(int)
    n_no_answer = 0
    for stem in sorted(h.predictions):
        if stem in joined_stems:
            continue
        ranked = [(h.canon(b), s) for b, s in h.predictions[stem]]
        if not ranked:
            n_no_answer += 1
            continue
        pred, cf = ranked[0]
        q = hc.queue_of_prediction(pred, cf, support, acc_of)
        queue_counts[q] = queue_counts.get(q, 0) + 1
        if q == "long_tail":
            lt_species[pred] += 1
    n_unlab = sum(queue_counts.values())

    review = [r for r in sp_recs
              if top1(r) != r["gt"] and conf(r) >= hc.REVIEW_CONF]
    review_pairs = defaultdict(list)
    for r in review:
        review_pairs[(r["gt"], top1(r))].append(conf(r))
    review_counts = (len(review), len(review_pairs))

    checks = verify_snapshot(
        verify_dir, per_species=per_species, buckets=buckets, bins_all=bins_all,
        trend=trend, n_crowns=n, macro1=now["macro_top1"], micro1=now["micro_top1"],
        never_all=never_all, unscoreable=n - len(reach), strict_hits=strict1,
        queue_counts=queue_counts, n_no_answer=n_no_answer, review_counts=review_counts)

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

    # Labels above species split two ways, and mixing them understates the genus
    # rate: a family name can never equal a predicted genus, so every family-only
    # crown is a guaranteed miss at genus level rather than a measured one.
    fam_recs = [r for r in h.genus_recs if is_family(r["gt"])]
    gen_recs = [r for r in h.genus_recs if not is_family(r["gt"])]
    gn, fam_n = len(gen_recs), len(fam_recs)
    gg1 = sum(1 for r in gen_recs if hc.genus_of(r["ranked"][0][0]) == r["gt"])
    fam_names = len({r["gt"] for r in fam_recs})
    # Genus-only crowns whose right answer is narrowed to one in-genus candidate:
    # the cheapest confirmation on the page, a yes/no rather than an identification.
    in_gen = [sum(1 for b, _ in r["ranked"][:5] if hc.genus_of(b) == r["gt"]) for r in gen_recs]
    gen_any = sum(1 for k in in_gen if k)
    gen_one = sum(1 for k in in_gen if k == 1)
    gen_none = len(in_gen) - gen_any

    # --- page ---
    P = ['<h1>Pl@ntNet on BCI: per-species model health</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(trend.latest)} &middot; Pl@ntNet model <code>{esc(trend.tag)}</code> '
         f'&middot; {n:,} labelled crowns &middot; {n_sp} species</div>',
         '<p class="intro">This page says where botanist time is worth spending. Pl@ntNet has '
         'already guessed a species for every labelled crown photo and we know the right '
         'answer for those, so we can say per species how often it is right.</p>',
         f'<p class="terms">{HERO_TERMS}</p>',
         '<div class="hero">']
    for i, (metric, question, averaged, note) in enumerate(HEADLINES):
        P.append(f'<div class="metric{" first" if i == 0 else ""}">'
                 f'<div class="e">{averaged}</div><div class="row">'
                 f'<div class="v">{pctf(now[metric])}</div>{trend.spark(metric)}</div>'
                 f'<div class="l">{question}</div>'
                 f'<div class="n">{note.format(n_sp=n_sp)}</div></div>')
    P.append(f'</div><p class="note">{HERO_READING}</p>')
    P.append(f'<p class="note"><strong>Of the crowns this evaluation can possibly score, '
             f'{pctf(reach1)} are right: {sum(1 for r in reach if top1(r) == r["gt"]):,} of '
             f'{len(reach):,}.</strong> The other {n - len(reach):,} belong to {len(never)} '
             f'species that never reach the five candidates, so they are wrong at every '
             f'threshold. That is not the same as being outside Pl@ntNet&rsquo;s checklist: we '
             f'hold five names per photo, not the checklist. '
             f'&ldquo;What this cannot tell you&rdquo; says where that five came from.</p>')

    # Panels are built in reading order but emitted in section order at the foot of
    # this function, so a comment here names the panel, never its position.
    # ---- the five-candidate ceiling ----
    p_candidates = candidates_panel(recs=sp_recs + h.genus_recs, gen_n=gn, gen_none=gen_none)

    # ---- why the two headline numbers differ ----
    p_weighting = weighting_panel(per_species=per_species, sp_recs=sp_recs, support=support,
                                  buckets=buckets, now=now, n=n, n_sp=n_sp)

    # ---- to-do list ----
    body = ['<ul class="todo">']
    body += [f'<li><span class="n">{counts[k]}</span> species '
             f'<span class="tag {k}">{esc(lab)}</span> {esc(act)}</li>'
             for k, (lab, act) in STATUS.items()]
    body.append(f'</ul><p class="note">Each of the {n_sp} species sits in exactly one row. '
                f'The numbers behind each status are in the species table below.</p>'
                f'<p class="note"><strong>Cheaper still, and not counted in any row above: '
                f'{gen_one:,} crowns whose botanist label stops at the genus and whose five '
                f'candidates contain exactly one species from that genus.</strong> The question '
                f'there is yes or no, not which of {n_sp}. Those crowns are outside the {n_sp} '
                f'species scored on this page because they never named a species; see the '
                f'genus paragraph under &ldquo;What this cannot tell you&rdquo;.</p>')
    p_todo = panel(f"Where to spend botanist time next: {counts['ranking']} species are a "
                   f"cheap confirmation, {counts['unreachable']} are not worth time yet",
                   "<b>Work top to bottom.</b> Rows are ordered cheapest useful work first, "
                   "and the last two rows are work you can skip.",
                   "\n".join(body), open_=True)

    # ---- what to send first: the unlabelled pool, ordered ----
    QL = {"long_tail": ("Species we barely have",
                        "The guess points at a species with fewer than 10 labelled crowns, "
                        "or one the model gets wrong even with more. These crowns fill the "
                        "long tail the labelling programme exists for"),
          "low_conf_known": ("A usually-right species, guessed weakly",
                             "The species is normally identified well but the model is "
                             "unsure here, so the photo is either an odd one worth having "
                             "or a quiet miss"),
          "normal": ("Everything else", "The ordinary queue"),
          "can_wait": ("Confident on a well-covered species",
                       "The two-part rule below says these can wait; look at them last")}
    body = table([("queue", False), ("unlabelled crowns", True),
                  ("share of the pool", True)],
                 [[f'<strong>{esc(QL[q][0])}</strong>' if q in ("long_tail", "low_conf_known")
                   else esc(QL[q][0]),
                   f'{queue_counts.get(q, 0):,}',
                   pctf(queue_counts.get(q, 0) / n_unlab if n_unlab else None)]
                  for q in hc.QUEUE_ORDER])
    top_lt = sorted(lt_species.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    body += (f'<p class="note">Most-named species in the first queue: '
             + ", ".join(f'<span class="sp">{esc(cap(s))}</span> ({k:,})' for s, k in top_lt)
             + '.</p>'
             f'<p class="note">Every crown, in order, is in <code>send_first_queue.csv</code> '
             f'in the snapshot folder: queue, photo key, the guess and its confidence, and '
             f'how well that species is already measured. Weakest confidence first inside '
             f'each queue, so the top of the file is the next batch.</p>'
             f'<p class="note"><strong>{n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Those are the '
             f'candidate junk or non-plant photos (leaves in the water, bare trunks). There '
             f'is no reliable automatic rule for junk, so check that handful by eye before '
             f'queueing them rather than filtering on it.</p>'
             f'<p class="note">The pool is {n_unlab:,} of {len(h.split_rows):,} photos: the '
             f'crowns with a cached Pl@ntNet answer and no botanist label. The species '
             f'record behind each queue is the one measured above, so a model update '
             f're-sorts this queue exactly as it re-sorts the can-wait one.</p>')
    p_send = panel(f"What to send to the botanist first: {queue_counts.get('long_tail', 0):,} "
                   f"of {n_unlab:,} unlabelled photos point at species we barely have",
                   "<b>Work the queues top to bottom.</b> The first two buy the most per "
                   "label: the long tail, where a species has almost nothing to be scored "
                   "on, and the photos where a usually-right species is guessed weakly.",
                   body)

    # ---- labels worth a second look ----
    pair_rows = sorted(review_pairs.items(), key=lambda kv: -len(kv[1]))[:10]
    body = (table([("botanist label", False), ("Pl@ntNet's first guess", False),
                   ("crowns", True), ("mean confidence", True)],
                  [[f'<span class="sp">{esc(cap(gt))}</span>',
                    f'<span class="sp">{esc(cap(pr))}</span>',
                    f"{len(cs):,}", f"{sum(cs) / len(cs):.2f}"]
                   for (gt, pr), cs in pair_rows])
            if pair_rows else '<p class="note">None at this threshold.</p>')
    body += (f'<p class="note">Each row is a labelled crown where the model is at least '
             f'{hc.REVIEW_CONF:.1f} confident in a <em>different</em> species. Confident '
             f'first guesses are right about 98% of the time in bulk, so each of these is '
             f'either a rare confident model error or a label error, and a label error '
             f'found this way is the cheapest label fix available. Offline there is no way '
             f'to tell which; that is the botanist\'s minute. '
             f'Every crown is in <code>label_review_queue.csv</code> in the snapshot folder, '
             f'most confident first.</p>'
             f'<p class="note">Not urgent: work this list after the send-first queues. A '
             f'confusion pair that keeps recurring is a signal about the species, not just '
             f'the photo.</p>')
    p_review = panel(f"Labels worth a second look: {review_counts[0]} crowns where Pl@ntNet "
                     f"confidently disagrees",
                     "<b>Possible label errors, possible model errors.</b> Either way they "
                     "are the disagreements most worth an expert's minute, once the cheap "
                     "queues above are worked through.", body)

    # history.py opens its own panel, and only the first panel of each
    # section here opens. Collapse the one leading tag rather than reach into that
    # module, and refuse to build if it stops being the tag we expect.
    p_trend = trend.render()
    if not p_trend.startswith('<details class="panel" open>'):
        raise SystemExit("16b: trend.render() no longer starts with an open panel tag; "
                         "re-check the collapse here against history.py")
    p_trend = p_trend.replace('<details class="panel" open>', '<details class="panel">', 1)

    # ---- deprioritization ----
    body = (f'<div class="rec"><strong>Suggested rule: leave a crown for later when '
            f'Pl@ntNet is at least {RECOMMENDED_CONF} confident and its species already has '
            f'{WAIT_SUPPORT_MIN} or more labelled crowns.</strong> On held-out test crowns '
            f'that is {best["n"]:,} of {len(test_recs):,} ({pctf(best["share"])}), and the '
            f'first guess is wrong on {pctf(best["err"])} of them.</div>'
            '<p class="note"><strong>Nothing here is a label.</strong> A crown that can wait '
            'keeps whatever ground truth it already has, or none at all. No prediction is '
            'ever written into ground truth by this rule. It only pushes crowns down the '
            "botanist's queue.</p>"
            f'<p class="note"><strong>The decision expires with the model.</strong> Pl@ntNet '
            f'ships a new model every few months, on its own schedule rather than ours, and '
            f'a crown deprioritized under <code>{esc(trend.tag)}</code> is not deprioritized '
            f'under the next one. Re-run this page after every model change and the queue '
            f're-sorts. Any crown can come back to the top.</p>'
            f'<p class="note">{len(eligible)} species clear the {WAIT_SUPPORT_MIN}-crown gate, '
            f'counted from <code>train</code> crowns only, and the error rate above is then '
            f'measured on the {len(test_recs):,} <code>test</code> crowns only.</p>')
    p_wait = panel(f"Which crowns can wait: {best['n']:,} of {len(test_recs):,} test crowns, "
                   f"revocable at the next model change",
                   "<b>Use this to order the queue, not to close crowns.</b> These are the "
                   "crowns to look at last, and the ranking is recomputed from scratch "
                   "whenever Pl@ntNet updates.", body)

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
             f'deprioritized under a gated rule, because the gate excludes them.</p>')
    p_rules = panel("How the five candidate rules compare, including the ungated ones",
                    "<b>Read this only if you want to move the threshold.</b> Each row trades "
                    "queue reduction against how often a deprioritized crown was actually "
                    "misidentified.", body)

    # ---- confidence ----
    # Same blue as the support-bucket chart in the next panel. Both draw the same
    # measure, and a reader comparing the two should not have to decide whether a
    # colour change means something. Green is spoken for by the status tags.
    body = (svg_hbar([(band, k / nn if nn else 0.0,
                       f'{pctf(k / nn) if nn else "n/a"}  ·  {nn:,} crowns', "#1565c0")
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
                    [[BAND_SHORT[lab], f"{flat[lab][0]:,}",
                      pctf(flat[lab][1] / flat[lab][0])]
                     for lab in hc.BUCKET_ORDER if lab in flat])
            + '<p class="note">Raising the confidence threshold does not repair this. '
              'Requiring the species to have been measured first does, which is why the '
              'suggested rule has two conditions.</p>')
    p_conf = panel("Can we trust the model's confidence? In bulk yes, on rare species no",
                   "<b>This is the evidence behind the two-part rule above.</b> Read it if "
                   "someone proposes ordering the queue on confidence alone.", body)

    # ---- labelled crowns vs accuracy ----
    body = (svg_hbar([(BAND_SHORT[lab], buckets[lab]["c1"] / buckets[lab]["n_crowns"],
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
    p_labels = panel("Does accuracy rise with more labels? It rises with abundance, and the "
                     "model is frozen",
                     "<b>Use this to see where the measurement is solid enough to act on.</b> "
                     "Do not use it to argue that labelling raises accuracy.", body)

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
            # A sparkline over 1 to 4 crowns draws a coin flip as a trend: 49 of
            # them run rail to rail on a single crown changing answer, and 55 are
            # the same flat line for accuracies from 0 to 1. The model is frozen,
            # so none of that movement is learning. Below the support floor the
            # cell says so instead of drawing a shape the panel text retracts.
            (trend.spark(f"species:{sp}:top1", empty="")
             if d["n_labelled_crowns"] >= WAIT_SUPPORT_MIN
             else '<span class="nospark">too few crowns</span>'),
            status_with_reason(st, STATUS[st][0], STATUS_REASON[st])])
        attrs.append(f' data-species="{esc(sp)}" data-status="{st}"')
    body = ('<p class="note">Hover the info icon for the reason behind each status.</p>'
            + filterable_table(
        [("Species", False), ("Labelled crowns", True),
         ("First guess right", True), ("Right name in the list", True),
         ("Model's confidence", True), ("Trend", False), ("Status", False)],
        sp_rows,
        options=[(k, v[0]) for k, v in STATUS.items()],
        row_attrs=attrs,
    ))
    p_species = panel(f"Look up one species: all {n_sp}, sortable and filterable",
                      "<b>Find a species you care about and read its status.</b> Click any "
                      "heading to sort, type to filter. The trend column draws a line only "
                      f"where there are two or more snapshots and at least {WAIT_SUPPORT_MIN} "
                      "labelled crowns, because below that one crown changing answer swings "
                      "the line from end to end.", body)

    # ---- ceiling ----
    body = (f'<p class="note"><strong>{len(never)} species ({never_crowns} of the {n:,} '
            f'evaluated crowns) never appear in any answer the model gave us.</strong> '
            f'Leaving them out raises the per-crown rate from {pctf(c1 / n)} to '
            f'{pctf(reach1)} on {len(reach):,} crowns. Across all {len(h.gt_rows):,} labelled '
            f'crowns the same condition covers {never_all} crowns.</p>'
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
              f'genus level they reach {pctf(gg1 / gn) if gn else "n/a"}. Of them, '
              f'{gen_any:,} have at least one candidate in the right genus among the five, '
              f'and <strong>{gen_one:,} have exactly one</strong>, which turns the question '
              f'into a yes or no rather than an identification. Whether taking them down to '
              f'species is worth expert time is a prioritisation question, not a model '
              f'question.</p>'
              f'<p class="note">A further {fam_n} crowns are labelled to '
              f'{fam_names} <em>families</em> rather than genera. They are excluded from the '
              f'genus rate above and cannot be scored at all offline: a family name can never '
              f'match a predicted species name, and mapping predictions up to family would '
              f'need a family lookup covering Pl@ntNet\'s vocabulary, which we do not have '
              f'here. Counting them in would have reported '
              f'{pctf(gg1 / (gn + fam_n))} instead of {pctf(gg1 / gn)}.</p>')
    p_ceiling = panel(f"What labelling cannot fix: {len(never)} species, {never_crowns} crowns "
                      f"the model never named, and why the five-candidate cap may be the cause",
                      "<b>Do not spend expert time renaming or relabelling these.</b> Either "
                      "the model cannot return the species or we never asked for enough "
                      "candidates to find out, and only re-running the predictions can tell "
                      "the two apart.", body)

    # ---- method ----
    p_method = method_panel(tag=trend.tag, n=n, n_sp=n_sp, checks=checks)

    # ---- three groups, so the page reads as decide, then interpret, then caveat ----
    P.append(section("What to do next",
                     "Which crowns to send first, which can wait, which labels deserve a "
                     "second look, and how any one species is doing.",
                     "\n".join([p_todo, p_send, p_wait, p_rules, p_species, p_review])))
    P.append(section("How to read the numbers",
                     "The two headline scores disagree. These panels say why, and whether the "
                     "model's own confidence can be trusted.",
                     "\n".join([p_weighting, p_conf, p_labels, p_trend])))
    P.append(section("What this cannot tell you",
                     "The ceilings on every number above.",
                     "\n".join([p_candidates, p_ceiling, p_method])))

    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Pl@ntNet on BCI - per-species model health</title>"
            # No footer: the subtitle already carries the build date, the snapshot and
            # the model tag, and a second copy at the foot said nothing new.
            f"<style>{CSS}</style></head><body>" + "\n".join(P)
            + f"<script>{JS}</script></body></html>"), checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", default=hc.GT_CSV)
    ap.add_argument("--splits", default=hc.SPLITS_CSV)
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument("--verify-against", default=None,
                    help="directory holding the committed measurement CSVs to cross-check; "
                         "defaults to the newest model-health-<date>/ folder, whose "
                         "siblings are the trend history")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "build",
                                                  "model_health_dashboard.html"))
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    args = ap.parse_args()

    h = hc.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=args.verify_against or latest_snapshot_dir(),
                         fallback_tag=args.model_tag,
                         cache_dir=args.cache_dir)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    # Encode here rather than letting open() do it, so the reported size is the
    # size on disk. Accented species names cost more than one byte apiece, so
    # len(page) undercounts by ten and a reader comparing against ls is misled.
    blob = page.encode("utf-8")
    with open(args.out, "wb") as f:
        f.write(blob)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {args.out}  ({len(blob):,} bytes)")


if __name__ == "__main__":
    main()
