"""
Phase 18a - Pl@ntNet predictions per CROWN instead of per photo.

13a sends a fixed 1280 square cut from the centre of each base frame, so a
prediction is scored against crown labels that may lie entirely outside the
region the model saw. This script sends each labelled crown's own pixels, which
removes the mismatch instead of filtering around it: the unit of prediction and
the unit of ground truth become the same object.

It also stores the geometry it used. 13a and the ingest script both computed crop
offsets and discarded them, which is why the region had to be reconstructed
afterwards from the box file.

Costs 1 credit per crown. The identify quota is 10,000/day, so a full run over
every labelled crown spans more than one day: the run is resumable and stops
cleanly at --max-calls or on HTTP 429, and re-running continues where it left
off. Frames are downloaded once and reused across the crowns they contain.

Nothing is sent until --run is passed. Without it the script reports the plan,
the credit cost and the join rates, and exits.

Input:
  input/boxes/crop_bounding_boxes.csv                 - crown boxes in frame pixels
  input/boxes/bci_images_for_plantnet_w_split.csv     - base frame URLs

Output:
  data/crowns/cache/<crown_id>.json   - per-crown cache
  data/crowns/run_log.txt

Usage:
  python predict/crown.py
  python predict/crown.py --run --max-calls 9500
  python predict/crown.py --run --sample 500          # size-spanning pilot
"""

import argparse
import collections
import csv
import importlib.util
import io
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

# A crown smaller than this on either side is not worth a credit: below roughly
# this size the crop carries too few pixels for the model to work with, and
# Pl@ntNet would be identifying texture rather than a plant.
MIN_BOX_SIDE = 128

# Identify quota is 10,000/day. Stop below it so a run never trips the limit
# mid-crown and leaves a half-written cache entry.
DEFAULT_MAX_CALLS = 9500
DEFAULT_DELAY = 0.5


def _load_13a():
    """Reuse 13a's API client rather than restating it.

    Module name starts with a digit so it cannot be imported normally; the
    by-path import is the same idiom build_export_only.py uses.
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


def load_frame_urls(frames_csv=FRAMES_CSV):
    """base frame filename -> URL. The CSV repeats frames, one row per crown."""
    urls = {}
    with open(frames_csv, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            urls.setdefault(r["global_key"], r["image_url"])
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
        url = urls.get(base)
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Pl@ntNet predictions per crown.")
    ap.add_argument("--run", action="store_true",
                    help="actually call the API and spend credits")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                    help=f"stop after this many calls (default {DEFAULT_MAX_CALLS})")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--min-box-side", type=int, default=MIN_BOX_SIDE)
    ap.add_argument("--sample", type=int,
                    help="pilot on this many crowns, spread over box sizes")
    ap.add_argument("--sample-frames", type=int, default=100,
                    help="frames the sample is drawn from (default 100)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    load_dotenv(REPO / ".env")
    with open(REPO / "config.yaml") as fh:
        config = yaml.safe_load(fh)

    out_dir = REPO / "data" / "crowns"
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    frames, dupes = load_crowns()
    urls = load_frame_urls()
    n_boxes = sum(len(v) for v in frames.values())

    lines = []

    def log(msg=""):
        print(msg)
        lines.append(msg)

    log("--- INPUT ---")
    log(f"  frames with boxes            : {len(frames)}")
    log(f"  distinct crowns              : {n_boxes}  ({dupes} duplicate rows collapsed)")
    log(f"  frames with a known URL      : {sum(1 for b in frames if b in urls)}")
    matched = sum(1 for b in frames if b in urls)
    if matched < len(frames):
        log(f"  WARNING frames with no URL   : {len(frames) - matched}, their crowns "
            "cannot be fetched")

    todo, dropped = plan(frames, urls, cache_dir, args.min_box_side)
    if args.sample:
        todo = sample_todo(todo, args.sample, args.sample_frames, args.seed)
    log("")
    log("--- PLAN ---")
    log(f"  already cached               : {dropped['cached']}")
    log(f"  skipped, side < {args.min_box_side} px      : {dropped['too_small']}")
    log(f"  skipped, no frame URL        : {dropped['no_frame_url']}")
    if args.sample:
        sides = sorted(min(t[2][2] - t[2][0], t[2][3] - t[2][1]) for t in todo)
        log(f"  SAMPLE of {args.sample} over {args.sample_frames} frames, seed {args.seed}")
        if sides:
            log(f"  sampled shorter side px      : min {sides[0]}, "
                f"median {sides[len(sides) // 2]}, max {sides[-1]}")
            log(f"  sampled below 518 px         : "
                f"{sum(1 for s in sides if s < 518)} of {len(sides)}")
    log(f"  to request                   : {len(todo)}  (1 credit each)")
    log(f"  this run will stop after     : {min(len(todo), args.max_calls)} calls")
    log(f"  frames to download           : {len({t[0] for t in todo[:args.max_calls]})}")

    if not args.run:
        log("")
        log("  DRY RUN. No credits spent. Pass --run to send.")
        return

    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        sys.exit("ERROR: PLANTNET_API_KEY not found in .env")

    pn = _load_13a()
    cfg = config["plantnet"]
    api_url = cfg["identify_url"]

    log("")
    log("--- RUN ---")
    ok = errors = 0
    frame_cache: tuple = (None, None)  # one frame at a time, keyed by name
    todo.sort(key=lambda t: t[0])      # group by frame so each is fetched once

    for i, (base, url, box) in enumerate(todo[:args.max_calls]):
        cid = crown_id(base, box)
        try:
            if frame_cache[0] != base:
                frame_cache = (base, pn.download_image(url))
            jpeg, frame_w, frame_h = crop_box(frame_cache[1], box)
            resp = pn.call_identify_api(
                jpeg, f"{cid}.jpg", api_url, api_key,
                cfg.get("identify_nb_results", 5),
                cfg.get("identify_organs", "auto"),
                cfg.get("identify_lang", "en"),
            )
            entry = pn.parse_response(resp, cid, url, frame_w, frame_h, None)
            # The geometry 13a threw away. Without these fields the region the
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

    (out_dir / "run_log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
