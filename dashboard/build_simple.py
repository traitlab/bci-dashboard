#!/usr/bin/env python3
"""The short version of the model-health dashboard: one glanceable HTML page.

Companion to build_full.py, not a replacement. The full page carries the reasoning
and the caveats; this page answers the three questions the labelling
programme asks every week, in plain English:

1. How is the model doing right now? (one headline number)
2. Which species need more photos? (the whole species list, three statuses)
3. What do we send the botanist next? (the send-first queues, ordered)

Same data layer (core), same verification gate (history):
every number is recomputed from source and cross-checked against the
committed snapshot CSVs, and a mismatch aborts the build, so the two pages
cannot disagree. Stdlib only, no network, opens from a file:// URL.

    python3 dashboard/build_simple.py [--out PATH]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core as hc  # noqa: E402
from assets import (CSS, JS, cap, esc, filterable_table, funnel_list, info_tip, panel, pctf,
                              status_legend, status_tag, table, threshold_card)  # noqa: E402
from history import (  # noqa: E402
    latest_snapshot_dir, model_tag_of, snapshot_date_of, verify_snapshot)

# The six-way diagnosis from core, collapsed to the three actions this page
# drives. "hard" lands in "send": the labels feed Pl@ntNet's next retraining.
SIMPLE_STATUS = {
    "reliable": ("fine", "Doing fine"),
    "adequate": ("fine", "Doing fine"),
    "ranking": ("send", "Send more photos"),
    "unmeasured": ("send", "Send more photos"),
    "hard": ("send", "Send more photos"),
    "unreachable": ("unreachable", "Never in the 5 guesses"),
}
TAG_CLASS = {"fine": "reliable", "send": "unmeasured", "unreachable": "unreachable"}

# Keyed by the tag drawn, not the six situations behind it: one badge with three
# sentences left no way to tell which applied. Each holds for every situation.
SIMPLE_REASON = {
    "fine": "The first guess is right often enough that extra labels here buy less than "
            "they do elsewhere.",
    "send": "Either too few labelled frames to score, or enough frames and a first guess "
            "that is still weak. More photos are the useful move either way.",
    "unreachable": "It never appears in the five guesses we asked for, so labelling will not "
                   "recover it. Whether Pl@ntNet carries the species at all is not known "
                   "from here.",
}

STATUS_PRIORITY = {"send": 0, "fine": 1, "unreachable": 2}

QUEUE_NAMES = {
    "long_tail": "Species we barely have",
    "low_conf_known": "A usually-right species, guessed weakly",
    "normal": "Everything else",
    "can_wait": "Can wait: confident on a well-covered species",
}

def gt_provenance(gt_csv: str) -> str:
    """One line saying where the ground truth came from.

    The merge script (labelling/gt_from_export.py) writes a sidecar next to the GT at merge time, so
    the page describes the current batch rather than a baked-in one. Without a
    sidecar, fall back to the file's own date: vague, but never stale.
    """
    sidecar = os.path.splitext(gt_csv)[0] + ".provenance.txt"
    if os.path.exists(sidecar):
        with open(sidecar, encoding="utf-8") as f:
            return f.read().strip()
    mtime = _dt.date.fromtimestamp(os.path.getmtime(gt_csv)).isoformat()
    return f"Ground truth: {os.path.basename(gt_csv)}, dated {mtime}."


def build(h, *, generated, verify_dir, fallback_tag, cache_dir, gt_csv):
    sp_recs, per_species = h.sp_recs, h.per_species
    n, n_sp = len(sp_recs), len(per_species)

    c1 = sum(1 for r in sp_recs if r["ranked"][0][0] == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:5]])
    macro1 = sum(d["top1_accuracy"] for d in per_species) / n_sp
    macro5 = sum(d["top5_accuracy"] for d in per_species) / n_sp
    micro1 = c1 / n

    # --- the quantities the verifier holds against the snapshot CSVs.
    # Same formulas as build_full.py; if the two ever drift apart, the
    # snapshot cross-check below is what catches it.
    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    buckets = {}
    for d in per_species:
        buckets.setdefault(d["support_bucket"],
                           dict(n_species=0, n_crowns=0, c1=0))["n_species"] += 1
    for r in sp_recs:
        b = buckets[hc.bucket_label(support[r["gt"]])]
        b["n_crowns"] += 1
        b["c1"] += r["ranked"][0][0] == r["gt"]
    bins_all = [(f"[{lo:.1f},{min(hi, 1.0):.1f})", len(sub),
                 sum(1 for r in sub if r["ranked"][0][0] == r["gt"]))
                for lo, hi in hc.CONF_BINS
                for sub in ([r for r in sp_recs if lo <= r["ranked"][0][1] < hi],)]
    # Accuracy at or above the can-wait confidence threshold, from the same bins.
    hi = [(nn, k) for (band, nn, k), (lo, _) in zip(bins_all, hc.CONF_BINS)
          if lo >= hc.WAIT_CONF - 1e-9]
    conf_n, conf_k = sum(nn for nn, _ in hi), sum(k for _, k in hi)
    conf_acc = conf_k / conf_n if conf_n else None
    never_sp = {d["species"] for d in per_species if not d["in_corpus_vocabulary"]}
    never_all = h.tier_crowns["e_absent_from_corpus"] + h.tier_crowns["c_genus_only_in_corpus"]
    reach = [r for r in sp_recs if r["gt"] not in never_sp]
    strict1 = sum(1 for r in sp_recs
                  if r["ranked_strict"] and r["ranked_strict"][0][0] == r["gt_strict"])

    tag = model_tag_of(verify_dir, fallback_tag)
    snap_date = snapshot_date_of(verify_dir)

    # --- send-first queue over the unlabelled pool (logic lives in core).
    acc_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    joined_stems = {stem for _, stem, _ in h.joined}
    queue_counts = {}
    queue_pressure = defaultdict(int)
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
        if q in ("long_tail", "low_conf_known"):
            queue_pressure[pred] += 1
        if q == "long_tail":
            lt_species[pred] += 1
    n_unlab = sum(queue_counts.values())

    checks = verify_snapshot(
        verify_dir, per_species=per_species, buckets=buckets, bins_all=bins_all,
        never_all=never_all, unscoreable=n - len(reach), strict_hits=strict1,
        queue_counts=queue_counts, n_no_answer=n_no_answer)

    # --- statuses, six-way diagnosis collapsed to three actions ---
    simple = {d["species"]: SIMPLE_STATUS[hc.diagnose(d)] for d in per_species}
    counts = defaultdict(int)
    for key, _ in simple.values():
        counts[key] += 1

    # --- page ---
    P = ['<h1>Pl@ntNet on BCI: how the model is doing</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(snap_date)} &middot; Pl@ntNet model <code>{esc(tag)}</code> '
         f'&middot; {n:,} labelled frames'
         f'{info_tip(f"Photos that carry both a ground-truth species label and a cached "
                     f"Pl@ntNet prediction, so they can be scored. {len(h.gt_rows):,} photos "
                     f"are labelled in total; see \u2018Where these numbers come from\u2019 below "
                     f"for how that splits.")}'
         f' &middot; {n_sp} species</div>',
         '<p class="intro"><b>Send the botanist more photos of the species marked '
         '&ldquo;Send more photos&rdquo; below, starting with the queue in the next '
         'panel.</b></p>',
         f'<p class="terms">A <b>frame</b> is one drone photo. Its label is the species '
         f'whose outlined crowns cover the largest total area in the <i>whole</i> frame. '
         f'The picture sent to Pl@ntNet is the <b>1280&times;1280 centre crop</b>, which is '
         f'13.65% of that frame. The <b>first guess</b> is the top-ranked of the 5 names we '
         f'asked for (<code>nb-results=5</code>, our request parameter, not a model limit). '
         f'Right means it matches the frame’s label.</p>',
         f'<p class="caveat"><strong>These two numbers score a centre crop against a '
         f'whole-frame label.</strong> On 1,377 of 3,777 evaluated records the labelled '
         f'species covers less than half the crop, and on 207 it covers none of it. Read '
         f'them as a provenance record of the centre-crop path, not as the model’s '
         f'accuracy.</p>',
         '<div class="hero">',
         '<div class="metric first">'
         '<div class="e">per species</div>'
         f'<div class="v">{pctf(macro1)}'
         f'{info_tip("Measured over every labelled frame, train and test together, so "
                     "that a species with a handful of labels still appears here. It is "
                     "therefore not a held-out score. The split tags live in "
                     "data/splits.csv and the full page uses them: the can-wait rule is "
                     "set on train frames and graded on test frames only.")}'
         '</div>'
         '<div class="l">First guess is right</div>'
         f'<div class="n">each of the {n_sp} species counts once, however few frames '
         f'it has</div></div>',
         '<div class="metric">'
         '<div class="e">per frame</div>'
         f'<div class="v">{pctf(micro1)}</div>'
         '<div class="l">First guess is right</div>'
         f'<div class="n">one vote per labelled frame ({c1:,} of {n:,}), so common '
         f'species dominate</div></div>',
         '</div>',
         f'<p class="note">Read the two side by side, not as a contradiction. '
         f'<b>Per species</b> is the number to quote for a species picked off the '
         f'checklist; <b>per frame</b> for a photo picked off the drive. Per frame is '
         f'higher because the species with many frames are the ones Pl@ntNet already '
         f'knows.</p>',
         f'<p class="note">Ground truth covers {len(h.gt_rows):,} of '
         f'{len(h.split_rows):,} photos. <strong>{counts["fine"]} species doing fine, '
         f'{counts["send"]} need more photos, {counts["unreachable"]} never turn up in '
         f'the 5-guess list.</strong> That last group is not the same as species '
         f'Pl@ntNet does not carry: we only ever asked for five names, so the two look '
         f'alike from here.</p>'
         f'<p class="note">The right name is somewhere in the 5-guess list for '
         f'<strong>{pctf(macro5)}</strong> of species ({pctf(c5 / n)} of frames), and '
         f'when Pl@ntNet is at least {hc.WAIT_CONF:.0%} confident it is right '
         f'<strong>{pctf(conf_acc)}</strong> of the time ({conf_n:,} frames, '
         f'{pctf(conf_n / n)} of the set).</p>']

    # ---- where the headline numbers come from ----
    gt_date = _dt.date.fromtimestamp(os.path.getmtime(gt_csv)).isoformat()
    funnel_body = funnel_list([
        (len(h.split_rows), "photos in the whole BCI corpus"),
        (len(h.gt_rows), "already carry a ground-truth species label \u2014 every "
                         f"label collected to date, including the {gt_date} "
                         "Labelbox export"),
        (n, "of the labelled photos also have a cached Pl@ntNet prediction \u2014 "
            "every accuracy figure on this page is measured on this set"),
        (n_unlab, "have a prediction but no label yet \u2014 these sit in the "
                  "send-first queue below"),
        (n_no_answer, "got no prediction at all \u2014 check those by eye"),
    ])
    funnel_body += (
        '<p class="note">A Labelbox export only adds or revises some of the photos '
        'above; it does not replace the set. That is why one export\u2019s row count '
        'never matches the corpus, ground-truth, evaluated, or queue counts here: '
        'each of those counts a different thing, not the same thing measured twice.</p>'
        f'<p class="note">Every rate on this page is computed over all labelled frames, '
        f'train and test together, so <b>none of them is a held-out score</b>. That is '
        f'deliberate: holding out would drop the species that have only a few labels, '
        f'which are the ones this page exists to queue. Split tags do exist, in '
        f'<code>data/splits.csv</code> ('
        f'{sum(1 for r in h.sp_recs if r["split"]):,} of {len(h.sp_recs):,} scored frames '
        f'carry one), and the full page uses them to grade the can-wait rule out of '
        f'sample.</p>')
    P.append(panel("Where these numbers come from",
                   "<b>Read this if a count looks off, or before quoting a rate as final.</b>",
                   funnel_body))

    # ---- what to send next ----
    top_lt = sorted(lt_species.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    body = table([("queue", False), ("unlabelled photos", True), ("share", True)],
                 [[f'<strong>{esc(QUEUE_NAMES[q])}</strong>'
                   if q in ("long_tail", "low_conf_known") else esc(QUEUE_NAMES[q]),
                   f'{queue_counts.get(q, 0):,}',
                   pctf(queue_counts.get(q, 0) / n_unlab if n_unlab else None)]
                  for q in hc.QUEUE_ORDER])
    body += (f'<p class="note">&ldquo;Barely have&rdquo; is under {hc.WELL_SAMPLED_MIN_N} '
             f'labelled frames or a first guess right under {hc.HARD_MAX_TOP1:.0%} of the '
             f'time; &ldquo;weakly&rdquo; is confidence under {hc.LOW_CONF:.0%} on a '
             f'species right at least {hc.RELIABLE_MIN_TOP1:.0%} of the time; '
             f'&ldquo;can wait&rdquo; is confidence of {hc.WAIT_CONF:.0%} or more on a '
             f'species with {hc.WELL_SAMPLED_MIN_N} or more labelled frames.</p>')
    body += (f'<p class="note">Most-named species in the first queue: '
             + ", ".join(f'<span class="sp">{esc(cap(s))}</span> ({k:,})' for s, k in top_lt)
             + '.</p>'
             f'<p class="note">The top of <code>send_first_queue.csv</code> in the '
             f'snapshot folder is the next batch, chunked into <code>send_batches.csv</code> '
             f'(whole species groups packed to {hc.BATCH_SIZE} frames a batch, so '
             f'lookalike photos stay together) so it drops '
             f'straight into a Labelbox send. {n_no_answer} photos got no answer at '
             f'all, likely junk; check those by eye.</p>')
    P.append(panel(f"What to send next: {queue_counts.get('long_tail', 0):,} of "
                   f"{n_unlab:,} unlabelled photos point at species we barely have",
                   "<b>Work the queues top to bottom.</b>", body, open_=True))

    # ---- why the "can wait" threshold is safe ----
    P.append(panel("Why this threshold is safe",
                   "<b>Both must be green before a frame can wait.</b>",
                   threshold_card(hc.WAIT_CONF, hc.WELL_SAMPLED_MIN_N), open_=True))

    # ---- the species table ----
    sp_rows, attrs = [], []
    def species_rank(d):
        sp = d["species"]
        action = simple[sp][0]
        if action == "send":
            return (STATUS_PRIORITY[action], -queue_pressure[sp], d["n_labelled_crowns"],
                    d["top1_accuracy"], sp)
        if action == "fine":
            return (STATUS_PRIORITY[action], d["n_labelled_crowns"], -d["top1_accuracy"], sp)
        return (STATUS_PRIORITY[action], d["n_labelled_crowns"], sp)

    for d in sorted(per_species, key=species_rank):
        sp = d["species"]
        key, label = simple[sp]
        sp_rows.append([
            f'<span class="sp" data-sort="{esc(sp)}">{esc(cap(sp))}</span>',
            f'<span data-sort="{d["n_labelled_crowns"]}">{d["n_labelled_crowns"]:,}</span>',
            f'<span data-sort="{d["top1_accuracy"]:.6f}">{pctf(d["top1_accuracy"])}</span>',
            status_tag(TAG_CLASS[key], label, sort_key=label)])
        attrs.append(f' data-species="{esc(sp)}" data-status="{key}"')
    # Six situations, three visible tags, so one legend line per tag drawn. The
    # finer split is on the full page.
    body = (status_legend([(TAG_CLASS[k], SIMPLE_STATUS[o][1], SIMPLE_REASON[k])
                           for o, k in (("reliable", "fine"), ("unmeasured", "send"),
                                        ("unreachable", "unreachable"))])
            + '<p class="note">The default order starts with the species that need work '
              'now.</p>'
            + filterable_table(
        [("Species", False), ("Labelled frames", True),
         ("First guess right", True), ("What to do", False)],
        sp_rows,
        options=[("send", "Send more photos"),
                 ("fine", "Doing fine"),
                 ("unreachable", "Never in the 5 guesses")],
        row_attrs=attrs,
    ))
    # The species count grows with every export, so it cannot decide the anchor.
    P.append(panel(f"All {n_sp} species, priority first",
                   "<b>Click a heading to sort, type to filter.</b>", body, open_=True,
                   anchor="all-species"))

    # ---- provenance, one line ----
    P.append(f'<p class="note">{esc(gt_provenance(gt_csv))} '
             f'{n:,} labelled frames, {n_sp} species; numbers recomputed from source at '
             f'build time.</p>')

    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Pl@ntNet on BCI - how the model is doing</title>"
            f"<style>{CSS}</style></head><body>" + "\n".join(P)
            + f"<script>{JS}</script></body></html>"), checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", default=hc.GT_CSV)
    ap.add_argument("--splits", default=hc.SPLITS_CSV)
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument("--verify-against", default=None,
                    help="snapshot folder to cross-check; defaults to the newest "
                         "model-health-<date>/ folder in the docs repo")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "build",
                                                  "simple_dashboard.html"))
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    args = ap.parse_args()

    h = hc.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=args.verify_against or latest_snapshot_dir(),
                         fallback_tag=args.model_tag, cache_dir=args.cache_dir,
                         gt_csv=args.gt)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    blob = page.encode("utf-8")
    with open(args.out, "wb") as f:
        f.write(blob)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {args.out}  ({len(blob):,} bytes)")


if __name__ == "__main__":
    main()
