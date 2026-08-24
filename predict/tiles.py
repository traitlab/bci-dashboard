"""Quadrat predictions: let the API slide a window over the whole frame.

Every published number so far comes from a 1280px square cut from the centre of
a 4000x3000 frame, which is 13.7% of it. Crown crops score better than that
square, but a crown crop needs a botanist's box, so it cannot run on a photo
nobody has labelled. The quadrat endpoint needs no box: it slides a 518px window
at stride 259 over the whole frame, 140 sub-queries, and returns a species per
tile plus that species' share of the frame.

This script runs it over a sample of frames that already have a centre-crop
prediction cached, so the two can be compared on the same frames against the
same ground truth. It writes one JSON per frame and never overwrites one.

    python predict/tiles.py --limit 200
    python predict/tiles.py --limit 200 --dry-run

Cost: charged against the quadrat quota (20,000/day), separate from identify.
A 140-tile call did not move the counter when this was written, so the price is
not yet known; --limit is there so a run cannot spend an unknown budget.
"""

import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import random
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "tiles" / "cache"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # a @dataclass in core.py needs this
    spec.loader.exec_module(mod)
    return mod


def log(msg):
    print(msg, flush=True)


def quota(key):
    import requests
    r = requests.get("https://my-api.plantnet.org/v2/quota/daily",
                     params={"api-key": key}, timeout=60)
    return r.json().get("quota", {}) if r.ok else {}


def candidates(core, crown, cache_dir):
    """Frames worth spending a call on, most-informative first.

    A frame earns a call when it has species-level ground truth and an existing
    centre-crop prediction, because only then does the result answer the
    question this script exists for: does seeing the whole frame beat seeing
    13.7% of it, on the same frame, against the same label.
    """
    gt, canon = crown.frame_gt_map(core)
    urls = crown.load_frame_urls()
    photo_cache = REPO / "data" / "predictions" / "cache"
    out = []
    for base, species in gt.items():
        if base not in urls:
            continue
        if not (photo_cache / f"{base}.json").exists():
            continue
        if (cache_dir / f"{base}.json").exists():
            continue
        out.append((base, species))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=100,
                    help="maximum API calls this run may make")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent calls; one frame is ~60s of server work, "
                         "so serial is hours for a few hundred frames")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be sent, call nothing")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    key = os.environ.get("PLANTNET_API_KEY")
    if not key and not args.dry_run:
        sys.exit("ERROR: PLANTNET_API_KEY not set (see .env)")

    core = _load("_core", REPO / "dashboard" / "core.py")
    crown = _load("_crown", REPO / "predict" / "crown.py")
    ingest = _load("_ingest", REPO / "predict" / "ingest_photos.py")

    args.out.mkdir(parents=True, exist_ok=True)
    todo = candidates(core, crown, args.out)
    random.Random(args.seed).shuffle(todo)
    todo = todo[:args.limit]

    log(f"frames eligible and not yet cached : {len(todo)} (capped at {args.limit})")
    if args.dry_run:
        for base, sp in todo[:5]:
            log(f"  would send {base}  gt={sp}")
        return

    before = quota(key)
    log(f"quota before: {json.dumps(before)}")

    urls = crown.load_frame_urls()
    quota_hit = threading.Event()

    def one(item):
        """-> 'ok' | 'fail' | 'quota'. Writes its own cache entry."""
        base, species = item
        if quota_hit.is_set():
            return "skip"
        try:
            raw = ingest.download_image_bytes(urls[base])
            resp = ingest._api_call_with_retry(ingest.call_survey, raw, base, key)
        except ingest.QuotaExceededError:
            # One worker hitting the ceiling means every other worker is about
            # to; stop the whole run rather than spend the list on a quota that
            # is already gone. The cache lets the next run resume.
            quota_hit.set()
            return "quota"
        except Exception as e:                                  # noqa: BLE001
            log(f"  FAIL {base}: {type(e).__name__}: {e}")
            return "fail"
        resp["_gt"] = species
        resp["_base_image"] = base
        dest = args.out / f"{base}.json"
        tmp = dest.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(resp))
        tmp.replace(dest)               # never leave a half-written cache entry
        time.sleep(args.delay)
        return "ok"

    done = failed = 0
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, outcome in enumerate(pool.map(one, todo), 1):
            done += outcome == "ok"
            failed += outcome == "fail"
            if i % 20 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {i}/{len(todo)}  ok={done} fail={failed}  "
                    f"{el / i:.1f}s/frame  {el / 60:.0f}m elapsed")
    if quota_hit.is_set():
        log("  STOPPED: quota exceeded; rerun to resume from the cache")

    after = quota(key)
    log(f"quota after : {json.dumps(after)}")
    for k in sorted(set(before) | set(after)):
        b = before.get(k, {}).get("count")
        a = after.get(k, {}).get("count")
        if b != a:
            log(f"  {k}: {b} -> {a}  ({(a or 0) - (b or 0)} for {done} frames)")
    log(f"written: {done}   failed: {failed}   cache: {args.out}")


if __name__ == "__main__":
    main()
