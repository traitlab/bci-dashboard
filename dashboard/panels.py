#!/usr/bin/env python3
"""Every panel the dashboard pages can carry, and the one context they share.

The 2026-08-27 split gave the panels two audiences. The internal page answers
"what do we label next" and belongs to the labelling team; its real deliverable
is ``send_batches.csv``, so the page stays thin. The external page answers "how
does Pl@ntNet do against the labels" and is the one that leaves the lab. A
panel therefore names its audience once, here, instead of a page hand-keeping a
list of what it happens to include.

``prepare`` computes every derived figure once and each builder reads it, rather
than each builder recomputing from ``Health``. Two panels recomputing the same
figure is exactly the drift ``history.verify_snapshot`` exists to catch, and it
would catch it only after both pages were already built.

Stdlib only, like the rest of ``dashboard/``.
"""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core as hc  # noqa: E402
from assets import (CSS, JS, cap, esc, filterable_table, panel, pctf,  # noqa: E402
                    section, status_legend, status_tag, svg_hbar, table)
from explain import (BAND_SHORT, candidates_panel, method_panel,  # noqa: E402
                     weighting_panel)
from history import model_tag_of, snapshot_date_of  # noqa: E402

# A species is "rarely labelled" below this many frames. Same threshold as the
# deprioritization support gate, so the two panels cannot disagree.
RARE_MAX_SUPPORT = 10
# Deliberately equal to hc.WELL_SAMPLED_MIN_N, the threshold hc.diagnose uses,
# so this page renders the same status hc.diagnose would for the same species.
WAIT_SUPPORT_MIN = 10
RECOMMENDED_CONF = 0.8

# Enough to answer "what do I send next" without a CSV reader. A batch is 100
# frames, so 25 is one morning's work and still short enough to read.
SEND_PREVIEW = 25
# Same reasoning, shorter: this list is read, not worked through.
REVIEW_PREVIEW = 15

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
    "unmeasured": "Fewer than 10 labelled frames, so the score is too thin to trust yet.",
    "hard": "Enough frames, but the first guess is still weak, so more labels will not fix it.",
    "adequate": "Mixed results, so keep it in the normal review queue.",
    "reliable": "Usually right, so this species is low priority for extra work.",
    "unreachable": "It never appears in the five candidates we asked for, so labelling will not "
                   "recover it. Whether Pl@ntNet carries the species at all is not known from here.",
}

# A 2x2 grid: question asked (rows) by how it was averaged (columns), because
# 50.3% / 79.5% side by side reads as one superseding the other.
# (metric, question, averaged over, note).
HEADLINES = [
    ("macro_top1", "First guess is right", "per species",
     "each of the {n_sp} species counts once, however few frames it has"),
    ("micro_top1", "First guess is right", "per frame",
     "one vote per labelled frame, so common species dominate"),
    ("macro_top5", "Right name is among the 5 requested", "per species",
     "the ceiling reranking can reach at nb-results=5, not the model's ceiling"),
    ("micro_top5", "Right name is among the 5 requested", "per frame",
     "we only ever asked Pl@ntNet for 5 names"),
]

# Sits directly under the grid. Without it the two columns read as a
# contradiction rather than as two questions.
HERO_READING = (
    "Read down a column, not across. <b>Per species</b> is the number to quote for "
    "a species picked off the checklist; <b>per frame</b> is the number to quote for "
    "a photo picked off the drive. Per frame is the higher of the two because the "
    "species with many frames are the ones Pl@ntNet already knows."
)

# What a reader has to know before any of the four numbers means anything.
HERO_TERMS = (
    "A <b>frame</b> is one 4000&times;3000 drone photo. Its label is the species whose "
    "outlined crowns cover the largest total area in the <i>whole</i> frame. The photo sent "
    "to Pl@ntNet is the <b>1280&times;1280 centre crop</b>, which is 13.65% of that frame. "
    "We asked Pl@ntNet for 5 names per crop (<code>nb-results=5</code>, our request "
    "parameter, not a model limit); the <b>first guess</b> is the top-ranked one. Right "
    "means it matches the frame's label."
)

# The two regions above are not the same region, and the numbers below compare
# across them. Stated here rather than in a footnote because every figure on
# this page inherits the mismatch.
HERO_REGION = (
    "<strong>These four numbers score a centre crop against a whole-frame label.</strong> "
    "On 1,377 of 3,777 evaluated records the labelled species covers less than half the "
    "crop, and on 207 it covers none of it, so a wrong answer here is not always a wrong "
    "identification. Read them as a provenance record of the centre-crop path, not as the "
    "model's accuracy. The region-aligned replacement is the crown arm, where the unit "
    "of prediction is the unit the label describes."
)

# Queue name -> (what it is, why it is worth sending). Shown in the order
# hc.QUEUE_ORDER gives, which is the order the CSV is sorted in.
QL = {"long_tail": ("Species we barely have",
                    "The guess points at a species with fewer than 10 labelled frames, "
                    "or one the model gets wrong even with more. These frames fill the "
                    "long tail the labelling programme exists for"),
      "low_conf_known": ("A usually-right species, guessed weakly",
                         "The species is normally identified well but the model is "
                         "unsure here, so the photo is either an odd one worth having "
                         "or a quiet miss"),
      "normal": ("Everything else", "The ordinary queue"),
      "can_wait": ("Confident on a well-covered species",
                   "The two-part rule below says these can wait; look at them last")}


def is_family(n: str) -> bool:
    """A one-word label ending in -aceae is a family, not a genus.

    Every botanical family name carries that suffix and no accepted genus does,
    so the test is exact rather than a heuristic. It matters because a family
    label can never equal a predicted genus, so counting those frames into a
    genus-level rate would report guaranteed misses as measured ones.
    """
    return n.strip().lower().endswith("aceae")


def top1(r):
    return r["ranked"][0][0]


def conf(r):
    return r["ranked"][0][1]


def camera_of(key):
    """Which drone lens shot a frame, read off its key.

    The drone flies a zoom and a tele lens and the filename records which.
    Counted, not assumed: the two populations are not the same one.
    """
    low = key.lower()
    for c in ("zoom", "tele"):
        if c in low:
            return c
    raise SystemExit(f"frame key names no camera: {key!r}. The camera split "
                     f"below reads the key, so a third camera has to be handled "
                     f"here rather than counted as neither.")


def prepare(h, *, verify_dir, fallback_tag) -> SimpleNamespace:
    """Every figure both pages draw from, computed once off one ``Health``.

    The returned context is read-only as far as the builders are concerned, with
    one exception: ``checks`` is filled in by the page after it has run its own
    slice of ``history.verify_snapshot``, because which invariants apply is a
    property of the page, not of the measurement.
    """
    sp_recs, per_species = h.sp_recs, h.per_species
    n, n_sp = len(sp_recs), len(per_species)

    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:5]])
    now = dict(macro_top1=sum(d["top1_accuracy"] for d in per_species) / n_sp,
               macro_top5=sum(d["top5_accuracy"] for d in per_species) / n_sp,
               micro_top1=c1 / n, micro_top5=c5 / n)

    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    status = {d["species"]: hc.diagnose(d) for d in per_species}
    counts = defaultdict(int)
    for s in status.values():
        counts[s] += 1

    # --- frames grouped by how many labels their species has ---
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
    # "Never named": in no cached candidate list, so no threshold scores it. Counted
    # over the evaluated set and over every label; the run log uses the second.
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

    tag = model_tag_of(verify_dir, fallback_tag)
    snap_date = snapshot_date_of(verify_dir)

    # --- send-first queue over the unlabelled pool, and labels worth a second look.
    # The logic lives in core so this page and measure.py cannot drift apart.
    acc_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    joined_stems = {stem for _, stem, _ in h.joined}
    queue_counts = {}
    lt_species = defaultdict(int)
    queue_rows = []
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
        queue_rows.append((q, stem, pred, cf))
        if q == "long_tail":
            lt_species[pred] += 1
    n_unlab = sum(queue_counts.values())
    # send_first_queue.csv's own order. The page prints the head of that file and
    # tells the reader to open the rest, so two sorts would be two lists.
    queue_rows.sort(key=lambda r: (hc.QUEUE_ORDER.index(r[0]), r[3], r[1]))

    scored_cams = Counter(camera_of(r["global_key"]) for r in sp_recs)
    queue_cams = Counter(camera_of(stem) for _, stem, _, _ in queue_rows)

    confident = [r for r in sp_recs if conf(r) >= hc.REVIEW_CONF]
    review = [r for r in confident if top1(r) != r["gt"]]
    # The claim the review panel rests on. Measured, not asserted: it moves with
    # every batch, and stale it argues for spending expert time on the wrong list.
    confident_ok = (len(confident) - len(review)) / len(confident)
    review_pairs = defaultdict(list)
    for r in review:
        review_pairs[(r["gt"], top1(r))].append(conf(r))
    review_counts = (len(review), len(review_pairs))

    # --- why confidence alone is unsafe: error by labelled frames, at conf>=0.7 ---
    flat = {}
    for r in sp_recs:
        if conf(r) >= 0.7:
            b = flat.setdefault(hc.bucket_label(support[r["gt"]]), [0, 0])
            b[0] += 1
            b[1] += top1(r) != r["gt"]

    # --- queue-ordering rules. Which species clear the gate is decided from train frames
    # only, then scored on test only, so no rule is graded on the frames that defined it.
    train_support = defaultdict(int)
    for r in sp_recs:
        if r["split"] == "train":
            train_support[r["gt"]] += 1
    eligible = {s for s, k in train_support.items() if k >= WAIT_SUPPORT_MIN}
    test_recs = [r for r in sp_recs if r["split"] == "test"]
    rare = {s for s, k in support.items() if k < RARE_MAX_SUPPORT}
    n_rare_test = sum(1 for r in test_recs if r["gt"] in rare)

    rules = [(f"confidence &ge; {t}, any species", t, False) for t in (0.7, 0.8)]
    rules += [(f"confidence &ge; {t} and at least {WAIT_SUPPORT_MIN} labelled frames for "
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

    # Kept apart from family-only labels: a family name can never equal a predicted
    # genus, so mixing them scores guaranteed misses as measured ones.
    fam_recs = [r for r in h.genus_recs if is_family(r["gt"])]
    gen_recs = [r for r in h.genus_recs if not is_family(r["gt"])]
    gn, fam_n = len(gen_recs), len(fam_recs)
    gg1 = sum(1 for r in gen_recs if hc.genus_of(r["ranked"][0][0]) == r["gt"])
    fam_names = len({r["gt"] for r in fam_recs})
    # Genus-only frames whose right answer is narrowed to one in-genus candidate:
    # the cheapest confirmation on the page, a yes/no rather than an identification.
    in_gen = [sum(1 for b, _ in r["ranked"][:5] if hc.genus_of(b) == r["gt"]) for r in gen_recs]
    gen_any = sum(1 for k in in_gen if k)
    gen_one = sum(1 for k in in_gen if k == 1)
    gen_none = len(in_gen) - gen_any

    return SimpleNamespace(
        h=h, sp_recs=sp_recs, per_species=per_species, n=n, n_sp=n_sp,
        c1=c1, c5=c5, now=now, support=support, status=status, counts=counts,
        buckets=buckets, bins_all=bins_all, never=never, never_crowns=never_crowns,
        never_all=never_all, reach=reach, reach1=reach1, unscoreable=n - len(reach),
        strict1=strict1, short5=short5, n_pred=n_pred, tag=tag, snap_date=snap_date,
        queue_counts=queue_counts, lt_species=lt_species, queue_rows=queue_rows,
        n_no_answer=n_no_answer, n_unlab=n_unlab, scored_cams=scored_cams,
        queue_cams=queue_cams, confident=confident, review=review,
        confident_ok=confident_ok, review_pairs=review_pairs, review_counts=review_counts,
        flat=flat, eligible=eligible, test_recs=test_recs, rare=rare,
        n_rare_test=n_rare_test, ops=ops, best=best, gn=gn, fam_n=fam_n, gg1=gg1,
        fam_names=fam_names, gen_any=gen_any, gen_one=gen_one, gen_none=gen_none,
        checks=None)


# ---------------------------------------------------------------------------
# Panels. One function per panel, each reading only the prepared context, so a
# page is a list of panel ids rather than 400 lines of interleaved rendering.
# ---------------------------------------------------------------------------

def p_todo(c):
    body = ['<ul class="todo">']
    body += [f'<li><span class="n">{c.counts[k]}</span> species '
             f'<span class="tag {k}">{esc(lab)}</span> {esc(act)}</li>'
             for k, (lab, act) in STATUS.items()]
    body.append(f'</ul><p class="note">Each of the {c.n_sp} species sits in exactly one row. '
                f'The numbers behind each status are in the species table below.</p>'
                f'<p class="note"><strong>Cheaper still, and not counted in any row above: '
                f'{c.gen_one:,} frames whose botanist label stops at the genus and whose five '
                f'candidates contain exactly one species from that genus.</strong> The question '
                f'there is yes or no, not which of {c.n_sp}. Those frames are outside the '
                f'{c.n_sp} species scored on this page because they never named a species; see '
                f'the genus paragraph under &ldquo;What this cannot tell you&rdquo;.</p>')
    return panel(f"Where to spend botanist time next: {c.counts['ranking']} species are a "
                 f"cheap confirmation, {c.counts['unreachable']} are not worth time yet",
                 "<b>Work top to bottom.</b> Rows are ordered cheapest useful work first, "
                 "and the last two rows are work you can skip.",
                 "\n".join(body), open_=True)


def p_send(c):
    body = table([("queue", False), ("unlabelled frames", True),
                  ("share of the pool", True)],
                 [[f'<strong>{esc(QL[q][0])}</strong>' if q in ("long_tail", "low_conf_known")
                   else esc(QL[q][0]),
                   f'{c.queue_counts.get(q, 0):,}',
                   pctf(c.queue_counts.get(q, 0) / c.n_unlab if c.n_unlab else None)]
                  for q in hc.QUEUE_ORDER])
    # The list itself, not a pointer to it: the counts above say how much work
    # there is, and the CSV in the snapshot folder said which photo.
    head = c.queue_rows[:SEND_PREVIEW]
    body += ('<h3 class="sub">The next ' + f'{len(head)}' + ' photos, in order</h3>'
             + table([("#", True), ("photo", False), ("Pl@ntNet's guess", False),
                      ("confidence", True), ("frames that species has", True)],
                     [[f"{i}", f'<code class="key">{esc(stem)}</code>',
                       f'<span class="sp">{esc(cap(pred))}</span>', f"{cf:.3f}",
                       f"{c.support.get(pred, 0):,}"]
                      for i, (_, stem, pred, cf) in enumerate(head, 1)]))
    top_lt = sorted(c.lt_species.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    body += (f'<p class="note">Most-named species in the first queue: '
             + ", ".join(f'<span class="sp">{esc(cap(s))}</span> ({k:,})' for s, k in top_lt)
             + '.</p>'
             f'<p class="note">Every frame, in order, is in <code>send_first_queue.csv</code> '
             f'in the snapshot folder: queue, photo key, the guess and its confidence, and '
             f'how well that species is already measured. Weakest confidence first inside '
             f'each queue, so the top of the file is the next batch.</p>'
             f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Those are the '
             f'candidate junk or non-plant photos (leaves in the water, bare trunks). There '
             f'is no reliable automatic rule for junk, so check that handful by eye before '
             f'queueing them rather than filtering on it.</p>'
             f'<p class="note"><b>Every frame scored on this page was shot with the zoom '
             f'lens</b> ({c.scored_cams["zoom"]:,} of {sum(c.scored_cams.values()):,}), while '
             f'{c.queue_cams["tele"]:,} of the {sum(c.queue_cams.values()):,} photos in this '
             f'queue ({pctf(c.queue_cams["tele"] / sum(c.queue_cams.values()))}) are tele. No '
             f'accuracy on this page has been measured on a tele frame, because no tele '
             f'frame has a botanist label yet, so how well the model reads that lens is '
             f'not known from here. Sending them is how it becomes known.</p>'
             f'<p class="note">The pool is {c.n_unlab:,} of {len(c.h.split_rows):,} photos: '
             f'the frames with a cached Pl@ntNet answer and no botanist label. The species '
             f'record behind each queue is the one measured above, so a model update '
             f're-sorts this queue exactly as it re-sorts the can-wait one.</p>')
    return panel(f"What to send to the botanist first: "
                 f"{c.queue_counts.get('long_tail', 0):,} "
                 f"of {c.n_unlab:,} unlabelled photos point at species we barely have",
                 "<b>Work the queues top to bottom.</b> The first two buy the most per "
                 "label: the long tail, where a species has almost nothing to be scored "
                 "on, and the photos where a usually-right species is guessed weakly.",
                 body)


def p_review(c):
    pair_rows = sorted(c.review_pairs.items(), key=lambda kv: -len(kv[1]))[:10]
    body = (table([("botanist label", False), ("Pl@ntNet's first guess", False),
                   ("frames", True), ("mean confidence", True)],
                  [[f'<span class="sp">{esc(cap(gt))}</span>',
                    f'<span class="sp">{esc(cap(pr))}</span>',
                    f"{len(cs):,}", f"{sum(cs) / len(cs):.2f}"]
                   for (gt, pr), cs in pair_rows])
            if pair_rows else '<p class="note">None at this threshold.</p>')
    # The frames themselves, most confident first, each linked into Labelbox where
    # the link is known. Known means an export carried that data row: the URL is
    # read from what a merge recorded, never guessed and never fetched.
    urls = hc.labelbox_urls()
    top_review = sorted(c.review, key=lambda r: -conf(r))[:REVIEW_PREVIEW]
    linked = sum(1 for r in c.review if r["global_key"] in urls)
    body += table([("frame", False), ("botanist label", False),
                   ("Pl@ntNet's first guess", False), ("confidence", True)],
                  [[(f'<a href="{esc(urls[r["global_key"]])}" target="_blank" '
                     f'rel="noopener">{esc(r["global_key"])}</a>'
                     if r["global_key"] in urls else esc(r["global_key"])),
                    f'<span class="sp">{esc(cap(r["gt"]))}</span>',
                    f'<span class="sp">{esc(cap(top1(r)))}</span>',
                    f"{conf(r):.2f}"]
                   for r in top_review])
    body += (f'<p class="note">The {len(top_review)} most confident disagreements. '
             f'A frame name links straight to its Labelbox data row where that link '
             f'is known: {linked} of {len(c.review)} frames here, because a data row id '
             f'is only known for frames carried by an export this ground truth was '
             f'merged from. Frames labelled in a project that has not been exported '
             f'since are listed without a link rather than sent to a guessed URL.</p>')
    body += (f'<p class="note">Each row is a labelled frame where the model is at least '
             f'{hc.REVIEW_CONF:.1f} confident in a <em>different</em> species. A first guess '
             f'this confident is right {pctf(c.confident_ok)} of the time in bulk '
             f'({len(c.confident) - len(c.review):,} of {len(c.confident):,}), so each of '
             f'these is either a rare confident model error or a label error, and a label '
             f'error found this way is the cheapest label fix available. Offline there is no '
             f'way to tell which; that is the botanist\'s minute. '
             f'Every frame is in <code>label_review_queue.csv</code> in the snapshot folder, '
             f'most confident first.</p>'
             f'<p class="note">Not urgent: work this list after the send-first queues. A '
             f'confusion pair that keeps recurring is a signal about the species, not just '
             f'the photo.</p>')
    return panel(f"Labels worth a second look: {c.review_counts[0]} frames where Pl@ntNet "
                 f"confidently disagrees",
                 "<b>Possible label errors, possible model errors.</b> Either way they "
                 "are the disagreements most worth an expert's minute, once the cheap "
                 "queues above are worked through.", body)


def p_wait(c):
    best = c.best
    body = (f'<div class="rec"><strong>Suggested rule: leave a frame for later when '
            f'Pl@ntNet is at least {RECOMMENDED_CONF} confident and its species already has '
            f'{WAIT_SUPPORT_MIN} or more labelled frames.</strong> On held-out test frames '
            f'that is {best["n"]:,} of {len(c.test_recs):,} ({pctf(best["share"])}), and the '
            f'first guess is wrong on {pctf(best["err"])} of them.</div>'
            '<p class="note"><strong>Nothing here is a label.</strong> A frame that can wait '
            'keeps whatever ground truth it already has, or none at all. No prediction is '
            'ever written into ground truth by this rule. It only pushes frames down the '
            "botanist's queue.</p>"
            f'<p class="note"><strong>The decision expires with the model.</strong> Pl@ntNet '
            f'ships a new model every few months, on its own schedule rather than ours, and '
            f'a frame deprioritized under <code>{esc(c.tag)}</code> is not deprioritized '
            f'under the next one. Re-run this page after every model change and the queue '
            f're-sorts. Any frame can come back to the top.</p>'
            f'<p class="note">{len(c.eligible)} species clear the {WAIT_SUPPORT_MIN}-frame '
            f'gate, counted from <code>train</code> frames only, and the error rate above is '
            f'then measured on the {len(c.test_recs):,} <code>test</code> frames only.</p>')
    return panel(f"Which frames can wait: {best['n']:,} of {len(c.test_recs):,} test frames, "
                 f"revocable at the next model change",
                 "<b>Use this to order the queue, not to close frames.</b> These are the "
                 "frames to look at last, and the ranking is recomputed from scratch "
                 "whenever Pl@ntNet updates.", body)


def p_rules(c):
    body = table([("rule", False), ("frames that can wait", True),
                  ("share of the queue", True), ("of those, first guess wrong", True),
                  ("rarely-labelled frames among them", True),
                  ("rarely-labelled share of what is left", True)],
                 [[f'<strong>{o["label"]}</strong>' if o is c.best else o["label"],
                   f'{o["n"]:,}', pctf(o["share"]), pctf(o["err"]), f'{o["rare"]}',
                   pctf(o["rare_rest"])] for o in c.ops])
    body += (f'<p class="note">A species with fewer than {RARE_MAX_SUPPORT} labelled frames '
             f'counts as rarely labelled: {len(c.rare)} of {c.n_sp} species, {c.n_rare_test} '
             f'of the {len(c.test_recs):,} test frames. No rarely-labelled frame can be '
             f'deprioritized under a gated rule, because the gate excludes them.</p>')
    return panel("How the five candidate rules compare, including the ungated ones",
                 "<b>Read this only if you want to move the threshold.</b> Each row trades "
                 "queue reduction against how often a deprioritized frame was actually "
                 "misidentified.", body)


def p_conf(c):
    # Same blue as the next panel's chart: same measure, so a colour change would
    # read as meaning something. Green is spoken for by the status tags.
    flat = c.flat
    body = (svg_hbar([(band, k / nn if nn else 0.0,
                       f'{pctf(k / nn) if nn else "n/a"}  ·  {nn:,} frames', "#1565c0")
                      for band, nn, k in c.bins_all],
                     title="how often the first guess is right, by the model's own confidence")
            + '<p class="note">Over all frames at once the confidence score is trustworthy: '
              'when the model is sure it is almost always right. That is what makes queue '
              'ordering possible at all.</p>'
              '<p class="note"><strong>It is not trustworthy on rarely-labelled '
              'species.</strong> Ordering the queue on confidence alone would push exactly '
              'the species you care about to the bottom:</p>'
            + table([("labelled frames for that species", False),
                     ("frames at confidence &ge; 0.7", True),
                     ("of those, first guess wrong", True)],
                    [[BAND_SHORT[lab], f"{flat[lab][0]:,}",
                      pctf(flat[lab][1] / flat[lab][0])]
                     for lab in hc.BUCKET_ORDER if lab in flat])
            + '<p class="note">Raising the confidence threshold does not repair this. '
              'Requiring the species to have been measured first does, which is why the '
              'suggested rule has two conditions.</p>')
    return panel("Can we trust the model's confidence? In bulk yes, on rare species no",
                 "<b>This is the evidence behind the two-part rule above.</b> Read it if "
                 "someone proposes ordering the queue on confidence alone.", body)


def p_labels(c):
    buckets = c.buckets
    body = (svg_hbar([(BAND_SHORT[lab], buckets[lab]["c1"] / buckets[lab]["n_crowns"],
                       f'{pctf(buckets[lab]["c1"] / buckets[lab]["n_crowns"])}  ·  '
                       f'{buckets[lab]["n_species"]} spp, {buckets[lab]["n_crowns"]:,} '
                       f'frames', "#1565c0")
                      for lab in hc.BUCKET_ORDER
                      if buckets.get(lab) and buckets[lab]["n_crowns"]],
                     title="how often the first guess is right, by how many frames that "
                           "species has")
            + '<div class="warn"><strong>Read this as how common the species is, not as '
              'training data.</strong> These predictions come from a frozen Pl@ntNet '
              'regional model that has never seen a single BCI label, so labelling a species '
              'does not make Pl@ntNet better at it. What this axis really tracks is how '
              'common a species is on the plot, and common species also have more reference '
              'photos inside Pl@ntNet. What extra labels buy is knowledge: below about '
              f'{WAIT_SUPPORT_MIN} frames a per-species accuracy jumps around too much to '
              f'act on, and above it the species can enter the queue-ordering rule.</div>')
    return panel("Does accuracy rise with more labels? It rises with abundance, and the "
                 "model is frozen",
                 "<b>Use this to see where the measurement is solid enough to act on.</b> "
                 "Do not use it to argue that labelling raises accuracy.", body)


def p_species(c):
    sp_rows, attrs = [], []
    for d in sorted(c.per_species, key=lambda x: (-x["n_labelled_crowns"], x["species"])):
        sp, st = d["species"], c.status[d["species"]]
        sp_rows.append([
            f'<span class="sp" data-sort="{esc(sp)}">{esc(cap(sp))}</span>',
            f'<span data-sort="{d["n_labelled_crowns"]}">{d["n_labelled_crowns"]:,}</span>',
            f'<span data-sort="{d["top1_accuracy"]:.6f}">{pctf(d["top1_accuracy"])}</span>',
            f'<span data-sort="{d["top5_accuracy"]:.6f}">{pctf(d["top5_accuracy"])}</span>',
            f'<span data-sort="{d["mean_top1_confidence"]:.6f}">'
            f'{d["mean_top1_confidence"]:.2f}</span>',
            status_tag(st, STATUS[st][0])])
        attrs.append(f' data-species="{esc(sp)}" data-status="{st}"')
    body = (status_legend([(st, STATUS[st][0], STATUS_REASON[st]) for st in STATUS])
            + filterable_table(
        [("Species", False), ("Labelled frames", True),
         ("First guess right", True), ("Right name in the list", True),
         ("Model's confidence", True), ("Status", False)],
        sp_rows,
        options=[(k, v[0]) for k, v in STATUS.items()],
        row_attrs=attrs,
    ))
    return panel(f"Look up one species: all {c.n_sp}, sortable and filterable",
                 "<b>Find a species you care about and read its status.</b> Click any "
                 "heading to sort, type to filter.", body)


def p_ceiling(c):
    n, gn = c.n, c.gn
    body = (f'<p class="note"><strong>{len(c.never)} species ({c.never_crowns} of the {n:,} '
            f'evaluated frames) never appear in any answer the model gave us.</strong> '
            f'Leaving them out raises the per-frame rate from {pctf(c.c1 / n)} to '
            f'{pctf(c.reach1)} on {len(c.reach):,} centre crops. Across all '
            f'{len(c.h.gt_rows):,} labelled frames the same condition covers '
            f'{c.never_all} frames.</p>'
            f'<div class="warn"><strong>This is a limit of the question we asked, not proof '
            f'the model has never heard of these species.</strong> The only test we can run '
            f'offline is whether a species name turns up somewhere in the cached answers, and '
            f'we asked Pl@ntNet for its best five candidates per photo. A species Pl@ntNet '
            f'knows perfectly well, but which never made anyone\'s top five on a BCI photo, '
            f'is indistinguishable here from one it truly cannot return. The five-candidate '
            f'cap is what hides the difference. It did not bite everywhere: on '
            f'{c.short5:,} of the {c.n_pred:,} frames with a cached answer '
            f'({pctf(c.short5 / c.n_pred)}) fewer than five candidates came back, so nothing '
            f'was cut off. On the other {c.n_pred - c.short5:,} the list was full, and '
            f'anything the model would have ranked sixth or lower is invisible to us. The way '
            f'to find out is to re-run the predictions asking for more candidates per photo. '
            f'More name cleaning will not help, because names are already matched as well as '
            f'they can be.</div>'
            + table([("Species", False), ("Labelled frames", True)],
                    [[f'<span class="sp">{esc(cap(d["species"]))}</span>',
                      f'{d["n_labelled_crowns"]:,}'] for d in c.never])
            + f'<p class="note"><strong>Spelling and renamed species are not costing us '
              f'anything.</strong> Labels and predictions are put into the same standard form '
              f'before they are compared, and old names are resolved to current ones. Scoring '
              f'the raw names instead would give {pctf(c.strict1 / n)} rather than '
              f'{pctf(c.c1 / n)} on the centre crop, so that matching is worth '
              f'{100 * (c.c1 - c.strict1) / n:+.2f} points, or {c.c1 - c.strict1} frames. '
              f'Treat it as a gain already banked, not as a source of error.</p>'
              f'<p class="note"><strong>{gn:,} further frames carry only a genus '
              f'name</strong> and are left out of every species number above. Scored at '
              f'genus level they reach {pctf(c.gg1 / gn) if gn else "n/a"}. Of them, '
              f'{c.gen_any:,} have at least one candidate in the right genus among the five, '
              f'and <strong>{c.gen_one:,} have exactly one</strong>, which turns the question '
              f'into a yes or no rather than an identification. Whether taking them down to '
              f'species is worth expert time is a prioritisation question, not a model '
              f'question.</p>'
              f'<p class="note">A further {c.fam_n} frames are labelled to '
              f'{c.fam_names} <em>families</em> rather than genera. They are excluded from '
              f'the genus rate above and cannot be scored at all offline: a family name can '
              f'never match a predicted species name, and mapping predictions up to family '
              f'would need a family lookup covering Pl@ntNet\'s vocabulary, which we do not '
              f'have here. Counting them in would have reported '
              f'{pctf(c.gg1 / (gn + c.fam_n))} instead of {pctf(c.gg1 / gn)}.</p>')
    return panel(f"What labelling cannot fix: {len(c.never)} species, {c.never_crowns} frames "
                 f"the model never named, and why the five-candidate cap may be the cause",
                 "<b>Do not spend expert time renaming or relabelling these.</b> Either "
                 "the model cannot return the species or we never asked for enough "
                 "candidates to find out, and only re-running the predictions can tell "
                 "the two apart.", body)


def p_candidates(c):
    return candidates_panel(recs=c.sp_recs + c.h.genus_recs, gen_n=c.gn, gen_none=c.gen_none)


def p_weighting(c):
    return weighting_panel(per_species=c.per_species, sp_recs=c.sp_recs, support=c.support,
                           buckets=c.buckets, now=c.now, n=c.n, n_sp=c.n_sp)


def p_method(c):
    if c.checks is None:
        raise SystemExit("the method panel reports the build's own verification lines, so "
                         "the page must run verify_snapshot and set ctx.checks before "
                         "rendering it.")
    return method_panel(tag=c.tag, n=c.n, n_sp=c.n_sp, checks=c.checks)


# ---------------------------------------------------------------------------
# The registry: which section a panel belongs to, and which page carries it.
# ---------------------------------------------------------------------------

# section key -> (heading, the one orienting line under it).
SECTIONS = {
    "label-first": (
        "What to label first",
        "Which frames to send, which can wait, and the evidence behind the wait rule."),
    "model-health": (
        "How Pl@ntNet is doing against the labels",
        "The two headline scores disagree. These panels say why, how any one species is "
        "doing, and which labels deserve a second look."),
    "limits": (
        "What this cannot tell you",
        "The ceilings on every number above."),
}

# panel id -> (section key, builder). A panel belongs to the goal it serves, so
# the confidence evidence sits with the queue rule it justifies and the species
# lookup sits with the scores it reports.
PANELS = {
    "todo": ("label-first", p_todo),
    "send": ("label-first", p_send),
    "wait": ("label-first", p_wait),
    "rules": ("label-first", p_rules),
    "conf": ("label-first", p_conf),
    "weighting": ("model-health", p_weighting),
    "labels": ("model-health", p_labels),
    "species": ("model-health", p_species),
    "review": ("model-health", p_review),
    "candidates": ("limits", p_candidates),
    "ceiling": ("limits", p_ceiling),
    "method": ("limits", p_method),
}

# The 2026-08-27 split. Internal is the labelling team's tool and stays thin;
# its real deliverable is send_batches.csv. External is what leaves the lab, and
# the confident disagreements go with it so they can be worked in Labelbox.
INTERNAL_PANELS = ("todo", "send", "wait", "rules", "conf")
EXTERNAL_PANELS = ("weighting", "labels", "species", "review",
                   "candidates", "ceiling", "method")

if set(INTERNAL_PANELS) | set(EXTERNAL_PANELS) != set(PANELS):
    raise SystemExit(f"every panel belongs to a page: "
                     f"{sorted(set(PANELS) - set(INTERNAL_PANELS) - set(EXTERNAL_PANELS))} "
                     f"belongs to neither")


def render(c, ids) -> str:
    """The chosen panels, grouped into their sections, in SECTIONS order.

    A section with no chosen panel is not emitted at all, so a page never shows
    a heading and a jump list over nothing.
    """
    unknown = [i for i in ids if i not in PANELS]
    if unknown:
        raise SystemExit(f"no such panel: {unknown}. Known: {sorted(PANELS)}")
    out = []
    for key, (title, lede) in SECTIONS.items():
        chosen = [PANELS[i][1](c) for i in ids if PANELS[i][0] == key]
        if chosen:
            out.append(section(title, lede, "\n".join(chosen)))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The bits of a page that are not a panel: the command line, the document
# wrapper, and writing the file. Both pages do these identically, and a second
# copy is a second place for the verify flags to drift.
# ---------------------------------------------------------------------------

def parse_args(doc: str, default_out: str):
    """The builder command line. Same flags on both pages, different --out."""
    import argparse

    ap = argparse.ArgumentParser(description=doc)
    ap.add_argument("--gt", default=hc.GT_CSV)
    ap.add_argument("--splits", default=hc.SPLITS_CSV)
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument("--verify-against", default=None,
                    help="directory holding the committed measurement CSVs to cross-check; "
                         "defaults to the newest model-health-<date>/ folder")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "build", default_out))
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    return ap.parse_args()


def document(title: str, body: str) -> str:
    """One self-contained file: every style and script inlined, nothing fetched.

    No footer: the subtitle already carries the build date, the snapshot and the
    model tag, and a second copy at the foot said nothing new.
    """
    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title>"
            f"<style>{CSS}</style></head><body>" + body
            + f"<script>{JS}</script></body></html>")


def write_page(page: str, checks, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # Encoded here so the reported size is the size on disk: accented species names
    # cost more than a byte each, and len(page) undercounts by ten.
    blob = page.encode("utf-8")
    with open(out, "wb") as f:
        f.write(blob)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {out}  ({len(blob):,} bytes)")
