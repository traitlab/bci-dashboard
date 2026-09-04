"""Every figure a page shows, computed once off one ``Health``.

One entry point: ``prepare``. Panels read what it returns and do no arithmetic
of their own, so two cannot drift by recomputing the same figure differently.
"""

from __future__ import annotations

import base64
import csv
import os
import statistics
from collections import Counter, defaultdict
from types import SimpleNamespace

import core as hc
import queues
from checklist import load_checklist
# The three arithmetic helpers behind the confusion-matrix rates. They live in
# health.py because that is where the per-species rows are built from the same
# counts, and importing them keeps the corpus figure and the table row from
# being two spellings of one formula.
from health import confidence_spread, confusion_counts, f_measure
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

# The worldwide Pl@ntNet project, read only to say whether a species out of
# scope for hc.EVAL_PROJECT is at least on the global list. Not an evaluation
# project itself: no prediction was ever requested from it.
WORLD_PROJECT = "k-world-flora"


def _rates(sp_recs, per_species):
    """Every corpus rate, and the two counts they are over.
    One question two ways: per species, so a rare one weighs as much as a common
    one, and per frame. Both, because neither alone says how the model does.

    Top-1 and top-5 are accuracy: how often the label is the first guess, and
    how often it is among the names we asked for. Precision, recall and F1 come
    off the same frames through ``health.confusion_counts``, and answer the
    question accuracy cannot: not "how often is the model right" but "when it
    says Terminalia, is it Terminalia".

    Two identities are worth knowing before reading what comes back.

    Per species, recall *is* the first-guess rate. Both count a species' right
    first guesses over its own labelled frames. ``macro_recall`` is computed
    from the confusion counts rather than copied off ``macro_top1``, so the two
    routes can be checked against each other; they must agree.

    Per frame, precision, recall and F1 are one number, and that number is the
    per-frame first-guess rate. Every frame in ``sp_recs`` carries exactly one
    label and exactly one first guess, since ``health.load_health`` admits a
    frame only when it has both, so a wrong guess is one miss for the labelled
    species and one false positive for the guessed one at the same time. The
    two counts are the same count, so their rates are the same rate. It is
    returned once, as ``micro_prf1``, rather than three times.
    """
    n, n_sp = len(sp_recs), len(per_species)
    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:N_CANDIDATES]])
    tp, guessed, labelled = confusion_counts(sp_recs)
    # Averaged over the labelled species, the same population macro_top1 uses,
    # so the two per-species columns are comparable row for row. A species the
    # model only ever guesses wrongly has no row of its own and no recall to
    # average; its guesses are already counted as another species' misses.
    precisions = [(tp[s] / guessed[s]) if guessed[s] else 0.0 for s in labelled]
    recalls = [tp[s] / labelled[s] for s in labelled]
    # F1 per species, then averaged. Averaging first and taking the F1 of the
    # two averages is a different number, and is the way this ships wrong.
    f1s = [f_measure(p, r) for p, r in zip(precisions, recalls)]
    return {
        "n": n, "n_sp": n_sp, "c1": c1,
        "now": {"macro_top1": hc.ratio(sum(d["top1_accuracy"] for d in per_species), n_sp),
                "macro_top5": hc.ratio(sum(d["top5_accuracy"] for d in per_species), n_sp),
                "micro_top1": hc.ratio(c1, n), "micro_top5": hc.ratio(c5, n),
                "macro_precision": hc.ratio(sum(precisions), len(precisions)),
                "macro_recall": hc.ratio(sum(recalls), len(recalls)),
                "macro_f1": hc.ratio(sum(f1s), len(f1s)),
                "micro_prf1": hc.ratio(c1, n)},
        # How many frames the model guessed each labelled species on: the
        # denominator under every per-species precision, carried so a panel can
        # print a rate beside the population it was measured on.
        "n_guessed": {s: guessed[s] for s in labelled}}


def _confidence(sp_recs, per_species):
    """The corpus confidence distribution, and the same for the right guesses.

    The species table has carried a mean since the first build and nothing else.
    A mean is the wrong single figure for this score: Pl@ntNet spreads its
    confidence over every species it knows, so the distribution is skewed and
    the median lands somewhere else. The middle half is carried with it, since
    a median without a spread is one number standing in for a shape again.

    ``when_correct`` is the mean over only the frames the first guess got
    right. ``health.aggregate_per_species`` has computed it per species from
    the beginning and no page has ever shown it; the corpus figure is here so
    one can.
    """
    confs = [conf(r) for r in sp_recs]
    ok = [conf(r) for r in sp_recs if top1(r) == r["gt"]]
    when_correct = [d["mean_top1_confidence_when_correct"] for d in per_species
                    if d["mean_top1_confidence_when_correct"] is not None]
    return {"conf_spread": confidence_spread(confs),
            "conf_spread_correct": confidence_spread(ok),
            "n_conf_correct": len(ok),
            # Per species rather than per frame, so a common species cannot
            # decide it. Only the species that ever get one right have a value.
            "n_species_with_a_right_guess": len(when_correct)}


def _species_status(per_species):
    """How many labels each species has, and the verdict core.diagnose gives it."""
    support = {d["species"]: d["n_labelled_frames"] for d in per_species}
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


def _coverage_sweep(sp_recs, per_species):
    """Accuracy at each crop-coverage bar, the lowest bar included.

    The house rule is that a gated number and its ungated twin are published
    side by side, and ``measure.write_coverage_gate`` already sweeps the bars.
    Recomputed here from the records rather than read back out of that CSV, so
    the page and the file are two counts of one thing and can be caught
    disagreeing.

    ``coverage_dropped`` describes the species the highest bar loses, by how many
    labelled frames each of them has. The per-species rate climbs steeply across
    the sweep and the honest reason is that those species leave, so the panel
    shows how small they are rather than asserting it.
    """
    support = {d["species"]: d["n_labelled_frames"] for d in per_species}
    kept = {r["gt"] for r in hc.coverage_split(sp_recs, hc.CROP_COVERAGE_SWEEP[-1])[0]}
    lowest = {r["gt"] for r in hc.coverage_split(sp_recs, hc.CROP_COVERAGE_SWEEP[0])[0]}
    left = sorted(support.get(sp, 0) for sp in lowest - kept)
    return {"coverage_sweep": [hc.coverage_gate_stats(sp_recs, t)
                               for t in hc.CROP_COVERAGE_SWEEP],
            "coverage_dropped": {"n": len(left),
                                 "max": max(left) if left else None,
                                 "median": statistics.median(left) if left else None}}


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
    and the run log uses the second.

    That population splits into two, when ``core.EVAL_PROJECT``'s checklist is
    on disk: ``out_of_scope`` species are proven absent from Pl@ntNet's own
    list, ``unproven_absent`` ones simply never ranked in an
    ``N_CANDIDATES``-name sample. Without a checklist neither can be told
    apart, so both are empty and ``never`` alone carries the population,
    today's behaviour.
    """
    never = sorted((d for d in per_species if not d["in_corpus_vocabulary"]),
                   key=lambda d: -d["n_labelled_frames"])
    never_sp = {d["species"] for d in never}
    reach = [r for r in sp_recs if r["gt"] not in never_sp]
    # Scoring the raw names says what canonicalisation is worth: always a gain.
    strict1 = sum(1 for r in sp_recs
                  if r["ranked_strict"] and r["ranked_strict"][0][0] == r["gt_strict"])
    has_checklist = h.checklist is not None
    out_of_scope = [d for d in never if d["in_project_checklist"] is False] if has_checklist else []
    unproven_absent = [d for d in never if d not in out_of_scope]
    # Whether the region-only species are at least on the worldwide list, so
    # explain.py can say the regional restriction rather than assume it.
    out_of_scope_in_world = None
    if out_of_scope:
        world = load_checklist(WORLD_PROJECT)
        if world is not None:
            world_canon = world.canon_binomials(h.canon)
            out_of_scope_in_world = sum(1 for d in out_of_scope if d["species"] in world_canon)
    return {
        "never": never,
        "never_frames": sum(d["n_labelled_frames"] for d in never),
        "never_all": (h.tier_crowns["e_absent_from_corpus"]
                      + h.tier_crowns["c_genus_only_in_corpus"]),
        "reach": reach,
        "reach1": hc.ratio(sum(1 for r in reach if top1(r) == r["gt"]), len(reach)),
        "unscoreable": len(sp_recs) - len(reach),
        "strict1": strict1,
        "short5": sum(1 for r in sp_recs + h.genus_recs
                      if len(r["ranked"]) < N_CANDIDATES),
        "n_pred": len(sp_recs) + len(h.genus_recs),
        "has_checklist": has_checklist,
        "out_of_scope": out_of_scope,
        "out_of_scope_frames": sum(d["n_labelled_frames"] for d in out_of_scope),
        "unproven_absent": unproven_absent,
        "unproven_absent_frames": sum(d["n_labelled_frames"] for d in unproven_absent),
        "out_of_scope_in_world": out_of_scope_in_world}


def _queue(h, support, per_species):
    """The send-first queue over the unlabelled pool.
    The ordering lives in ``queues``, and this is the same call measure.py makes,
    so the page and send_first_queue.csv are one list read twice."""
    acc_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    joined_stems = {stem for _, stem, _ in h.joined}
    # The same file measure.py reads, through the same loader. Two readings
    # would order the page and send_first_queue.csv differently, and
    # verify_snapshot aborts the build on the first row where they diverge.
    # `splits` too, for the same reason: the queue holds evaluation frames out,
    # and a page that held out a different set from the CSV would fail
    # history.check_send_batches on the first row where the two diverge.
    rows, n_no_answer, held_out = queues.send_first_rows(
        h.predictions, joined_stems, h.canon, support, acc_of,
        novelty=queues.load_novelty(hc.QUEUE_NOVELTY_CSV), key_prefix=hc.GT_KEY_PREFIX,
        splits=h.split_of)
    counts = Counter(r[0] for r in rows)
    # The batch count the note quotes, from the same call measure.py makes, so
    # the number on the page is the number of batches in send_batches.csv.
    # chunk_send_batches reads send_first_queue.csv rows by position, and these
    # rows are the decision before measure.py gives them their columns, so the
    # three fields it reads are placed by name and the rest left empty.
    at = {c: queues.SEND_FIRST_COLUMNS.index(c)
          for c in ("queue", "global_key", "predicted_species")}
    packable = []
    for q, stem, pred, _conf, _rank in rows:
        row = [""] * len(queues.SEND_FIRST_COLUMNS)
        row[at["queue"]] = q
        row[at["global_key"]] = hc.GT_KEY_PREFIX + stem
        row[at["predicted_species"]] = pred
        packable.append(row)
    batch_rows = queues.chunk_send_batches(packable)
    return {
        "queue_rows": rows, "queue_counts": counts, "n_no_answer": n_no_answer,
        "n_unlab": sum(counts.values()),
        "n_batches": batch_rows[-1][0] if batch_rows else 0,
        # Counted, not assumed to be BATCH_SIZE: packing keeps species groups
        # whole, so a batch stops short whenever the next group would overflow.
        # The internal page leads with this number, so it has to be the real one.
        "n_batch1": sum(1 for b in batch_rows if b[0] == 1),
        "lt_species": Counter(r[2] for r in rows if r[0] == "long_tail"),
        "queue_cams": Counter(camera_of(r[1]) for r in rows),
        # How much of the queue the ordering file reaches. A frame with no
        # vector keeps its old place, so the page must not claim otherwise.
        "n_ranked": sum(1 for r in rows if r[4] != queues.NO_NOVELTY),
        # The evaluation frames the queue refused, by split. The page states
        # this rather than letting the pool quietly come out 44 short.
        "queue_held_out": held_out,
        # In the form send_first_queue.csv writes them, for verify_snapshot.
        "queue_keys": [hc.GT_KEY_PREFIX + r[1] for r in rows]}


def _read_curve(path, columns):
    """A curve file as a list of float tuples, or ``[]`` when it is not there.

    The two curve files are written by hand, outside ``bin/refresh.sh``, so a
    fresh clone has neither. Missing is a normal state and the panel says so; a
    file whose columns have been renamed is not, and raises here rather than
    drawing a chart that is quietly one column short.
    """
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing column(s) {sorted(missing)}")
        return [tuple(float(row[c]) for c in columns) for row in reader]


def _first_reaching(points, level):
    """The x of the first point at or above ``level``, or None if none is.

    Both lines are read against the same level, so this runs twice on the same
    number: how many photos each order needed to reach it.
    """
    for x, y in points:
        if y >= level:
            return x
    return None


def _thumbs(rows, per_queue):
    """Small pictures for the head of each queue, as data: URIs.

    Read off disk and encoded here so the panel does no file work. A frame with
    no thumbnail is dropped rather than drawn as a gap: the fetch is a separate,
    resumable step and a half-finished run must not put holes in the sheet.
    """
    out, seen = defaultdict(list), Counter()
    for q, stem, pred, _conf, _rank in rows:
        if seen[q] >= per_queue:
            continue
        path = os.path.join(hc.THUMB_DIR, f"{hc.GT_KEY_PREFIX}{stem}.jpg")
        if not os.path.exists(path):
            continue
        seen[q] += 1
        with open(path, "rb") as f:
            uri = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
        out[q].append((stem, pred, uri))
    return dict(out)


def _look(rows, queue_cams, n_ranked):
    """What the ordering by look did, in the two shapes a page can show it.

    The discovery curve is scored on the frames that already carry a name, not
    on the queue, so its population is carried alongside it and printed on the
    chart. The novelty curve is the queue itself.
    """
    discovery = _read_curve(hc.DISCOVERY_CURVE_CSV,
                            ("photos_named", "species_directed", "species_random"))
    directed = [(x, y) for x, y, _ in discovery]
    random_order = [(x, z) for x, _, z in discovery]
    half = directed[-1][1] / 2 if directed else 0.0

    novelty = _read_curve(hc.NOVELTY_CURVE_CSV,
                          ("novelty_rank", "mean_distance_to_nearest_labelled"))

    # The frames the ordering puts first, and their cameras. The labelled frames
    # are all one camera, so a photo can read as new because of the lens. The
    # same decile the ranker prints, so the page and the run agree.
    ranked = sorted((r for r in rows if r[4] != queues.NO_NOVELTY), key=lambda r: r[4])
    head = ranked[:max(1, int(n_ranked * hc.QUEUE_HEAD_SHARE))] if ranked else []
    n_queue = sum(queue_cams.values()) or 1
    return {
        "discovery": directed, "discovery_random": random_order,
        "discovery_half": half,
        "discovery_half_directed": _first_reaching(directed, half),
        "discovery_half_random": _first_reaching(random_order, half),
        "discovery_species": directed[-1][1] if directed else 0,
        "discovery_photos": directed[-1][0] if directed else 0,
        "novelty_curve": novelty,
        "head_n": len(head),
        "head_tele": sum(1 for r in head if camera_of(r[1]) == "tele"),
        "head_tele_share": hc.ratio(sum(1 for r in head if camera_of(r[1]) == "tele"),
                                    len(head)),
        "queue_tele_share": hc.ratio(queue_cams.get("tele", 0), n_queue),
        "thumbs": _thumbs(rows, hc.THUMBS_PER_QUEUE)}


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
            # None, not 0.0: with nothing above REVIEW_CONF there is no rate
            # to report, and `pctf` prints "n/a" for it.
            "confident_ok": hc.ratio(hits, len(confident)),
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
    fig.update(_confidence(sp_recs, per_species))
    fig.update(_species_status(per_species))
    fig.update(_support_buckets(per_species, sp_recs, fig["support"]))
    fig.update(_coverage_sweep(sp_recs, per_species))
    fig.update(_confidence_bands(sp_recs))
    fig.update(_out_of_reach(h, sp_recs, per_species))
    fig.update(_queue(h, fig["support"], per_species))
    fig.update(_look(fig["queue_rows"], fig["queue_cams"], fig["n_ranked"]))
    fig.update(_review(sp_recs))
    fig.update(_error_by_support(sp_recs, fig["support"]))
    fig.update(_wait_rules(sp_recs, fig["support"]))
    fig.update(_genus_and_family(h))
    return SimpleNamespace(**fig)
