"""Ingest drone photos: call Pl@ntNet, aggregate, and score.

Per photo, calls identify + embeddings (the two-call stand-in for direct
survey access) and writes one survey-shaped JSON, then runs the aggregation
and scoring in predict/aggregate_survey.py.

Photos come from a local directory (--photos) or from a CSV carrying
image_url (--csv). CSV mode streams each photo from its URL and never writes
image data to disk, which is how the Arbutus bucket is processed.

Output per image, in --out-dir/cache/: <filename>.json, the survey-shaped
record. Aggregated, in --out-dir/: survey_embeddings.json (coverage-weighted)
and survey_species_scores.json (rarity-weighted).

Usage:
    python predict/ingest_photos.py --csv input/boxes/bci_images_for_plantnet_w_split.csv
    python predict/ingest_photos.py --photos /data/new_drone_photos/
    python predict/ingest_photos.py --csv ... --test        # one image

--survey-endpoint <url> calls the survey API directly instead, when a key
that reaches it is available.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from photo import (
    CROP_SIZE,
    QuotaExceededError,
    center_crop_jpeg_box,
    load_config,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data"

MAX_RETRIES = 3
BACKOFF = [1, 5, 10]
API_TIMEOUT = 60
DEFAULT_DELAY = 0.5

# The quadrat endpoint. The path documented as /v2/survey/<project> returns 404;
# this is the one that answers, and the trailing 'tiles' is the flavor.
SURVEY_TILES_URL = "https://my-api.plantnet.org/v2/survey/tiles/k-central-america"
# One call runs 140 sub-queries over a 4000x3000 frame, so it is not a 60s job.
SURVEY_TIMEOUT = 300
IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def load_csv_urls(csv_path: Path) -> list[tuple[str, str]]:
    import csv as csvmod
    entries = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csvmod.DictReader(f):
            url = row.get("image_url", "").strip()
            gk = row.get("global_key", "").strip()
            if url and gk:
                entries.append((gk, url))
    return entries


def download_image_bytes(url: str) -> bytes:
    resp = requests.get(url, timeout=API_TIMEOUT)
    resp.raise_for_status()
    return resp.content


# The crop lives in photo.py, so both fetch paths send the model the same
# pixels and record the same rectangle.
center_crop_jpeg_from_bytes = center_crop_jpeg_box


def center_crop_jpeg(image_path: Path) -> tuple[bytes, int, int, tuple]:
    return center_crop_jpeg_from_bytes(image_path.read_bytes())


def _api_call_with_retry(fn, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except QuotaExceededError:
            raise
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = BACKOFF[attempt]
                print(f"    Attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def _post(url: str, field: str, jpeg_bytes: bytes, filename: str,
          params: dict, data: dict | None = None, timeout: int = API_TIMEOUT) -> dict:
    """One image posted to one endpoint, with the quota answer named.

    The three calls below differ in the field name, the parameters and how
    long they may take, and in nothing else. Written once so a 429 cannot be
    a plain HTTPError on one path and a QuotaExceededError on another.
    """
    resp = requests.post(
        url,
        files=[(field, (filename, io.BytesIO(jpeg_bytes), "image/jpeg"))],
        data=data,
        params=params,
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise QuotaExceededError("Quota exceeded (HTTP 429)")
    resp.raise_for_status()
    return resp.json()


def call_identify(jpeg_bytes: bytes, filename: str, api_key: str,
                  api_url: str, nb_results: int, organs: str) -> dict:
    """One identify call. Both request settings come from config.yaml.

    `organs` used to be "auto" typed here, so `plantnet.identify_organs` moved
    `predict/photo.py` and left this path asking the old way, silently.
    """
    return _post(api_url, "images", jpeg_bytes, filename,
                 params={"api-key": api_key, "nb-results": nb_results,
                         "no-reject": "true", "include-related-images": "false"},
                 data={"organs": organs})


def call_embeddings(jpeg_bytes: bytes, filename: str, api_key: str,
                    api_url: str) -> dict:
    return _post(api_url, "image", jpeg_bytes, filename,
                 params={"api-key": api_key})


def call_survey(jpeg_bytes: bytes, filename: str, api_key: str,
                survey_url: str = SURVEY_TILES_URL) -> dict:
    """Quadrat: the API slides a 518px window over the whole frame itself.

    The field is 'image', singular, unlike identify's 'images'. Sending the
    plural name returns HTTP 400 '"image" is required', which is how this was
    found: the endpoint had been assumed unavailable on this key when in fact
    only the request was malformed. 'organs' is not accepted here either.

    Verified 2026-08-15 against a 4000x3000 frame: 140 sub-queries at
    tile_size 518 / tile_stride 259, and the quadrat quota counter did not move.
    """
    return _post(survey_url, "image", jpeg_bytes, filename,
                 params={"api-key": api_key}, timeout=SURVEY_TIMEOUT)


def identify_to_survey_json(identify_resp: dict, emb_resp: dict) -> dict:
    """Convert identify + embeddings responses into survey-compatible JSON.

    The single-species endpoint returns confidence scores, not coverage.
    We use confidence as a proxy for coverage so 15c's weighted aggregation
    still works (higher-confidence species get more embedding weight).
    """
    species = []
    for r in identify_resp.get("results", []):
        sp = r.get("species", {})
        gbif = r.get("gbif", {})
        score = r.get("score", 0.0)
        species.append({
            "gbif_id": str(gbif.get("id", "")),
            "binomial": sp.get("scientificNameWithoutAuthor", ""),
            "name": sp.get("commonNames", [""])[0] if sp.get("commonNames") else "",
            "coverage": score,
            "max_score": score,
            "count": 1,
            "location": [],
        })

    emb_vector = None
    for key in ("embedding", "embeddings", "vector"):
        if key in emb_resp:
            val = emb_resp[key]
            if isinstance(val, list) and val and isinstance(val[0], (int, float)):
                emb_vector = val
                break
            elif isinstance(val, list) and val and isinstance(val[0], dict):
                emb_vector = val[0].get("embeddings", [])
                break

    per_tiles = []
    if emb_vector:
        per_tiles.append({"embeddings": emb_vector})

    return {
        "results": {
            "species": species,
            "per_tiles_embeddings": per_tiles,
        }
    }


def stamp_geometry(result: dict, frame_w: int, frame_h: int, box: tuple) -> dict:
    """Record the region that was actually sent, alongside the API's answer.

    Without this the cache says what the model replied and not what it was
    looking at, so any later comparison against a crown box has to assume every
    frame is 4000x3000 and the crop is always the same rectangle. That is true
    of the corpus today and is not a property of the data.
    """
    result["crop"] = {
        "box": {"x_min": box[0], "y_min": box[1], "x_max": box[2], "y_max": box[3]},
        "frame_width": frame_w,
        "frame_height": frame_h,
        "crop_size": CROP_SIZE,
        "unit": "photo",
    }
    return result


def process_photo(
    photo_path: Path,
    api_key: str,
    config: dict,
    cache_dir: Path,
    survey_url: str | None = None,
    delay: float = DEFAULT_DELAY,
) -> dict | None:
    filename = photo_path.name
    cache_file = cache_dir / f"{filename}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    jpeg_bytes, orig_w, orig_h, crop_box = center_crop_jpeg(photo_path)

    if survey_url:
        raw = _api_call_with_retry(call_survey, jpeg_bytes, filename, api_key, survey_url)
        result = raw
    else:
        identify_url = config["plantnet"]["identify_url"]
        embeddings_url = config["plantnet"]["embeddings_api_url"]
        nb_results = config["plantnet"]["identify_nb_results"]
        organs = config["plantnet"]["identify_organs"]

        id_resp = _api_call_with_retry(
            call_identify, jpeg_bytes, filename, api_key, identify_url,
            nb_results, organs
        )
        time.sleep(delay)
        emb_resp = _api_call_with_retry(
            call_embeddings, jpeg_bytes, filename, api_key, embeddings_url
        )
        result = identify_to_survey_json(id_resp, emb_resp)

    stamp_geometry(result, orig_w, orig_h, crop_box)

    tmp = cache_file.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(result, f)
    tmp.replace(cache_file)
    return result


def process_url(
    filename: str,
    url: str,
    api_key: str,
    config: dict,
    cache_dir: Path,
    survey_url: str | None = None,
    delay: float = DEFAULT_DELAY,
) -> dict | None:
    cache_file = cache_dir / f"{filename}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    raw_image = download_image_bytes(url)
    jpeg_bytes, orig_w, orig_h, crop_box = center_crop_jpeg_from_bytes(raw_image)

    if survey_url:
        result = _api_call_with_retry(call_survey, jpeg_bytes, filename, api_key, survey_url)
    else:
        identify_url = config["plantnet"]["identify_url"]
        embeddings_url = config["plantnet"]["embeddings_api_url"]
        nb_results = config["plantnet"]["identify_nb_results"]
        organs = config["plantnet"]["identify_organs"]

        id_resp = _api_call_with_retry(
            call_identify, jpeg_bytes, filename, api_key, identify_url,
            nb_results, organs
        )
        time.sleep(delay)
        emb_resp = _api_call_with_retry(
            call_embeddings, jpeg_bytes, filename, api_key, embeddings_url
        )
        result = identify_to_survey_json(id_resp, emb_resp)

    stamp_geometry(result, orig_w, orig_h, crop_box)

    tmp = cache_file.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(result, f)
    tmp.replace(cache_file)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--photos", type=Path,
                        help="directory of local drone JPGs")
    source.add_argument("--csv", type=Path,
                        help="CSV with global_key,image_url columns (streams from URLs)")
    ap.add_argument("--survey-endpoint", type=str, default=None,
                    help="direct survey API URL (skips 2-call fallback)")
    ap.add_argument("--gt", type=Path, default=OUT / "gt_dominant_taxon.csv",
                    help="GT CSV for species-priority scoring")
    ap.add_argument("--rare-threshold", type=int, default=5)
    ap.add_argument("--method", choices=["sum", "max"], default="sum")
    ap.add_argument("--out-dir", type=Path, default=OUT / "predictions")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                    help=f"delay between API calls (default {DEFAULT_DELAY}s)")
    ap.add_argument("--no-aggregate", action="store_true",
                    help="skip aggregation (cache JSONs only, aggregate locally later)")
    ap.add_argument("--test", action="store_true", help="process 1 image only")
    args = ap.parse_args()

    load_dotenv()
    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        sys.exit("ERROR: PLANTNET_API_KEY not found in .env")

    config = load_config()
    out_dir = args.out_dir
    cache_dir = out_dir / "cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.csv:
        entries = load_csv_urls(args.csv)
        if not entries:
            sys.exit(f"No valid rows in {args.csv}")
        if args.test:
            entries = entries[:1]
            print("TEST MODE: 1 image only\n")

        mode = "survey" if args.survey_endpoint else "identify+embeddings"
        cached = sum(1 for gk, _ in entries if (cache_dir / f"{gk}.json").exists())
        print(f"Ingesting {len(entries)} photos via {mode} (streaming from URLs)")
        print(f"  Cached: {cached}, remaining: {len(entries) - cached}\n")

        processed = 0
        failed = []
        for i, (gk, url) in enumerate(entries, 1):
            print(f"  [{i}/{len(entries)}] {gk} ... ", end="", flush=True)
            try:
                result = process_url(
                    gk, url, api_key, config, cache_dir,
                    survey_url=args.survey_endpoint, delay=args.delay,
                )
                if result:
                    n_sp = len(result.get("results", {}).get("species", []))
                    print(f"OK ({n_sp} species)")
                    processed += 1
                else:
                    print("SKIP (no result)")
            except QuotaExceededError as e:
                print(f"\n\nQUOTA EXHAUSTED after {processed} images: {e}")
                print("Safe to resume -- cached images will be skipped.")
                break
            except Exception as e:
                print(f"FAIL ({e})")
                failed.append(gk)

            if i < len(entries):
                time.sleep(args.delay)
    else:
        photos = sorted(
            p for p in args.photos.iterdir()
            if p.suffix.lower() in IMG_EXTENSIONS
        )
        if not photos:
            sys.exit(f"No image files found in {args.photos}")

        if args.test:
            photos = photos[:1]
            print("TEST MODE: 1 image only\n")

        mode = "survey" if args.survey_endpoint else "identify+embeddings"
        cached = sum(1 for p in photos if (cache_dir / f"{p.name}.json").exists())
        print(f"Ingesting {len(photos)} photos via {mode}")
        print(f"  Cached: {cached}, remaining: {len(photos) - cached}\n")

        processed = 0
        failed = []
        for i, photo in enumerate(photos, 1):
            print(f"  [{i}/{len(photos)}] {photo.name} ... ", end="", flush=True)
            try:
                result = process_photo(
                    photo, api_key, config, cache_dir,
                    survey_url=args.survey_endpoint, delay=args.delay,
                )
                if result:
                    n_sp = len(result.get("results", {}).get("species", []))
                    print(f"OK ({n_sp} species)")
                    processed += 1
                else:
                    print("SKIP (no result)")
            except QuotaExceededError as e:
                print(f"\n\nQUOTA EXHAUSTED after {processed} images: {e}")
                print("Safe to resume -- cached images will be skipped.")
                break
            except Exception as e:
                print(f"FAIL ({e})")
                failed.append(photo.name)

            if i < len(photos):
                time.sleep(args.delay)

    print(f"\nAPI calls done: {processed} processed, {len(failed)} failed")
    if failed:
        print(f"  Failed: {', '.join(failed[:10])}")

    if args.no_aggregate:
        n_cached = len(list(cache_dir.glob("*.json")))
        print(f"\n--no-aggregate: {n_cached} JSONs in {cache_dir}")
        print("Aggregate locally with:")
        print(f"  python3 predict/aggregate_survey.py --survey-dir {cache_dir}")
        return

    # --- Aggregate (same as 15c) ---
    print("\nAggregating ...")
    json_files = sorted(cache_dir.glob("*.json"))
    if not json_files:
        sys.exit("No cached JSONs to aggregate")

    sys.path.insert(0, str(REPO / "predict"))
    from importlib import import_module
    agg = import_module("aggregate_survey")

    embeddings: dict[str, list[float]] = {}
    dataset_species: dict[str, list] = {}
    for jf in json_files:
        global_key = agg._norm_key(jf.name)
        parsed = agg.parse_survey_json(jf)
        if parsed is None:
            continue
        emb = agg.aggregate_photo_embedding(parsed)
        if emb is not None:
            embeddings[global_key] = emb.tolist()
        if parsed["species"]:
            dataset_species[global_key] = parsed["species"]

    emb_path = out_dir / "survey_embeddings.json"
    with open(emb_path, "w") as f:
        json.dump(embeddings, f)
    print(f"  Embeddings: {len(embeddings)} photos -> {emb_path}")

    import pandas as pd
    from labelfirst.eval.species_priority import batch_scores

    labeled_counts: dict[str, int] = {}
    if args.gt.exists():
        gt = pd.read_csv(args.gt)
        labeled_counts = gt["wcvp_canonical_name"].value_counts().to_dict()
        print(f"  GT: {len(labeled_counts)} species, {len(gt)} labeled")

    scores = batch_scores(
        dataset_species, labeled_counts,
        rare_threshold=args.rare_threshold, method=args.method,
    )
    score_path = out_dir / "survey_species_scores.json"
    with open(score_path, "w") as f:
        json.dump(scores, f)
    print(f"  Scores: {len(scores)} photos -> {score_path}")

    print("\nDone. Rebuild the dashboard over the new cache:")
    print("  python3 dashboard/measure.py && python3 dashboard/build_external.py")
    print(f"  embeddings: {emb_path}")
    print(f"  species scores: {score_path}")


if __name__ == "__main__":
    main()
