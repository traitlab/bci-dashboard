"""Draw the frozen frame list for the confirmatory region-aligned evaluation.

Earlier published numbers drew their frames after the fact. This script draws
them from a seed and commits the list before any API call, so re-running it
reproduces the list byte for byte. That is what makes the later comparison
confirmatory rather than exploratory.

A frame is eligible only if both arms can score it against the same label: a
species-level ground truth, a frame URL, an existing centre-crop prediction,
no tiles cache entry (the 146 frames fetched earlier have been seen), and a
labelled crown at least MIN_BOX_SIDE px on both sides in `data/export_boxes.csv`.
That file is the July 2026 botanist revision, which defines the label; the
tracked 2024 file holds three times as many boxes, and a crown cut from a
different revision is not aligned with the label it is scored against.

The pool gets its own committed manifest, because eligibility reads live caches
and the fetch this draw authorises fills one of them. --verify redraws from the
manifest rather than re-deriving the pool, which would fail the moment fetching
began.

Frames are not independent draws: 40 flight days and 12 sites carry them, and
one site holds 26.3% of the pool. The draw is proportional to site, capped at
CAP of the sample so no single plot carries the headline. What a capped site
sheds is spread over the uncapped ones to a fixed point, then rounded by
largest remainder.

    python predict/draw_confirmatory.py --rebuild-pool   # derive the pool, report
    python predict/draw_confirmatory.py --rebuild-pool --write
    python predict/draw_confirmatory.py --verify         # redraw from the manifest
"""

import argparse
import csv
import hashlib
import importlib.util
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "input" / "confirmatory_frames_2026-08.csv"
POOL = REPO / "input" / "confirmatory_pool_2026-08.csv"

N = 300
SEED = 20260826
CAP = 0.25
MIN_BOX_SIDE = 128

# The box export the ground truth is computed from (labelling/gt_from_export.py),
# not the tracked 2024 file crown.py defaults to.
BOXES_CSV = REPO / "data" / "export_boxes.csv"

PHOTO_CACHE = REPO / "data" / "predictions" / "cache"
TILES_CACHE = REPO / "data" / "tiles" / "cache"

# Mission folders are named <yyyymmdd>_<site>_<waypoint>_<aircraft>. The folder
# is in the frame URL for every eligible frame, and in the dataset inventory for
# only half of them, so the URL is the source that covers the population.
MISSION_RE = re.compile(r"/(\d{8})_([a-z0-9]+)_")
DAY_RE = re.compile(r"DJI_(\d{8})")

FIELDS = ["base_image", "site", "flight_day", "gt_species", "n_crowns"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # a @dataclass in core.py needs this
    spec.loader.exec_module(mod)
    return mod


def site_of(url):
    m = MISSION_RE.search(url or "")
    return m.group(2) if m else ""


def day_of(base):
    m = DAY_RE.search(base or "")
    return m.group(1) if m else ""


def eligible(core, crown):
    """Derive the draw pool from the live caches. Run once, at freeze time.

    Everything afterwards reads the committed manifest instead, because the
    per-photo fetch fills the tiles cache this function reads.
    """
    gt, _ = crown.frame_gt_map(core)
    urls = crown.load_frame_urls()
    boxes, _ = crown.load_crowns(BOXES_CSV)
    pool = []
    for base in sorted(gt):
        url = urls.get(base)
        if not url:
            continue
        if not (PHOTO_CACHE / f"{base}.json").exists():
            continue
        if (TILES_CACHE / f"{base}.json").exists():
            continue
        big = [b for b in boxes.get(base, [])
               if (b[2] - b[0]) >= MIN_BOX_SIDE and (b[3] - b[1]) >= MIN_BOX_SIDE]
        if not big:
            continue
        site = site_of(url)
        if not site:
            continue
        pool.append({"base_image": base, "site": site, "flight_day": day_of(base),
                     "gt_species": gt[base], "n_crowns": len(big)})
    return pool


def allocate(sizes, n, cap):
    """How many frames each site contributes: proportional, then capped.

    No site may give more than `cap` of the sample or more frames than it holds,
    whichever is smaller. A capped site sheds its excess to the uncapped ones in
    proportion to their own sizes, which can push another site over its own
    ceiling, so the redistribution runs to a fixed point. What is left after the
    proportional split is handed out by largest remainder, and a site that is
    already at its ceiling is skipped rather than pushed past it.

    Raises when the ceilings cannot reach `n` at all, because silently
    returning a smaller sample would make the frozen list disagree with the
    hypothesis that names its size.
    """
    ceiling = {s: min(sizes[s], int(cap * n)) for s in sizes}
    if sum(ceiling.values()) < n:
        raise ValueError(f"a cap of {cap:.0%} over {len(sizes)} strata cannot "
                         f"reach n={n}: the ceilings sum to "
                         f"{sum(ceiling.values())}")
    fixed, free, left_to_place = {}, set(sizes), n
    share = {}
    while free:
        pool = sum(sizes[s] for s in free)
        share = {s: left_to_place * sizes[s] / pool for s in free}
        over = [s for s in free if share[s] > ceiling[s]]
        if not over:
            break
        for s in over:
            fixed[s] = ceiling[s]
            free.discard(s)
            left_to_place -= ceiling[s]
    quota = {s: int(share[s]) for s in free}
    left = left_to_place - sum(quota.values())
    order = sorted(free, key=lambda s: (-(share[s] - quota[s]), s))
    while left > 0:
        room = [s for s in order if quota[s] < ceiling[s]]
        if not room:
            break
        for s in room[:left]:
            quota[s] += 1
        left -= len(room[:left])
    quota.update(fixed)
    return {s: quota[s] for s in sorted(quota) if quota[s]}


def draw(pool, n=N, seed=SEED, cap=CAP):
    """The frozen list. Sorted output, per-site seeds derived from `seed`."""
    by_site = {}
    for row in pool:
        by_site.setdefault(row["site"], []).append(row)
    quota = allocate({s: len(v) for s, v in by_site.items()}, n, cap)
    picked = []
    for site in sorted(quota):
        rows = sorted(by_site[site], key=lambda r: r["base_image"])
        rng = random.Random(f"{seed}:{site}")
        picked += rng.sample(rows, quota[site])
    return sorted(picked, key=lambda r: r["base_image"]), quota


def to_csv_text(rows):
    import io
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in FIELDS})
    return buf.getvalue()


def read_pool(path=POOL):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["n_crowns"] = int(r["n_crowns"])
    return sorted(rows, key=lambda r: r["base_image"])


def parse_args():
    """Read the committed manifest by default. --rebuild-pool derives the pool
    from the live caches instead, which is only correct before the freeze."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild-pool", action="store_true",
                    help="derive the pool from the live caches instead of "
                         "reading the committed manifest. Only correct before "
                         "the freeze")
    ap.add_argument("--write", action="store_true",
                    help="write the pool manifest and the frozen list")
    ap.add_argument("--pool-out", type=Path, default=POOL)
    ap.add_argument("--verify", action="store_true",
                    help="re-draw and compare against the committed CSV")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("-n", type=int, default=N)
    ap.add_argument("--seed", type=int, default=SEED)
    return ap.parse_args()


def report_draw(pool, rows, quota, digest, seed) -> None:
    """What was drawn, and how it spread across sites.

    The sha256 is printed on every run, not only on --verify: it is how anyone
    can tell at a glance whether the list in front of them is the frozen one.
    """
    print(f"eligible pool          : {len(pool)} frames")
    print(f"sites                  : {len(quota)}")
    print(f"drawn                  : {len(rows)} (seed {seed}, cap {CAP:.0%})")
    print(f"crowns in the draw     : {sum(r['n_crowns'] for r in rows)}")
    print(f"flight days in the draw: {len({r['flight_day'] for r in rows})}")
    print(f"sha256                 : {digest}")
    sizes = {}
    for r in pool:
        sizes[r["site"]] = sizes.get(r["site"], 0) + 1
    print(f"\n{'site':18} {'pool':>6} {'drawn':>6} {'share':>7}")
    for s in sorted(quota, key=lambda s: -quota[s]):
        print(f"{s:18} {sizes[s]:6d} {quota[s]:6d} {quota[s] / len(rows):6.1%}")


def verify_draw(args, text) -> None:
    """Hold the committed list to what this seed draws, byte for byte.

    Refuses to run against the live caches: a pool rebuilt after the freeze
    would make the check pass by moving the thing it checks.
    """
    if args.rebuild_pool:
        sys.exit("FAIL: --verify must read the committed manifest, not the "
                 "live caches; drop --rebuild-pool")
    if not args.out.exists():
        sys.exit(f"FAIL: {args.out} does not exist")
    if args.out.read_text() != text:
        sys.exit("FAIL: the committed list is not what this seed draws")
    print(f"\nVERIFY OK: {args.out} matches the draw byte for byte")


def main():
    """Draw the confirmatory sample, or check that the committed one is the
    draw. The draw is a pure function of the pool and the seed, which is what
    makes --verify meaningful."""
    args = parse_args()

    if args.rebuild_pool:
        core = _load("_core", REPO / "dashboard" / "core.py")
        crown = _load("_crown", REPO / "predict" / "crown.py")
        pool = eligible(core, crown)
    else:
        pool = read_pool(args.pool_out)
    rows, quota = draw(pool, args.n, args.seed)
    text = to_csv_text(rows)
    digest = hashlib.sha256(text.encode()).hexdigest()

    report_draw(pool, rows, quota, digest, args.seed)

    if args.verify:
        verify_draw(args, text)
    if args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.rebuild_pool:
            args.pool_out.write_text(to_csv_text(pool))
            print(f"\nwrote {args.pool_out}  {len(pool)} rows")
        args.out.write_text(text)
        print(f"wrote {args.out}  sha256 {digest}")


if __name__ == "__main__":
    main()
