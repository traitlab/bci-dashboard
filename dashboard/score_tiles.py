"""Does seeing the whole frame beat seeing 13.7% of it?

Compares three predictions of the same frame against the same ground truth:

    photo    the cached centre-crop identify call, one 1280px square
    tiles    the quadrat call, 140 tiles over the whole frame, ranked by the
             share of the frame each species holds
    tiles@crop
             the same tiles, restricted to the tiles whose centre falls inside
             that centre square, ranked by tile count

The third arm is the one that isolates the question. tiles and photo differ in
two ways at once, how much of the frame was seen and how the votes were pooled,
and tiles@crop holds the region fixed so only the pooling changes.

Ground truth is the frame's dominant labelled species, so it describes the
labelled crowns and not the whole frame. A whole-frame arm can therefore be
marked wrong for naming a real tree nobody labelled. That is a ceiling on the
tiles arms, not on the photo arm, and it is why the crop-restricted arm matters.

    python dashboard/score_tiles.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import core                                                   # noqa: E402
import crop_overlap                                           # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]
TILES = REPO / "data" / "tiles" / "cache"
PHOTOS = REPO / "data" / "predictions" / "cache"


def log(msg):
    print(msg, flush=True)


def photo_ranked(base):
    """Centre-crop identify, best species first."""
    path = PHOTOS / f"{base}.json"
    if not path.exists():
        return []
    sp = json.loads(path.read_text()).get("results", {}).get("species", [])
    return [s["binomial"] for s in sorted(sp, key=lambda s: -s["max_score"])
            if s.get("binomial")]


def tiles_ranked(doc):
    """Whole frame, ranked by each species' share of it."""
    sp = doc["results"]["species"]
    return [s["binomial"] for s in sorted(sp, key=lambda s: -s["coverage"])
            if s.get("binomial")]


def tiles_in_rect_ranked(doc, rect):
    """Same tiles, but only those centred inside `rect`, ranked by tile count.

    Coverage is a whole-frame quantity so it cannot be reused here; within a
    region the only signal left is how many tiles each species won, with the
    best tile score breaking ties.
    """
    votes = {}
    for s in doc["results"]["species"]:
        hits = [loc for loc in s["location"]
                if rect[0] <= loc["center"]["x"] <= rect[2]
                and rect[1] <= loc["center"]["y"] <= rect[3]]
        if hits:
            votes[s["binomial"]] = (len(hits), max(h["score"] for h in hits))
    return [k for k, _ in sorted(votes.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))]


def mcnemar_exact(a_only, b_only):
    """Two-sided exact binomial on the discordant pairs."""
    from math import comb
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main():
    if not TILES.exists():
        sys.exit(f"no tiles cache at {TILES}; run predict/tiles.py first")
    frames, _ = crop_overlap.build()
    canon = core.load_wcvp_crosswalk()[0]

    def norm(name):
        n = core.normalize(name or "")
        return canon.get(n, n)

    rows = []
    for path in sorted(TILES.glob("*.json")):
        doc = json.loads(path.read_text())
        base = doc["_base_image"]
        gt = norm(doc["_gt"])
        rect = frames.get(base, {}).get("crop_rect") or crop_overlap.crop_rect()
        rows.append({
            "base": base,
            "gt": gt,
            "photo": [norm(x) for x in photo_ranked(base)],
            "tiles": [norm(x) for x in tiles_ranked(doc)],
            "crop": [norm(x) for x in tiles_in_rect_ranked(doc, rect)],
            "uncovered": doc["results"]["uncovered"],
            "cover": frames.get(base, {}).get("coverage"),
        })
    rows = [r for r in rows if r["gt"] and r["photo"]]
    log(f"frames scorable in all arms: {len(rows)}\n")

    arms = ["photo", "tiles", "crop"]
    for k in (1, 5):
        log(f"top-{k}")
        for a in arms:
            hit = sum(1 for r in rows if r["gt"] in r[a][:k])
            log(f"  {a:6s} {hit / len(rows) * 100:5.1f}%  ({hit}/{len(rows)})")
        for a in arms[1:]:
            ao = sum(1 for r in rows
                     if r["gt"] in r[a][:k] and r["gt"] not in r["photo"][:k])
            bo = sum(1 for r in rows
                     if r["gt"] not in r[a][:k] and r["gt"] in r["photo"][:k])
            log(f"  {a} vs photo: {a}-only {ao}, photo-only {bo}, "
                f"exact p={mcnemar_exact(ao, bo):.4f}")
        log("")

    # The gate the dashboard publishes selects frames where one species fills
    # the centre square. If tiles only wins on frames the gate already admits,
    # it buys nothing the gate does not.
    admitted = [r for r in rows if (r["cover"] or 0) >= 0.50]
    rejected = [r for r in rows if (r["cover"] or 0) < 0.50]
    log(f"split by the published coverage gate (T=0.50)")
    for label, sub in (("admitted", admitted), ("not admitted", rejected)):
        if not sub:
            continue
        line = "  ".join(
            f"{a}={sum(1 for r in sub if r['gt'] == r[a][:1][0] if r[a]) / len(sub) * 100:5.1f}%"
            for a in arms)
        log(f"  {label:13s} n={len(sub):4d}  {line}")


if __name__ == "__main__":
    main()
