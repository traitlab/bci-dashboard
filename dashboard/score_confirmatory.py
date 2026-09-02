"""Score the frozen 300 under the design committed in bci-dashboard-docs/hypothesis.md.

Two arms, one label:

    crown   one identify call per labelled crown, aggregated to the frame
    photo   the centre square crop_overlap.CROP_SIZE names, the legacy reference

The label names the species whose crowns hold the largest summed box area over
the frame. The crown rule mirrors that criterion at its own unit and the photo
rule does not, which is the gap the experiment measures. A third arm, tiles, was
dropped before any read (deviation A4), taking P1 and P4 with it and leaving P3,
crown beats photo, as the primary prediction.

Nothing here chooses anything: hypothesis.md fixed every rule, cluster unit, test
and stopping rule before the data existed. A crown arm missing a frozen frame
stamps the report EXPLORATORY, because the stopping rule allows one read on the
complete set.

    python dashboard/score_confirmatory.py [--adjudication out.csv] [--out CSV]

``--out`` writes the numbers the external page publishes. The page reads that
file rather than re-running this script: a number that moved because a page was
rebuilt would not be a confirmatory number.
"""

import argparse
import csv
import json
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import core
from crop_overlap import CROP_SIZE, FRAME_H, FRAME_W

# The frame is a fixed size across the corpus, and crop_overlap is where that
# is written down and checked. Typed here as 4000 * 3000 it was a second copy
# in the one script whose numbers are frozen and never recomputed.
FRAME_AREA = FRAME_W * FRAME_H

REPO = pathlib.Path(__file__).resolve().parents[1]
FROZEN = REPO / "input" / "confirmatory_frames_2026-08.csv"
BOXES = REPO / "data" / "export_boxes.csv"
CROWNS = REPO / "data" / "crowns_export" / "cache"
PHOTOS = REPO / "data" / "predictions" / "cache"

ARMS = ("crown", "photo")
ALIGNED = ("crown",)
BOOTSTRAP_DRAWS = 10000
SEED = 20260826
MIN_BOX_SIDE = 128


def log(msg=""):
    print(msg, flush=True)


# --- names -------------------------------------------------------------------

def canonicaliser():
    """The dashboard's own normalisation, over the cached crosswalk."""
    crosswalk, _ = core.load_wcvp_crosswalk(core.WCVP_CACHE_JSON)
    return core.canonicaliser(crosswalk)


# --- the two aggregation rules, as committed -------------------------------

def rank_crowns(crowns):
    """Frame prediction from crowns: each votes its raw box area, matching
    ground truth (not crown count or mean score). ``crowns``: (area, top1,
    score).
    """
    vote, best = {}, {}
    for area, top1, score in crowns:
        if not top1:
            continue
        vote[top1] = vote.get(top1, 0) + area
        best[top1] = max(best.get(top1, 0.0), score)
    return sorted(vote, key=lambda s: (-vote[s], -best[s], s))


def rank_photo(doc):
    """Centre-crop identify, highest max_score first. Unchanged from the page."""
    sp = [s for s in doc.get("results", {}).get("species", []) if s.get("binomial")]
    sp.sort(key=lambda s: (-s.get("max_score", 0.0), s["binomial"]))
    return [s["binomial"] for s in sp]


# --- loading -----------------------------------------------------------------

def load_frozen(path=FROZEN):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_boxes(path=BOXES):
    """base_image -> list of (x0, y0, x1, y1, label), duplicates collapsed."""
    out, seen = {}, set()
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            box = (int(r["x_min"]), int(r["y_min"]), int(r["x_max"]), int(r["y_max"]))
            key = (r["base_image"], box)
            if key in seen:
                continue
            seen.add(key)
            out.setdefault(r["base_image"], []).append(box + (r["lb_label"],))
    return out


def crown_id(base_image, box):
    stem = base_image[:-4] if base_image.lower().endswith(".jpg") else base_image
    return f"{stem}__{box[0]}_{box[1]}_{box[2]}_{box[3]}"


def build_rows(frozen, boxes, canon):
    """One row per frozen frame: each arm's ranking, the frame's shape."""
    rows, missing = [], {a: [] for a in ARMS}
    for f in frozen:
        base, gt = f["base_image"], canon(f["gt_species"])
        row = {"base": base, "gt": gt, "site": f["site"], "day": f["flight_day"]}

        photo_doc = PHOTOS / f"{base}.json"
        row["photo"] = ([canon(x) for x in rank_photo(json.loads(photo_doc.read_text()))]
                        if photo_doc.exists() else None)

        big = [b for b in boxes.get(base, [])
               if (b[2] - b[0]) >= MIN_BOX_SIDE and (b[3] - b[1]) >= MIN_BOX_SIDE]
        votes, absent = [], 0
        for b in big:
            path = CROWNS / f"{crown_id(base, b[:4])}.json"
            if not path.exists():
                absent += 1
                continue
            doc = json.loads(path.read_text())
            res = doc.get("results") or []
            top = res[0] if res else {}
            votes.append(((b[2] - b[0]) * (b[3] - b[1]),
                          canon(top.get("scientific_name")),
                          top.get("score", 0.0)))
        row["crown"] = [x for x in rank_crowns(votes)] if votes and not absent else None
        row["n_crowns"] = len(big)
        # How much of the frame the labelled crowns cover at all. Kept as a
        # descriptive column; the prediction that read it, P4, named tiles.
        row["labelled_area"] = min(
            1.0, sum((b[2] - b[0]) * (b[3] - b[1]) for b in big) / FRAME_AREA)
        row["gt_area"] = min(1.0, sum(
            (b[2] - b[0]) * (b[3] - b[1]) for b in big if canon(b[4]) == gt)
            / FRAME_AREA)

        for a in ARMS:
            if row[a] is None:
                missing[a].append(base)
        rows.append(row)
    return rows, missing


# --- statistics --------------------------------------------------------------

def hit(row, arm, k=1):
    return bool(row[arm]) and row["gt"] in row[arm][:k]


def wilson(hits, n, z=1.96):
    """The interval the page already uses. Too narrow here, reported anyway."""
    if not n:
        return (0.0, 0.0)
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_bootstrap(rows, unit, statistic, draws=BOOTSTRAP_DRAWS, seed=SEED):
    """Percentile interval, resampling whole clusters with replacement. Too
    few sites (11-12) to trust a sandwich estimator. Cluster is site, not
    day: a day is one mission at one site.
    """
    groups = {}
    for r in rows:
        groups.setdefault(r[unit], []).append(r)
    keys = sorted(groups)
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        sample = []
        for _ in keys:
            sample += groups[keys[rng.randrange(len(keys))]]
        value = statistic(sample)
        if value is not None:
            out.append(value)
    out.sort()
    if not out:
        return (0.0, 0.0)
    return (out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))])


def accuracy(rows, arm, k=1):
    scorable = [r for r in rows if r[arm] is not None]
    if not scorable:
        return None
    return sum(hit(r, arm, k) for r in scorable) / len(scorable)


def mcnemar_exact(a_only, b_only):
    """Two-sided exact binomial on the discordant pairs, p = 0.5."""
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def discordance(rows, a, b, k=1):
    pairs = [r for r in rows if r[a] is not None and r[b] is not None]
    a_only = sum(1 for r in pairs if hit(r, a, k) and not hit(r, b, k))
    b_only = sum(1 for r in pairs if hit(r, b, k) and not hit(r, a, k))
    return len(pairs), a_only, b_only


def bootstrap_p(rows, a, b, unit, draws=BOOTSTRAP_DRAWS, seed=SEED):
    """Two-sided cluster bootstrap p: the pre-specified check, since exact
    McNemar assumes independent pairs and these are clustered. p is the
    doubled share of resamples opposite in sign to observed.
    """
    pairs = [r for r in rows if r[a] is not None and r[b] is not None]
    if not pairs:
        return None, None
    observed = accuracy(pairs, a) - accuracy(pairs, b)

    def diff(sample):
        if not sample:
            return None
        return accuracy(sample, a) - accuracy(sample, b)

    lo, hi = cluster_bootstrap(pairs, unit, diff, draws, seed)
    groups = {}
    for r in pairs:
        groups.setdefault(r[unit], []).append(r)
    keys = sorted(groups)
    rng = random.Random(seed)
    crossed = 0
    for _ in range(draws):
        sample = []
        for _ in keys:
            sample += groups[keys[rng.randrange(len(keys))]]
        d = diff(sample)
        if d is not None and (d <= 0 if observed > 0 else d >= 0):
            crossed += 1
    return min(1.0, 2 * crossed / draws), (observed, lo, hi)


# --- report ------------------------------------------------------------------

def report(rows, missing, complete, stat, draws=BOOTSTRAP_DRAWS):
    """The run log: every number printed is the number ``result_rows``
    (``stat``) publishes, not a resample."""
    n = len(rows)
    stamp = "CONFIRMATORY" if complete else "EXPLORATORY"
    log(f"=== {stamp} read of the frozen {n} ===")
    if not complete:
        log("  The stopping rule says the confirmatory read happens once, on the")
        log("  complete set. It is not complete, so nothing below may be published")
        log("  as a confirmatory result.")
    for a in ARMS:
        if missing[a]:
            log(f"  {a:6s} missing {len(missing[a])} frames, "
                f"e.g. {missing[a][0]}")
    log("")

    # The list length is core's, not a 5 typed here: the same constant decides
    # how many names were asked for and how wide the last column is named.
    top_n = f"top-{core.N_CANDIDATES}"
    log(f"primary endpoint: frame-level top-1 accuracy, and {top_n}")
    log(f"  {'arm':7} {'n':>4}  {'top-1':>6}  {'95% CI by site':>16}  "
        f"{'by day':>16}  {'Wilson':>16}  {top_n:>6}")
    for a in ARMS:
        scorable = [r for r in rows if r[a] is not None]
        if not scorable:
            log(f"  {a:7} {'0':>4}  no data")
            continue
        acc = stat[f"{a}_top1"]
        # The day-clustered interval is the one number here that no published
        # row carries, so it is the only bootstrap this function still runs.
        d_lo, d_hi = cluster_bootstrap(
            scorable, "day", lambda x, arm=a: accuracy(x, arm), draws)
        s_lo, s_hi = stat[f"{a}_top1_site_lo"], stat[f"{a}_top1_site_hi"]
        w_lo, w_hi = stat[f"{a}_top1_wilson_lo"], stat[f"{a}_top1_wilson_hi"]
        log(f"  {a:7} {len(scorable):4d}  {acc:6.1%}  "
            f"[{s_lo:6.1%},{s_hi:6.1%}]  [{d_lo:6.1%},{d_hi:6.1%}]  "
            f"[{w_lo:6.1%},{w_hi:6.1%}]  {stat[f'{a}_top5']:6.1%}")
    log("  Wilson is the unclustered interval the page already publishes. It is")
    log("  too narrow here, and is shown so the cost of clustering is visible.")
    log("  crown right-name-in-list is bounded by the number of distinct species")
    log(f"  its crowns name, usually fewer than {core.N_CANDIDATES}, so it is not comparable.")
    log("")

    log("P3, primary since tiles was dropped: crown against photo, paired on")
    log("    the frame. The test, the cluster unit and the tie-break are the ones")
    log("    P1 was to be read with; only the second arm changed.")
    log(f"  pairs {stat['paired_n']}, crown-only {stat['crown_only_hits']}, "
        f"photo-only {stat['photo_only_hits']}")
    log(f"  exact McNemar, two-sided        p = {stat['p_mcnemar_exact']:.5f}")
    if "crown_minus_photo" in stat:
        d = stat["crown_minus_photo"]
        lo, hi = stat["crown_minus_photo_site_lo"], stat["crown_minus_photo_site_hi"]
        p_boot = stat["p_cluster_bootstrap"]
        log(f"  difference                      {d:+.1%} "
            f"[{lo:+.1%}, {hi:+.1%}] clustered on site")
        log(f"  cluster bootstrap, two-sided    p = {p_boot:.5f}")
        verdict = "supported" if (p_boot < 0.05 and d > 0) else "not supported"
        log(f"  P3 (crown beats photo) is {verdict} at alpha = 0.05, reading the")
        log("  cluster bootstrap, which is the pre-specified answer when the two")
        log("  tests disagree.")
    log("")

    log("P2: the region-aligned arm beats 50% top-1")
    for a in ALIGNED:
        if f"{a}_top1_site_lo" not in stat:
            continue
        lo = stat[f"{a}_top1_site_lo"]
        log(f"  {a:6} lower bound of the site-clustered interval {lo:6.1%}  "
            f"{'beats' if lo > 0.5 else 'does not beat'} 50%")
    log("")

    log("P4 compared tiles against crown by how much of the frame the labelled")
    log("    crowns cover. It is not readable without the tiles arm and is not")
    log("    reported. See deviation A4.")
    log("")

    log("descriptive: what the label had to work with")
    if rows:
        gt_zero = sum(1 for r in rows if r["gt_area"] == 0)
        log(f"  frames where no labelled crown carries the GT species: {gt_zero}")
        log(f"  median labelled area share of the frame: "
            f"{sorted(r['labelled_area'] for r in rows)[len(rows) // 2]:.1%}")
        log(f"  median crowns per frame: "
            f"{sorted(r['n_crowns'] for r in rows)[len(rows) // 2]}")
    return {"complete": complete, "n": n}


def result_rows(rows, complete, draws=BOOTSTRAP_DRAWS):
    """The published numbers as ordered (key, value) pairs. Long format: the
    paired comparison belongs to neither arm, avoiding an average of two
    copies of it.
    """
    # Composition, not a result: a rate over 300 frames is weighted by whatever
    # those frames happen to hold, and a page that prints the rate without the
    # weighting invites the same per-frame-average mistake the dashboard already
    # argues against for the corpus numbers.
    by_species = {}
    for r in rows:
        by_species[r["gt"]] = by_species.get(r["gt"], 0) + 1
    top2 = sum(sorted(by_species.values(), reverse=True)[:2])
    cameras = sorted({("tele" if "tele" in r["base"].lower() else
                       "zoom" if "zoom" in r["base"].lower() else "unknown")
                      for r in rows})
    out = [("stamp", "CONFIRMATORY" if complete else "EXPLORATORY"),
           ("n_frames", len(rows)),
           ("n_sites", len({r["site"] for r in rows})),
           ("n_days", len({r["day"] for r in rows})),
           ("n_species", len(by_species)),
           ("top2_species_share", top2 / len(rows) if rows else 0.0),
           ("cameras", "+".join(cameras)),
           ("bootstrap_draws", draws),
           ("bootstrap_seed", SEED)]
    for a in ARMS:
        scorable = [r for r in rows if r[a] is not None]
        if not scorable:
            continue

        def acc_of(sample, arm=a):
            return accuracy(sample, arm)

        hits = sum(hit(r, a) for r in scorable)
        s_lo, s_hi = cluster_bootstrap(scorable, "site", acc_of, draws)
        w_lo, w_hi = wilson(hits, len(scorable))
        out += [(f"{a}_n", len(scorable)), (f"{a}_hits", hits),
                (f"{a}_top1", accuracy(scorable, a)),
                (f"{a}_top1_site_lo", s_lo), (f"{a}_top1_site_hi", s_hi),
                (f"{a}_top1_wilson_lo", w_lo), (f"{a}_top1_wilson_hi", w_hi),
                (f"{a}_top5", accuracy(scorable, a, core.N_CANDIDATES))]

    pairs, crown_only, photo_only = discordance(rows, "crown", "photo")
    p_boot, band = bootstrap_p(rows, "crown", "photo", "site", draws)
    out += [("paired_n", pairs), ("crown_only_hits", crown_only),
            ("photo_only_hits", photo_only),
            ("p_mcnemar_exact", mcnemar_exact(crown_only, photo_only))]
    if band:
        d, lo, hi = band
        out += [("crown_minus_photo", d), ("crown_minus_photo_site_lo", lo),
                ("crown_minus_photo_site_hi", hi), ("p_cluster_bootstrap", p_boot)]
    return out


def write_result(pairs, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["key", "value"])
        for k, v in pairs:
            w.writerow([k, f"{v:.6f}" if isinstance(v, float) else v])
    log(f"wrote {path}")


def write_adjudication(rows, path, seed=SEED):
    """Phase 5: disagreements, arm labels hidden so an adjudicator cannot
    favor the arm they expect to win. A/B order is drawn per frame from
    the seed; the key file stays closed until every verdict is in.
    """
    rng = random.Random(f"{seed}:adjudication")
    both = [r for r in rows if r["crown"] is not None and r["photo"] is not None]
    disagree = [r for r in both if (r["crown"][:1] or [None]) != (r["photo"][:1] or [None])]
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key_path = path.with_name(path.stem + "_key.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh, \
            open(key_path, "w", newline="", encoding="utf-8") as kh:
        w = csv.writer(fh, lineterminator="\n")
        k = csv.writer(kh, lineterminator="\n")
        w.writerow(["base_image", "ground_truth", "answer_A", "answer_B",
                    "verdict_A_correct", "verdict_B_correct", "notes"])
        k.writerow(["base_image", "answer_A_arm", "answer_B_arm"])
        for r in sorted(disagree, key=lambda r: r["base"]):
            a, b = ("crown", "photo") if rng.random() < 0.5 else ("photo", "crown")
            w.writerow([r["base"], r["gt"], r[a][0], r[b][0], "", "", ""])
            k.writerow([r["base"], a, b])
    log(f"wrote {path} with {len(disagree)} disagreements, "
        f"and the arm key to {key_path}")
    log("Do not open the key until every verdict column is filled in.")
    return len(disagree)


def main(argv=None):
    ap = argparse.ArgumentParser(description=core.summarise(__doc__))
    ap.add_argument("--frozen", type=pathlib.Path, default=FROZEN,
                    help="the list of frames frozen before the numbers existed")
    ap.add_argument("--adjudication", type=pathlib.Path,
                    help="write the blind adjudication sheet here")
    ap.add_argument("--out", type=pathlib.Path,
                    help="write the published numbers here as key,value rows")
    ap.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS,
                    help=f"how many times to re-run the count for the range "
                         f"(default: {BOOTSTRAP_DRAWS:,})")
    args = ap.parse_args(argv)

    frozen = load_frozen(args.frozen)
    canon = canonicaliser()
    rows, missing = build_rows(frozen, load_boxes(), canon)
    complete = not any(missing[a] for a in ALIGNED)
    published = result_rows(rows, complete, args.draws)
    report(rows, missing, complete, dict(published), args.draws)
    if args.out:
        write_result(published, args.out)
    if args.adjudication:
        if not complete:
            log("\nrefusing to write the adjudication sheet: the set is not "
                "complete, so the disagreements are not the final ones")
            return 1
        write_adjudication(rows, args.adjudication)
    return 0


if __name__ == "__main__":
    sys.exit(main())
