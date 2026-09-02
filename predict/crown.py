"""
Pl@ntNet predictions per crown instead of per photo.

predict/photo.py sends a fixed square cut from the centre of each base frame, so
a prediction is scored against crown labels that may lie entirely outside the
region the model saw. This script sends each labelled crown's own pixels, which
removes the mismatch instead of filtering around it, and stores the geometry it
used: photo.py and the ingest script both computed crop offsets and discarded
them, so the region had to be reconstructed afterwards from the box file.

Costs 1 credit per crown, against a quota of 10,000/day, so a full run spans
more than one day. It is resumable: cached crowns are skipped, and nothing is
sent until --run is passed.

Input:
  input/boxes/crop_bounding_boxes.csv                 - crown boxes in frame pixels
  input/boxes/bci_images_for_plantnet_w_split.csv     - base frame URLs

Output:
  data/crowns/cache/<crown_id>.json   - per-crown cache
  data/crowns/run_log.txt

Usage:
  python predict/crown.py
  python predict/crown.py --run
  python predict/crown.py --run --sample 500          # size-spanning pilot
  python predict/crown.py --run --frame-paired 700    # paired crown-vs-crop pilot
"""

import argparse
import collections
import csv
import importlib.util
import io
import json
import os
import random
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from PIL import Image

REPO = Path(__file__).resolve().parents[1]

BOXES_CSV = REPO / "input" / "boxes" / "crop_bounding_boxes.csv"
FRAMES_CSV = REPO / "input" / "boxes" / "bci_images_for_plantnet_w_split.csv"

# The tracked frame list covers the 2024 corpus only. Frames ingested since live
# in the dataset inventory, under a global key that carries the flight folder.
# Boxes for those frames resolve here or not at all.
DATASET_ROWS = REPO / "data" / "dataset_rows.jsonl"

# A crown smaller than this on either side is not worth a credit: below roughly
# this size the crop carries too few pixels for the model to work with, and
# Pl@ntNet would be identifying texture rather than a plant.
MIN_BOX_SIDE = 128

# Pl@ntNet's own window on a frame, the one it slides when it surveys a whole
# image (predict/ingest_photos.py records the measurement). The sample line
# below counts crowns smaller than that, which are crowns smaller than what the
# model looks at in one step. It was the number 518 typed into the comparison
# and again into the words beside it.
TILE_WINDOW_PX = 518

# Identify quota is 10,000/day. Stop below it so a run never trips the limit
# mid-crown and leaves a half-written cache entry.
DEFAULT_MAX_CALLS = 9500
DEFAULT_DELAY = 0.5


def _load_photo_script():
    """Reuse predict/photo.py's API client rather than restating it.

    Loaded by path, not by package import: predict/ holds no __init__.py, so it
    is not a package on the normal path. Same idiom build_export_only.py uses.
    """
    path = REPO / "predict" / "photo.py"
    spec = importlib.util.spec_from_file_location("_predict_photo", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def crown_id(base_image: str, box: tuple) -> str:
    """Stable cache key: the frame plus the box that was cut from it."""
    stem = base_image[:-4] if base_image.lower().endswith(".jpg") else base_image
    return f"{stem}__{box[0]}_{box[1]}_{box[2]}_{box[3]}"


def load_crowns(boxes_csv=BOXES_CSV):
    """base_image -> list of (x0, y0, x1, y1, label). Duplicate boxes collapsed."""
    frames = collections.defaultdict(list)
    seen = set()
    dupes = 0
    with open(boxes_csv, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            box = (int(r["x_min"]), int(r["y_min"]), int(r["x_max"]), int(r["y_max"]))
            key = (r["base_image"], box)
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            frames[r["base_image"]].append(box + (r["lb_label"],))
    return frames, dupes


def load_frame_urls(frames_csv=FRAMES_CSV, rows_jsonl=DATASET_ROWS):
    """base frame filename -> URL. The CSV repeats frames, one row per crown.

    Three global-key namespaces exist and only the basename is common between
    them: `comb_NAME`, `migrated/NAME`, and `<flight_folder>/NAME`. The tracked
    frame list keys on the bare filename and covers the 2024 corpus; anything
    ingested since resolves only through the dataset inventory. Both are keyed
    on the basename here, so a box finds its frame whichever namespace it came
    from. The CSV is applied last and wins, because it is the tracked definition
    of the population.
    """
    urls = {}
    if rows_jsonl and Path(rows_jsonl).exists():
        with open(rows_jsonl, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                key, url = row.get("global_key") or "", row.get("row_data") or ""
                if key and url:
                    urls.setdefault(key.split("/")[-1], url)
    with open(frames_csv, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            urls[r["global_key"].split("/")[-1]] = r["image_url"]
    return urls


def crop_box(image_bytes: bytes, box: tuple) -> tuple:
    """Cut `box` out of the frame. Returns (jpeg_bytes, frame_w, frame_h).

    The box is clamped to the frame, since a few boxes overshoot an edge by 1-2
    px. No resize: Pl@ntNet downsamples on its side, and upscaling a small crown
    would invent detail the sensor never recorded.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    x0, y0 = max(0, box[0]), max(0, box[1])
    x1, y1 = min(box[2], w), min(box[3], h)
    buf = io.BytesIO()
    img.crop((x0, y0, x1, y1)).save(buf, format="JPEG", quality=90)
    return buf.getvalue(), w, h


def plan(frames, urls, cache_dir, min_box_side=MIN_BOX_SIDE):
    """What a run would do, without doing any of it."""
    todo, too_small, no_url, cached = [], 0, 0, 0
    for base, boxes in frames.items():
        url = urls.get(base) or urls.get(base.split("/")[-1])
        for box in boxes:
            if url is None:
                no_url += 1
                continue
            if (box[2] - box[0]) < min_box_side or (box[3] - box[1]) < min_box_side:
                too_small += 1
                continue
            if (cache_dir / f"{crown_id(base, box)}.json").exists():
                cached += 1
                continue
            todo.append((base, url, box))
    return todo, {"too_small": too_small, "no_frame_url": no_url, "cached": cached}


def sample_todo(todo, n, n_frames, seed, bins=5):
    """A size-spanning subset of `todo`, cheap to fetch.

    Taking the first n entries would run the alphabetically earliest missions,
    and drawing n crowns at random would download nearly n frames at ~8 MB each.
    So frames are drawn first, then crowns within them are spread evenly over
    quantile bins of the shorter box side: the pilot has to say how the score
    varies with crown size, which needs the small and the large ones both.
    """
    rng = random.Random(seed)
    frames = sorted({t[0] for t in todo})
    chosen = set(rng.sample(frames, min(n_frames, len(frames))))
    pool = [t for t in todo if t[0] in chosen]
    if len(pool) <= n:
        return pool

    def short_side(t):
        return min(t[2][2] - t[2][0], t[2][3] - t[2][1])

    pool.sort(key=short_side)
    edges = [len(pool) * i // bins for i in range(bins + 1)]
    buckets = [pool[edges[i]:edges[i + 1]] for i in range(bins)]
    for b in buckets:
        rng.shuffle(b)
    out = []
    while len(out) < n and any(buckets):
        for b in buckets:
            if b and len(out) < n:
                out.append(b.pop())
    return out


def _load_core():
    """dashboard/core.py by path, for the name rules the GT join depends on."""
    path = REPO / "dashboard" / "core.py"
    spec = importlib.util.spec_from_file_location("_dashboard_core", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_dashboard_core"] = mod   # a @dataclass in core.py needs this
    spec.loader.exec_module(mod)
    return mod


def frame_gt_map(core):
    """base frame -> canonical GT species, for species-level GT only."""
    crosswalk, _ = core.load_wcvp_crosswalk(REPO / "data" / "wcvp_cache.json")

    def canon(name):
        n = core.normalize(name or "")
        return crosswalk.get(n, n)

    out = {}
    with open(REPO / "data" / "gt_dominant_taxon.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            gk = r["global_key"]
            stem = gk.removeprefix(core.GT_KEY_PREFIX)
            g = canon(r["wcvp_canonical_name"])
            if g and core.is_species_level(g):
                out[stem] = g
    return out, canon


def frame_paired_todo(frames, urls, n_frames, seed, cache_dir, min_box_side):
    """One crown per frame, plus a second where the frame allows it.

    The question a pilot has to answer is whether a crown's own pixels beat the
    centre crop of the same frame. That comparison is paired on the FRAME, so
    sending five crowns from one frame buys one comparison at five times the
    price: the first pilot spent 500 credits to reach 74 paired frames.

    A frame qualifies only if it can be compared at all: it needs a species-level
    GT label, a photo-cache entry scored from the centre crop, and at least one
    crown whose own label is that same species. Two crowns are sent per frame
    where possible, the largest matching crown and one other drawn at random.
    The largest alone would measure crown cropping at its best case while the
    photo arm runs as it is, which answers a narrower question than the one asked.

    Eligibility is judged against every matching box for the frame (cached or
    not), not against `plan()`'s cache-filtered todo: that todo already drops
    a crown the moment it is cached, so a frame with its largest crown done and
    its second still missing would otherwise look identical to a frame with
    nothing done at all. A frame is skipped only once both crowns it would emit
    are already cached (or its one crown, for a frame with no second candidate),
    so re-running the same command resumes a quota-interrupted pilot instead of
    drawing a fresh set of frames on top of it.
    """
    core = _load_core()
    gt, canon = frame_gt_map(core)
    photo_cache = REPO / "data" / "predictions" / "cache"

    eligible = {}
    for base, boxes in frames.items():
        url = urls.get(base) or urls.get(base.split("/")[-1])
        g = gt.get(base)
        if url is None or not g or not (photo_cache / f"{base}.json").exists():
            continue
        match = [(base, url, box) for box in boxes
                 if (box[2] - box[0]) >= min_box_side
                 and (box[3] - box[1]) >= min_box_side
                 and canon(core.strip_collection_codes(box[4])) == g]
        if match:
            eligible[base] = match

    def is_cached(t):
        return (cache_dir / f"{crown_id(t[0], t[2])}.json").exists()

    rng = random.Random(seed)
    chosen = sorted(eligible)
    rng.shuffle(chosen)
    out = []
    drawn = 0
    for base in chosen:
        if drawn >= n_frames:
            break
        match = eligible[base]
        largest = max(match, key=lambda t: ((t[2][2] - t[2][0]) * (t[2][3] - t[2][1])))
        rest = [t for t in match if t is not largest]
        second_done = any(is_cached(t) for t in rest)
        if is_cached(largest) and (not rest or second_done):
            continue  # both crowns this frame would emit are already cached
        drawn += 1
        if not is_cached(largest):
            out.append(largest)
        if rest and not second_done:
            out.append(rng.choice(rest))
    return out, len(eligible)


def parse_args(argv=None):
    """Every knob the run has, and what each one costs."""
    ap = argparse.ArgumentParser(description="Pl@ntNet predictions per crown.")
    ap.add_argument("--run", action="store_true",
                    help="actually call the API and spend credits")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                    help=f"stop after this many calls (default {DEFAULT_MAX_CALLS})")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--min-box-side", type=int, default=MIN_BOX_SIDE)
    ap.add_argument("--frame-paired", type=int, metavar="N_FRAMES",
                    help="pilot on N frames, up to 2 crowns each, for the "
                         "paired crown-vs-centre-crop test")
    ap.add_argument("--sample", type=int,
                    help="pilot on this many crowns, spread over box sizes")
    ap.add_argument("--sample-frames", type=int, default=100,
                    help="frames the sample is drawn from (default 100)")
    ap.add_argument("--boxes-csv", default=str(BOXES_CSV),
                    help="crown geometry. The default is the 2024 file; pass "
                         "data/export_boxes.csv for current geometry")
    ap.add_argument("--frames-csv", default=str(FRAMES_CSV),
                    help="frame URLs (global_key,image_url)")
    ap.add_argument("--frames-jsonl", default=str(DATASET_ROWS),
                    help="dataset inventory, for frames the frame list lacks")
    ap.add_argument("--allow-missing-frames", action="store_true",
                    help="proceed even though some boxes have no frame URL; "
                         "without this such a run exits 2")
    ap.add_argument("--only-frames", metavar="FILE",
                    help="restrict to the base_image names in FILE, one per "
                         "line, to answer one question cheaply")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", default=None,
                    help="where the cache and run log go. Give a separate one "
                         "per box geometry, so two runs stay comparable "
                         "instead of mixing in a single cache")
    return ap.parse_args(argv)


def open_run_log(path):
    """Print and append at once, so a long run can be tailed while it is alive.

    The file is truncated here and appended to on every call, rather than
    written at the end: a run that spans a quota reset is one nobody watches to
    completion.
    """
    path.write_text("", encoding="utf-8")

    def log(msg=""):
        print(msg, flush=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    return log


def report_input(log, args, frames, dupes, urls, only):
    """What the box file and the frame list gave us, before any planning."""
    log("--- INPUT ---")
    if only is not None:
        log(f"  RESTRICTED to {len(only)} frames from {args.only_frames}")
    matched = sum(1 for b in frames if b in urls)
    log(f"  frames with boxes            : {len(frames)}")
    log(f"  distinct crowns              : {sum(len(v) for v in frames.values())}"
        f"  ({dupes} duplicate rows collapsed)")
    log(f"  frames with a known URL      : {matched}")
    if matched < len(frames):
        log(f"  WARNING frames with no URL   : {len(frames) - matched}, their crowns "
            "cannot be fetched")


def report_plan(log, args, frames, urls, todo, dropped, n_eligible):
    """The credit cost of the job, and the one condition that refuses to run.

    Returns 2 when frames would be dropped silently, otherwise None. A run that
    cannot resolve a frame drops every crown of that frame and still reports
    "requested ok: 0, errors: 0", which reads as a completed job. Six such runs
    against the tele frames looked like success and cost three days.
    """
    log("")
    log("--- PLAN ---")
    log(f"  already cached               : {dropped['cached']}")
    log(f"  skipped, side < {args.min_box_side} px      : {dropped['too_small']}")
    log(f"  skipped, no frame URL        : {dropped['no_frame_url']}")
    if dropped["no_frame_url"] and not args.allow_missing_frames:
        unresolved = sorted({b for b in frames
                             if not (urls.get(b) or urls.get(b.split("/")[-1]))})
        log("")
        log(f"  ERROR {dropped['no_frame_url']} crowns across {len(unresolved)} "
            "frames have no URL and would be skipped silently.")
        for b in unresolved[:3]:
            log(f"    {b}")
        if len(unresolved) > 3:
            log(f"    ... and {len(unresolved) - 3} more")
        log("  Add these frames to the frame list or the dataset inventory, or "
            "pass --allow-missing-frames to accept the gap.")
        return 2
    if args.frame_paired:
        n_f = len({t[0] for t in todo})
        log(f"  FRAME-PAIRED sample, seed {args.seed}")
        log(f"  frames comparable in both arms : {n_eligible} "
            f"(species-level GT, a photo-cache entry, and a crown of that species)")
        log(f"  frames drawn                   : {n_f}")
        log(f"  frames giving a second crown   : {len(todo) - n_f}")
    elif args.sample:
        sides = sorted(min(t[2][2] - t[2][0], t[2][3] - t[2][1]) for t in todo)
        log(f"  SAMPLE of {args.sample} over {args.sample_frames} frames, seed {args.seed}")
        if sides:
            log(f"  sampled shorter side px      : min {sides[0]}, "
                f"median {sides[len(sides) // 2]}, max {sides[-1]}")
            log(f"  sampled below {TILE_WINDOW_PX} px         : "
                f"{sum(1 for s in sides if s < TILE_WINDOW_PX)} of {len(sides)}")
    log(f"  to request                   : {len(todo)}  (1 credit each)")
    log(f"  this run will stop after     : {min(len(todo), args.max_calls)} calls")
    log(f"  frames to download           : {len({t[0] for t in todo[:args.max_calls]})}")
    return None


def fetch_crowns(log, args, todo, cache_dir, cfg, api_key):
    """Send each crown, cache the answer with the geometry it was cut from.

    One frame is held at a time and the work is sorted by frame, so a frame
    carrying eight crowns is downloaded once. A bad crown is logged and skipped;
    a spent quota stops the run cleanly, and the cache makes the next one resume.
    """
    pn = _load_photo_script()
    api_url = cfg["identify_url"]
    log("")
    log("--- RUN ---")
    ok = errors = 0
    frame_cache: tuple = (None, None)  # one frame at a time, keyed by name
    todo.sort(key=lambda t: t[0])      # group by frame so each is fetched once

    for base, url, box in todo[:args.max_calls]:
        cid = crown_id(base, box)
        try:
            if frame_cache[0] != base:
                frame_cache = (base, pn.download_image(url))
            jpeg, frame_w, frame_h = crop_box(frame_cache[1], box)
            resp = pn.call_identify_api(
                jpeg, f"{cid}.jpg", api_url, api_key,
                cfg["identify_nb_results"],
                cfg["identify_organs"],
                cfg["identify_lang"],
            )
            entry = pn.parse_response(resp, cid, url, frame_w, frame_h, None)
            # The geometry photo.py threw away. Without these fields the region the
            # model saw cannot be recovered from the cache alone.
            entry.update({
                "base_image": base,
                "box": {"x_min": box[0], "y_min": box[1],
                        "x_max": box[2], "y_max": box[3]},
                "frame_width": frame_w,
                "frame_height": frame_h,
                "lb_label": box[4],
                "unit": "crown",
            })
            pn.save_cache(cache_dir / f"{cid}.json", entry)
            ok += 1
            if entry.get("remaining_credits") is not None and ok % 100 == 0:
                log(f"  {ok} done, {entry['remaining_credits']} credits left")
        except pn.QuotaExceededError as e:
            log(f"  STOPPING at {ok} calls: {e}")
            log("  Re-run tomorrow; cached crowns are skipped automatically.")
            break
        except Exception as e:  # noqa: BLE001 - one bad crown must not end the run
            errors += 1
            log(f"  ERROR {cid}: {e}")
        if args.delay:
            time.sleep(args.delay)

    log("")
    log(f"  requested ok : {ok}")
    log(f"  errors       : {errors}")
    log(f"  cache        : {cache_dir}")


def main(argv=None) -> int | None:
    """Report the plan, and send only if --run says to."""
    args = parse_args(argv)
    load_dotenv(REPO / ".env")
    with open(REPO / "config.yaml") as fh:
        config = yaml.safe_load(fh)

    out_dir = Path(args.out_dir) if args.out_dir else REPO / "data" / "crowns"
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    log = open_run_log(out_dir / "run_log.txt")

    frames, dupes = load_crowns(args.boxes_csv)
    urls = load_frame_urls(args.frames_csv, args.frames_jsonl)

    # Applied before anything is counted, so the PLAN block reports the cost of
    # the restricted job rather than the whole corpus.
    only = None
    if args.only_frames:
        with open(args.only_frames, encoding="utf-8") as fh:
            only = {line.strip() for line in fh if line.strip()}
        frames = {b: v for b, v in frames.items() if b in only}

    report_input(log, args, frames, dupes, urls, only)

    todo, dropped = plan(frames, urls, cache_dir, args.min_box_side)
    n_eligible = None
    if args.frame_paired:
        todo, n_eligible = frame_paired_todo(
            frames, urls, args.frame_paired, args.seed, cache_dir, args.min_box_side)
    elif args.sample:
        todo = sample_todo(todo, args.sample, args.sample_frames, args.seed)

    refused = report_plan(log, args, frames, urls, todo, dropped, n_eligible)
    if refused is not None:
        return refused

    if not args.run:
        log("")
        log("  DRY RUN. No credits spent. Pass --run to send.")
        return None

    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        sys.exit("ERROR: PLANTNET_API_KEY not found in .env")
    fetch_crowns(log, args, todo, cache_dir, config["plantnet"], api_key)
    return None


if __name__ == "__main__":
    sys.exit(main())
