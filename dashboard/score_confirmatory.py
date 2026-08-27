"""Score the frozen 300 under the design committed in bci-dashboard-docs/hypothesis.md.

Two arms, one label, two regions:

    crown   one identify call per labelled crown, aggregated to the frame
    photo   the 1280 px centre square, 13.65% of the frame, carried as the
            legacy reference and never described as region-aligned

Ground truth names the species whose labelled crowns hold the largest summed
raw box area over the whole frame. The crown rule below mirrors that criterion
at its own unit; the photo rule does not, which is the defect the experiment
exists to measure.

A third arm, tiles, was frozen alongside these two and dropped on 2026-08-27,
before any confirmatory read. bci-dashboard-docs/hypothesis.md carries the
reasons as deviation A4. P1 and P4 named tiles and die with it, so P3, crown
beats photo, is the primary prediction from here.

Nothing here chooses anything. Every rule, every threshold, the cluster unit,
the test and the stopping rule were fixed in bci-dashboard-docs/hypothesis.md before the data
existed. This file only applies them. If the region-aligned arm is missing a
frozen frame the report is stamped EXPLORATORY, because the stopping rule says
the confirmatory read happens once, on the complete set.

    python dashboard/score_confirmatory.py
    python dashboard/score_confirmatory.py --adjudication out.csv
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
    """The same normalisation the dashboard already applies, as one callable."""
    crosswalk, _ = core.load_wcvp_crosswalk(core.WCVP_CACHE_JSON)

    def canon(name):
        n = core.normalize(name or "")
        return crosswalk.get(n, n)

    return canon


# --- the two aggregation rules, as committed -------------------------------

def rank_crowns(crowns):
    """Frame prediction from crowns: each crown votes its own raw box area.

    Ground truth is summed raw box area over the frame, so a crown arm that
    pooled by crown count or by mean score would be answering a different
    question than the label asks. `crowns` is a list of (area, top1, score).
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
    """One row per frozen frame, with each arm's ranking and the frame's shape."""
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
            1.0, sum((b[2] - b[0]) * (b[3] - b[1]) for b in big) / (4000 * 3000))
        row["gt_area"] = min(1.0, sum(
            (b[2] - b[0]) * (b[3] - b[1]) for b in big if canon(b[4]) == gt)
            / (4000 * 3000))

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
    """Percentile interval, resampling whole clusters with replacement.

    Eleven or twelve sites is too few for a sandwich estimator to be trusted,
    which is why the interval is a bootstrap and why the cluster is the site
    rather than the flight day: a day is a mission at one site, so the site is
    the coarser unit and the more conservative choice.
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
    """Two-sided cluster bootstrap p for the paired accuracy difference.

    The exact McNemar assumes independent pairs and these pairs are clustered,
    so this is the pre-specified sensitivity. The p value is the share of
    resamples whose difference has the opposite sign to the observed one,
    doubled, which is the usual percentile inversion.
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

def report(rows, missing, complete, draws=BOOTSTRAP_DRAWS):
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

    log("primary endpoint: frame-level top-1 accuracy, and top-5")
    log(f"  {'arm':7} {'n':>4}  {'top-1':>6}  {'95% CI by site':>16}  "
        f"{'by day':>16}  {'Wilson':>16}  {'top-5':>6}")
    for a in ARMS:
        scorable = [r for r in rows if r[a] is not None]
        if not scorable:
            log(f"  {a:7} {'0':>4}  no data")
            continue
        acc = accuracy(scorable, a)
        hits = sum(hit(r, a) for r in scorable)
        def acc_of(sample, arm=a):
            return accuracy(sample, arm)

        s_lo, s_hi = cluster_bootstrap(scorable, "site", acc_of, draws)
        d_lo, d_hi = cluster_bootstrap(scorable, "day", acc_of, draws)
        w_lo, w_hi = wilson(hits, len(scorable))
        log(f"  {a:7} {len(scorable):4d}  {acc:6.1%}  "
            f"[{s_lo:6.1%},{s_hi:6.1%}]  [{d_lo:6.1%},{d_hi:6.1%}]  "
            f"[{w_lo:6.1%},{w_hi:6.1%}]  {accuracy(scorable, a, 5):6.1%}")
    log("  Wilson is the unclustered interval the page already publishes. It is")
    log("  too narrow here, and is shown so the cost of clustering is visible.")
    log("  crown top-5 is bounded by the number of distinct species its crowns")
    log("  name, which is usually fewer than five, so it is not comparable.")
    log("")

    log("P3, primary since tiles was dropped: crown against photo, paired on")
    log("    the frame. The test, the cluster unit and the tie-break are the ones")
    log("    P1 was to be read with; only the second arm changed.")
    pairs, crown_only, photo_only = discordance(rows, "crown", "photo")
    p_exact = mcnemar_exact(crown_only, photo_only)
    log(f"  pairs {pairs}, crown-only {crown_only}, photo-only {photo_only}")
    log(f"  exact McNemar, two-sided        p = {p_exact:.5f}")
    p_boot, band = bootstrap_p(rows, "crown", "photo", "site", draws)
    if band:
        d, lo, hi = band
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
        scorable = [r for r in rows if r[a] is not None]
        if not scorable:
            continue
        lo, _ = cluster_bootstrap(scorable, "site",
                                  lambda x, arm=a: accuracy(x, arm), draws)
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


def write_adjudication(rows, path, seed=SEED):
    """Phase 5: the disagreements, with the arm labels hidden.

    An adjudicator who can see which arm said what will find the arm they
    expect to win. The two answers are written as A and B in an order drawn per
    frame from the seed, and the key goes to a separate file that is not opened
    until every verdict is in.
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
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frozen", type=pathlib.Path, default=FROZEN)
    ap.add_argument("--adjudication", type=pathlib.Path,
                    help="write the blind adjudication sheet here")
    ap.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS)
    args = ap.parse_args(argv)

    frozen = load_frozen(args.frozen)
    canon = canonicaliser()
    rows, missing = build_rows(frozen, load_boxes(), canon)
    complete = not any(missing[a] for a in ALIGNED)
    report(rows, missing, complete, args.draws)
    if args.adjudication:
        if not complete:
            log("\nrefusing to write the adjudication sheet: the set is not "
                "complete, so the disagreements are not the final ones")
            return 1
        write_adjudication(rows, args.adjudication)
    return 0


if __name__ == "__main__":
    sys.exit(main())
