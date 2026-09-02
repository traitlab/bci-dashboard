"""Every figure a page shows, computed once off one ``Health``.

One entry point: ``prepare``. Panels read what it returns and do no arithmetic
of their own, so two cannot drift by recomputing the same figure differently.
"""

from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from types import SimpleNamespace

import core as hc
import queues
from history import model_tag_of, snapshot_date_of

# A species is "rarely labelled" below this many frames, and a frame can be
# deprioritised only at or above it. Both read hc.WELL_SAMPLED_MIN_N, so no page
# can disagree with the rule hc.diagnose applied.
RARE_MAX_SUPPORT = hc.WELL_SAMPLED_MIN_N
WAIT_SUPPORT_MIN = hc.WELL_SAMPLED_MIN_N
# The confidence the page recommends is the one the queue applies. Written as
# 0.8 twice, the page could recommend a rule the queue does not implement.
RECOMMENDED_CONF = hc.WAIT_CONF

# The frozen confirmatory read, written by dashboard/score_confirmatory.py. Read
# from the file, never re-scored: bci-dashboard-docs/hypothesis.md says that read
# happens once, on the complete set. Tracked, like the frozen frame list.
CONFIRMATORY_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "input", "confirmatory_result_2026-08.csv")


def is_family(n: str) -> bool:
    """A one-word label ending in -aceae is a family, not a genus (exact: every
    family name carries that suffix). It can never match a predicted genus, so
    scoring it in a genus rate counts a guaranteed miss as measured."""
    return n.strip().lower().endswith("aceae")


def top1(r):
    return r["ranked"][0][0]


def conf(r):
    return r["ranked"][0][1]


def camera_of(key):
    """Which drone camera shot a frame, read off its key: ``zoom`` (wide-angle)
    or ``tele`` (long-lens) in the file name. Counted, not assumed: the two
    populations are not the same one."""
    low = key.lower()
    for c in ("zoom", "tele"):
        if c in low:
            return c
    raise SystemExit(f"frame key names no camera: {key!r}. The camera split "
                     f"below reads the key, so a third camera has to be handled "
                     f"here rather than counted as neither.")


def load_confirmatory(path=CONFIRMATORY_CSV):
    """The frozen confirmatory read as a dict, or None if absent. Numeric values
    come back as floats, the rest as strings. Absent is not an error: a fresh
    clone that has not run the scorer still builds its other page."""
    if not os.path.exists(path):
        return None
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out[row["key"]] = float(row["value"])
            except ValueError:
                out[row["key"]] = row["value"]
    return out


# Both pages state the list length in prose, so it is aliased from core rather
# than restated, like RARE_MAX_SUPPORT above. prepare() checks the cache too.
N_CANDIDATES = hc.N_CANDIDATES


def _rates(sp_recs, per_species):
    """The four corpus rates, and the two counts they are over.
    One question two ways: per species, so a rare one weighs as much as a common
    one, and per frame. Both, because neither alone says how the model does."""
    n, n_sp = len(sp_recs), len(per_species)
    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:N_CANDIDATES]])
    return {
        "n": n, "n_sp": n_sp, "c1": c1,
        "now": {"macro_top1": sum(d["top1_accuracy"] for d in per_species) / n_sp,
                "macro_top5": sum(d["top5_accuracy"] for d in per_species) / n_sp,
                "micro_top1": c1 / n, "micro_top5": c5 / n}}


def _species_status(per_species):
    """How many labels each species has, and the verdict core.diagnose gives it."""
    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    status = {d["species"]: hc.diagnose(d) for d in per_species}
    counts = defaultdict(int)
    for s in status.values():
        counts[s] += 1
    return {"support": support, "status": status, "counts": counts}


def _support_buckets(per_species, sp_recs, support):
    """Frames grouped by how many labels their species has."""
    buckets = {}
    for d in per_species:
        buckets.setdefault(d["support_bucket"],
                           {"n_species": 0, "n_crowns": 0, "c1": 0})["n_species"] += 1
    for r in sp_recs:
        b = buckets[hc.bucket_label(support[r["gt"]])]
        b["n_crowns"] += 1
        b["c1"] += top1(r) == r["gt"]
    return {"buckets": buckets}


def _confidence_bands(sp_recs):
    """How often the first guess is right, by how sure the model was."""
    return {"bins_all": [(f"[{lo:.1f},{min(hi, 1.0):.1f})", len(sub),
                          sum(1 for r in sub if top1(r) == r["gt"]))
                         for lo, hi in hc.CONF_BINS
                         for sub in ([r for r in sp_recs if lo <= conf(r) < hi],)]}


def _out_of_reach(h, sp_recs, per_species):
    """What this evaluation cannot score, and what name matching is worth.
    "Never named" means the species is in no cached candidate list, so no
    threshold scores it. Counted over the evaluated set and over every label,
    and the run log uses the second."""
    never = sorted((d for d in per_species if not d["in_corpus_vocabulary"]),
                   key=lambda d: -d["n_labelled_crowns"])
    never_sp = {d["species"] for d in never}
    reach = [r for r in sp_recs if r["gt"] not in never_sp]
    # Scoring the raw names says what canonicalisation is worth: always a gain.
    strict1 = sum(1 for r in sp_recs
                  if r["ranked_strict"] and r["ranked_strict"][0][0] == r["gt_strict"])
    return {
        "never": never,
        "never_crowns": sum(d["n_labelled_crowns"] for d in never),
        "never_all": (h.tier_crowns["e_absent_from_corpus"]
                      + h.tier_crowns["c_genus_only_in_corpus"]),
        "reach": reach,
        "reach1": sum(1 for r in reach if top1(r) == r["gt"]) / len(reach),
        "unscoreable": len(sp_recs) - len(reach),
        "strict1": strict1,
        "short5": sum(1 for r in sp_recs + h.genus_recs
                      if len(r["ranked"]) < N_CANDIDATES),
        "n_pred": len(sp_recs) + len(h.genus_recs)}


def _queue(h, support, per_species):
    """The send-first queue over the unlabelled pool.
    The ordering lives in ``queues``, and this is the same call measure.py makes,
    so the page and send_first_queue.csv are one list read twice."""
    acc_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    joined_stems = {stem for _, stem, _ in h.joined}
    rows, n_no_answer = queues.send_first_rows(h.predictions, joined_stems,
                                               h.canon, support, acc_of)
    counts = Counter(q for q, _, _, _ in rows)
    return {
        "queue_rows": rows, "queue_counts": counts, "n_no_answer": n_no_answer,
        "n_unlab": sum(counts.values()),
        "lt_species": Counter(pred for q, _, pred, _ in rows if q == "long_tail"),
        "queue_cams": Counter(camera_of(stem) for _, stem, _, _ in rows),
        # In the form send_first_queue.csv writes them, for verify_snapshot.
        "queue_keys": [hc.GT_KEY_PREFIX + stem for _, stem, _, _ in rows]}


def _review(sp_recs):
    """Labels worth a second look: the model is sure and disagrees with the label.
    The same filter as measure.py's label_review_queue.csv, or verify_snapshot
    aborts the build on the count mismatch."""
    confident = [r for r in sp_recs if conf(r) >= hc.REVIEW_CONF]
    raised = [r for r in confident if top1(r) != r["gt"]]
    review = [r for r in raised if r["global_key"] not in hc.adjudicated_keys()]
    pairs = defaultdict(list)
    for r in review:
        pairs[(r["gt"], top1(r))].append(conf(r))
    # The claim the review panel rests on, measured not asserted. Counted over
    # every disagreement, since a confirmed label still leaves the guess wrong.
    hits = len(confident) - len(raised)
    return {"confident": confident, "review": review, "confident_hits": hits,
            "confident_ok": hits / len(confident),
            "n_adjudicated": len(raised) - len(review),
            "review_pairs": pairs, "review_counts": (len(review), len(pairs))}


def _error_by_support(sp_recs, support):
    """Why being sure is not enough: error by labelled frames, at the lowest band
    core.CONF_THRESHOLDS names. The queue page writes this threshold into its own
    column header, so it reads it from here rather than typing it."""
    thr = hc.CONF_THRESHOLDS[0]
    flat = {}
    for r in sp_recs:
        if conf(r) >= thr:
            b = flat.setdefault(hc.bucket_label(support[r["gt"]]), [0, 0])
            b[0] += 1
            b[1] += top1(r) != r["gt"]
    return {"flat": flat, "flat_thr": thr}


def _wait_rules(sp_recs, support):
    """Every queue-ordering rule the page compares, and the one it recommends.
    Which species clear the gate is decided from train frames only, then scored
    on test only, so no rule is graded on the frames that defined it."""
    train_support = defaultdict(int)
    for r in sp_recs:
        if r["split"] == "train":
            train_support[r["gt"]] += 1
    eligible = {s for s, k in train_support.items() if k >= WAIT_SUPPORT_MIN}
    test_recs = [r for r in sp_recs if r["split"] == "test"]
    rare = {s for s, k in support.items() if k < RARE_MAX_SUPPORT}

    rules = [(f"{t} or more sure, any species", t, False)
             for t in hc.CONF_THRESHOLDS[:-1]]
    rules += [(f"{t} or more sure, and the species has at least {WAIT_SUPPORT_MIN} "
               f"labelled frames", t, True) for t in hc.CONF_THRESHOLDS]
    ops = []
    for label, thr, gate in rules:
        wait = [r for r in test_recs if conf(r) >= thr and (not gate or r["gt"] in eligible)]
        ids = {id(r) for r in wait}
        rest = [r for r in test_recs if id(r) not in ids]
        ops.append({"label": label, "thr": thr, "gate": gate, "n": len(wait),
                    "share": len(wait) / len(test_recs) if test_recs else None,
                    "err": sum(1 for r in wait if top1(r) != r["gt"]) / len(wait)
                    if wait else None,
                    "rare": sum(1 for r in wait if r["gt"] in rare),
                    "rare_rest": sum(1 for r in rest if r["gt"] in rare) / len(rest)
                    if rest else None})
    return {
        "eligible": eligible, "test_recs": test_recs, "rare": rare,
        "n_rare_test": sum(1 for r in test_recs if r["gt"] in rare), "ops": ops,
        "best": next(o for o in ops
                     if o["gate"] and abs(o["thr"] - RECOMMENDED_CONF) < 1e-9)}


def _genus_and_family(h):
    """Frames labelled only to genus, and only to family, kept apart."""
    fam_recs = [r for r in h.genus_recs if is_family(r["gt"])]
    gen_recs = [r for r in h.genus_recs if not is_family(r["gt"])]
    # Genus-only frames narrowed to one in-genus candidate: the cheapest
    # confirmation on the page, a yes/no rather than an identification.
    in_gen = [sum(1 for b, _ in r["ranked"][:N_CANDIDATES] if hc.genus_of(b) == r["gt"])
              for r in gen_recs]
    gen_any = sum(1 for k in in_gen if k)
    return {
        "gn": len(gen_recs), "fam_n": len(fam_recs),
        "gg1": sum(1 for r in gen_recs if hc.genus_of(r["ranked"][0][0]) == r["gt"]),
        "fam_names": len({r["gt"] for r in fam_recs}),
        "gen_any": gen_any, "gen_one": sum(1 for k in in_gen if k == 1),
        "gen_none": len(in_gen) - gen_any}


def prepare(h, *, verify_dir, fallback_tag) -> SimpleNamespace:
    """Every figure both pages draw from, computed once off one ``Health``.
    Each helper owns one question and hands back the fields answering it; this
    assembles them into the one object panels read. Read-only for builders except
    ``checks``, filled in by the page after ``history.verify_snapshot`` runs."""
    sp_recs, per_species = h.sp_recs, h.per_species
    longest = max(len(r["ranked"]) for r in sp_recs + h.genus_recs)
    if longest > N_CANDIDATES:
        raise SystemExit(
            f"cached predictions carry up to {longest} names per photo, but every rate\n"
            f"and every sentence on both pages is written for {N_CANDIDATES}. Re-ingest\n"
            f"changed the request setting: update N_CANDIDATES in dashboard/core.py.")

    fig = {"h": h, "sp_recs": sp_recs, "per_species": per_species,
           "n_cand": N_CANDIDATES, "cf": load_confirmatory(), "checks": None,
           "tag": model_tag_of(verify_dir, fallback_tag),
           "snap_date": snapshot_date_of(verify_dir),
           "scored_cams": Counter(camera_of(r["global_key"]) for r in sp_recs),
           # How many scored frames the centre crop mostly misses, split at
           # core.MIN_CROP_COVERAGE rather than a 0.5 typed here.
           "crop_half": len(hc.coverage_split(sp_recs)[1]),
           "crop_none": sum(1 for r in sp_recs
                            if (r.get("crop_coverage") or 0) == 0),
           # Every frame a botanist has labelled at all, whatever rank the name
           # stops at and cached answer or not. The widest of the three counts.
           "n_gt": len(h.gt_rows)}

    fig.update(_rates(sp_recs, per_species))
    fig.update(_species_status(per_species))
    fig.update(_support_buckets(per_species, sp_recs, fig["support"]))
    fig.update(_confidence_bands(sp_recs))
    fig.update(_out_of_reach(h, sp_recs, per_species))
    fig.update(_queue(h, fig["support"], per_species))
    fig.update(_review(sp_recs))
    fig.update(_error_by_support(sp_recs, fig["support"]))
    fig.update(_wait_rules(sp_recs, fig["support"]))
    fig.update(_genus_and_family(h))
    return SimpleNamespace(**fig)
