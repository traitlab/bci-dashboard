"""
Pl@ntNet single-species predictions, one call per photo.

Calls the Pl@ntNet /v2/identify/{project} endpoint (one call per image, 1 credit
each) and saves the top-N species results + organ predictions per image.

Uses a centre crop CROP_SIZE px on a side and a disk-cache/resume pattern. Safe to stop and
resume at any time.

Config (config.yaml):
  plantnet.identify_url:        full API endpoint URL
  plantnet.identify_nb_results: how many names to ask for per photo
  plantnet.identify_organs:     organ hint sent to API
  plantnet.identify_lang:       language for common names
Every one is required: the values live in config.yaml, not in a default here.

Input:
  input/boxes/bci_images_for_plantnet_w_split.csv

Output, into the folder config.yaml names and dashboard/core.py reads:
  data/predictions/cache/<global_key>.json:  per-image cache
  data/predictions/predictions.json:         all results combined
  data/predictions/predictions_summary.json: run statistics

Usage:
  python predict/photo.py --test
  python predict/photo.py
  python predict/photo.py --delay 1.0
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import requests
import yaml
from dotenv import load_dotenv
from PIL import Image

REPO = Path(__file__).resolve().parents[1]

# The tracked frame list. Named here rather than typed into the argument
# default, because the folder it sits in comes from config.yaml and the two
# halves of the path were drifting apart: this half still said
# bci_images_for_plantnet.csv, a file no longer in the repo, so a plain
# `python predict/photo.py` opened nothing.
FRAMES_CSV_NAME = "bci_images_for_plantnet_w_split.csv"

CROP_SIZE     = 1280
JPEG_QUALITY  = 90
DEFAULT_DELAY = 0.5
DEFAULT_MAX_CALLS = 9500
MAX_RETRIES   = 3
API_TIMEOUT   = 60
BACKOFF       = [1, 5, 10]


class QuotaExceededError(Exception):
    pass


def load_config():
    """config.yaml, found from this file rather than from the working
    directory, so a run started anywhere reads the settings the repo ships."""
    with open(REPO / "config.yaml") as f:
        return yaml.safe_load(f)


def api_and_project(config=None):
    """The API root and the project id, both read off ``identify_url``.

    Every other Pl@ntNet route this repo calls is that root plus that project:
    the quadrat endpoint the ingest falls back from, the species checklist the
    dashboard reads absence from. Typed out, each was a second copy of the tail
    of one setting, and pointing the run at another project would have left
    them answering for a model the cached predictions never came from.
    """
    url = (config or load_config())["plantnet"]["identify_url"].rstrip("/")
    if "/identify/" not in url:
        raise ValueError(f"config.yaml plantnet.identify_url is not "
                         f".../identify/<project>: {url}")
    base, project = url.rsplit("/identify/", 1)
    return base, project


def load_image_list(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cache_name(global_key: str) -> str:
    """Cache file stem for a global key.

    Current-ingest keys carry the flight folder (``<folder>/DJI_...tele.JPG``),
    so the raw key is not a legal file name. Legacy ``comb_``/``migrated`` keys
    hold no slash, which makes this a no-op for the cached corpus.
    """
    return global_key.replace("/", "__")


def center_crop_jpeg_box(image_bytes: bytes) -> tuple[bytes, int, int, tuple]:
    """-> (jpeg, frame_w, frame_h, box), box being the rectangle that was sent.

    The box is returned rather than recomputed downstream. A prediction is only
    interpretable against the region the model saw, and that region used to be
    reconstructed afterwards from the frame size and CROP_SIZE, which works only
    while every frame is the same shape. A frame smaller than the crop is sent
    whole, and its box is the whole frame.

    This is the one centre crop in the repo. predict/ingest_photos.py calls it
    too, so the two fetch paths cannot send the model different pixels.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    box = (0, 0, w, h)
    if w >= CROP_SIZE and h >= CROP_SIZE:
        left = (w - CROP_SIZE) // 2
        top = (h - CROP_SIZE) // 2
        box = (left, top, left + CROP_SIZE, top + CROP_SIZE)
        img = img.crop(box)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue(), w, h, box


def center_crop_jpeg(image_bytes: bytes) -> tuple[bytes, int, int, int | None]:
    """The same crop, reported the way the per-photo cache records it:
    the crop size when one was taken, and None when the frame went whole."""
    jpeg, w, h, box = center_crop_jpeg_box(image_bytes)
    cropped = (box[2] - box[0], box[3] - box[1]) == (CROP_SIZE, CROP_SIZE)
    return jpeg, w, h, CROP_SIZE if cropped else None


def download_image(url: str, timeout: int = 30) -> bytes:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def post_image(url: str, field: str, jpeg_bytes: bytes, filename: str,
               params: dict, data: dict | None = None,
               timeout: int = API_TIMEOUT) -> dict:
    """One image posted to one Pl@ntNet endpoint, with the quota answer named.

    Every call in predict/ goes through here. They differ in the field name,
    the parameters and how long they may take, and in nothing else. Written
    once so a 429 cannot be a plain HTTPError on one path and a
    QuotaExceededError on another, which is what decides whether a run stops
    and resumes or burns the rest of its images on failures.
    """
    resp = requests.post(
        url,
        files=[(field, (filename, io.BytesIO(jpeg_bytes), "image/jpeg"))],
        data=data,
        params=params,
        timeout=timeout,
    )
    if resp.status_code == 429:
        left = resp.headers.get("X-RateLimit-Remaining", "unknown")
        raise QuotaExceededError(
            f"API quota exceeded (HTTP 429). Remaining: {left}")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def with_retry(fn, *args, **kwargs):
    """`fn` again after a wait, up to MAX_RETRIES, except when the key is out.

    A quota answer is not a transient failure: retrying it spends the wait and
    returns the same 429. Every other failure is worth one more try, since the
    runs this serves are thousands of images long and a single dropped
    connection should not end one.
    """
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except QuotaExceededError:
            raise
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = BACKOFF[attempt]
            print(f"    Attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
            time.sleep(wait)


def call_identify_api(jpeg_bytes: bytes, filename: str, api_url: str,
                      api_key: str, nb_results: int,
                      organs: str, lang: str) -> dict:
    """Call /v2/identify. Returns parsed JSON.
    Raises QuotaExceededError on HTTP 429, RuntimeError on other failures.
    """
    return with_retry(
        post_image, api_url, "images", jpeg_bytes, filename,
        params={"api-key": api_key, "nb-results": nb_results,
                "no-reject": "true", "include-related-images": "false",
                "lang": lang},
        data={"organs": organs})


def parse_response(response: dict, global_key: str, image_url: str,
                   orig_width: int, orig_height: int,
                   crop_size: int | None) -> dict:
    """
    Extract top-N results and organ predictions from API response.
    Each result entry: {rank, score, scientific_name, family, genus, gbif_id, powo_id}
    Organs: list of unique organ strings from predictedOrgans (e.g. ["leaf", "flower"])

    The whole response is kept under "raw". Re-asking Pl@ntNet costs a credit per
    photo, so anything the parser does not model today (similar-image references,
    fields added by a later API version) would otherwise have to be bought twice.
    """
    # Organs are in a separate top-level array, not nested per result
    organs_seen = []
    for po in response.get("predictedOrgans", []):
        organ = po.get("organ")
        if organ and organ not in organs_seen:
            organs_seen.append(organ)

    results = []
    for rank, r in enumerate(response.get("results", []), start=1):
        # `or {}` rather than a .get default: Pl@ntNet sends the key with an
        # explicit null for taxa it cannot resolve, and a default only applies
        # when the key is absent. The chained lookup below then fails on None
        # and the crown costs a credit for nothing.
        sp   = r.get("species") or {}
        gbif = r.get("gbif")    or {}
        powo = r.get("powo")    or {}

        results.append({
            "rank":                rank,
            "score":               r.get("score"),
            "scientific_name":     sp.get("scientificNameWithoutAuthor"),
            "scientific_name_full": sp.get("scientificName"),
            "family":              (sp.get("family") or {}).get("scientificNameWithoutAuthor"),
            "genus":               (sp.get("genus")  or {}).get("scientificNameWithoutAuthor"),
            "gbif_id":             gbif.get("id"),
            "powo_id":             powo.get("id"),
        })

    best_match = results[0]["scientific_name"] if results else None

    return {
        "global_key":        global_key,
        "image_url":         image_url,
        "best_match":        best_match,
        "remaining_credits": response.get("remainingIdentificationRequests"),
        "original_width":    orig_width,
        "original_height":   orig_height,
        "crop_size":         crop_size,
        "results":           results,
        "organs":            organs_seen,
        "raw":               response,
    }


def save_cache(cache_path: Path, entry: dict) -> None:
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry), encoding="utf-8")
    tmp.rename(cache_path)


def parse_args():
    """The four flags, and why --max-calls has a default at all: the daily quota
    is shared, so a run that is allowed to spend all of it can strand a later job."""
    parser = argparse.ArgumentParser(
        description="Get Pl@ntNet single-species predictions for all BCI images."
    )
    parser.add_argument("--test",  action="store_true", help="Process 1 image only (verbose)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"Delay between API calls in seconds (default {DEFAULT_DELAY})")
    parser.add_argument("--input", help="Image list CSV (global_key,image_url). "
                                        "Default: the configured BCI export list.")
    parser.add_argument("--out-dir", help="Output directory. Default: the configured "
                                          "single-prediction folder.")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                        help=f"Stop after this many API calls (default {DEFAULT_MAX_CALLS}). "
                             "Guards the daily quota so a run cannot strand a later job.")
    return parser.parse_args()


def api_settings(config):
    """The four Pl@ntNet settings, read by index rather than with a default.

    config.yaml carries every one of them. A default retyped here would be a
    second copy of the setting that only shows itself when somebody removes the
    key, which is the moment you least want a silent fallback.
    """
    pn_cfg = config["plantnet"]
    return SimpleNamespace(
        url=pn_cfg["identify_url"],
        nb_results=pn_cfg["identify_nb_results"],
        organs=pn_cfg["identify_organs"],
        lang=pn_cfg["identify_lang"])


def outstanding(rows, cache_dir, max_calls):
    """Which photos still need a call, capped at the quota guard.

    Returns the cached set as well as the work: the summary reports both, and
    counting the cache twice in two places is how the two numbers drift.
    """
    cached = {p.stem for p in cache_dir.glob("*.json")}
    to_process = [r for r in rows if cache_name(r["global_key"]) not in cached]
    if len(to_process) > max_calls:
        print(f"  CAPPED at --max-calls={max_calls} "
              f"(of {len(to_process)} outstanding)")
        to_process = to_process[:max_calls]
    return cached, to_process


def report_request(gk, orig_w, orig_h, crop_s, jpeg_bytes, response):
    """What --test prints before the answer is parsed.

    Before, deliberately: a response this script cannot parse is exactly the one
    worth seeing, and printing it afterwards would mean never seeing it.
    """
    print(f"  Image: {gk}")
    print(f"  Original size: {orig_w}\u00d7{orig_h}")
    print(f"  Crop size: {crop_s}")
    print(f"  JPEG size: {len(jpeg_bytes):,} bytes")
    print("\n  Raw API response:")
    print(json.dumps(response, indent=2))


def report_entry(entry):
    """What --test prints once the answer is parsed: the names, in rank order."""
    print("\n  Parsed entry:")
    print(f"  Best match:  {entry['best_match']}")
    print(f"  Results:     {len(entry['results'])} species")
    for r in entry["results"]:
        print(f"    #{r['rank']} {r['scientific_name']} "
              f"(score={r['score']:.4f}, gbif={r['gbif_id']})")
    print(f"  Organs:      {entry['organs']}")
    print(f"  Credits remaining: {entry.get('remaining_credits')}")


def fetch_all(to_process, api, api_key, cache_dir, *, delay, test):
    """Call the API once per photo, writing each answer to the cache as it lands.

    Nothing is held in memory to write at the end: a full run spans a quota
    reset, and stopping it at any point has to leave the work already paid for
    on disk. A quota refusal ends the loop; any other error is counted and the
    next photo is tried.
    """
    ok = errors = 0
    last_remaining = None
    for i, row in enumerate(to_process):
        gk, image_url = row["global_key"], row["image_url"]
        try:
            img_bytes = download_image(image_url)
            jpeg_bytes, orig_w, orig_h, crop_s = center_crop_jpeg(img_bytes)
            response = call_identify_api(
                jpeg_bytes, f"{gk}.jpg", api.url, api_key, api.nb_results,
                api.organs, api.lang
            )
            if test:
                report_request(gk, orig_w, orig_h, crop_s, jpeg_bytes, response)

            entry = parse_response(response, gk, image_url, orig_w, orig_h, crop_s)
            save_cache(cache_dir / f"{cache_name(gk)}.json", entry)
            ok += 1
            last_remaining = entry.get("remaining_credits")

            if test:
                report_entry(entry)
            elif (i + 1) % 100 == 0 or i == 0:
                cr = f", {last_remaining} credits remaining" if last_remaining else ""
                print(f"  [{i+1}/{len(to_process)}] {gk}: "
                      f"top={entry['best_match']}{cr}")

        except QuotaExceededError as e:
            print(f"\n  QUOTA EXCEEDED: {e}")
            print(f"  Processed {ok} images this run. Resume by re-running the script.")
            break
        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{len(to_process)}] ERROR {gk}: {e}")

        if i < len(to_process) - 1:
            time.sleep(delay)
    return ok, errors, last_remaining


def write_outputs(cache_dir, output_dir, api, summary_extra):
    """Rebuild predictions.json from the cache, not from this run.

    The cache is the record. Assembling from it means a run that fetched nothing
    still writes a complete file, and two half-runs add up to one whole one.
    """
    all_entries = [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted(cache_dir.glob("*.json"))]
    out_path = output_dir / "predictions.json"
    out_path.write_text(json.dumps(all_entries, indent=2), encoding="utf-8")

    summary = {
        "total_cached":       len(all_entries),
        "api_url":            api.url,
        "nb_results":         api.nb_results,
        "organs":             api.organs,
        "crop_size":          CROP_SIZE,
        **summary_extra,
    }
    summary_path = output_dir / "predictions_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_path, len(all_entries)


def main():
    """Load the list, call for what is missing, then rebuild the output from the
    cache. Every step prints what it did, because the slow one can run for hours."""
    args = parse_args()
    load_dotenv()
    config = load_config()

    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        sys.exit("ERROR: PLANTNET_API_KEY not found in .env")

    api = api_settings(config)
    images_csv  = (Path(args.input) if args.input else
                   Path(config["folders"]["export_for_plantnet"]) / FRAMES_CSV_NAME)
    output_dir  = (Path(args.out_dir) if args.out_dir else
                   Path(config["folders"]["single_predictions"]))
    cache_dir   = output_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("Step 1 - Loading image list...")
    rows = load_image_list(images_csv)
    print(f"  {len(rows)} images")
    if args.test:
        rows = rows[:1]
        print("  TEST MODE: 1 image only")

    cached, to_process = outstanding(rows, cache_dir, args.max_calls)
    print(f"\nStep 2 - Calling Pl@ntNet API ({api.url})...")
    print(f"  Already cached: {len(cached)}")
    print(f"  To process:     {len(to_process)}")
    if not to_process:
        print("  All images already cached, proceeding to assemble output.")
    else:
        print(f"  Delay: {args.delay}s between calls\n")

    ok, errors, last_remaining = fetch_all(
        to_process, api, api_key, cache_dir, delay=args.delay, test=args.test)

    print("\nStep 3 - Assembling predictions.json from cache...")
    out_path, n_cached = write_outputs(cache_dir, output_dir, api, {
        "processed_this_run": ok,
        "skipped_cached":     len(cached),
        "errors_this_run":    errors,
        "last_credits_remaining": last_remaining,
        "test_mode":          args.test,
    })
    print(f"  {n_cached} predictions written to {out_path}")

    rule = "=" * 55
    print(f"\n{rule}\nSUMMARY\n{rule}")
    print(f"  Total in cache:      {n_cached}")
    print(f"  Processed this run:  {ok}")
    print(f"  Errors this run:     {errors}")
    if last_remaining is not None:
        print(f"  Credits remaining:   {last_remaining}")
    print(f"  Output:              {out_path}")
    print(rule)


if __name__ == "__main__":
    main()
