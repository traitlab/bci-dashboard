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
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from photo import (
    API_TIMEOUT,
    CROP_SIZE,
    QuotaExceededError,
    api_and_project,
    center_crop_jpeg_box,
    load_config,
    post_image,
    with_retry,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data"

DEFAULT_DELAY = 0.5

# One call runs 140 sub-queries over a whole frame, so it is not a 60s job.
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


def call_identify(jpeg_bytes: bytes, filename: str, api_key: str,
                  api_url: str, nb_results: int, organs: str,
                  lang: str) -> dict:
    """One identify call. Every request setting comes from config.yaml.

    `organs` and `lang` come from the settings, not from literals here: typed
    out, this path once asked for different organs and a different common-name
    language than `predict/photo.py`, silently.
    """
    return post_image(api_url, "images", jpeg_bytes, filename,
                 params={"api-key": api_key, "nb-results": nb_results,
                         "no-reject": "true", "include-related-images": "false",
                         "lang": lang},
                 data={"organs": organs})


def call_embeddings(jpeg_bytes: bytes, filename: str, api_key: str,
                    api_url: str) -> dict:
    return post_image(api_url, "image", jpeg_bytes, filename,
                 params={"api-key": api_key})


def survey_tiles_url(config=None) -> str:
    """The quadrat endpoint for the project config.yaml names.

    The path documented as /v2/survey/<project> returns 404; this is the one
    that answers, and the trailing 'tiles' is the flavor. Built from the same
    setting the identify calls use, so the two arms cannot end up on different
    projects.
    """
    base, project = api_and_project(config)
    return f"{base}/survey/tiles/{project}"


def call_survey(jpeg_bytes: bytes, filename: str, api_key: str,
                survey_url: str | None = None) -> dict:
    """Quadrat: the API slides a 518px window over the whole frame itself.

    The field is 'image', singular, unlike identify's 'images'. The plural
    returns HTTP 400 '"image" is required', which reads as the endpoint being
    unavailable on this key. 'organs' is not accepted here either.

    Verified 2026-08-15 against a 4000x3000 frame: 140 sub-queries at
    tile_size 518 / tile_stride 259, and the quadrat quota counter did not move.
    """
    return post_image(survey_url or survey_tiles_url(), "image", jpeg_bytes, filename,
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


def process_image(
    filename: str,
    read_bytes,
    api_key: str,
    config: dict,
    cache_dir: Path,
    survey_url: str | None = None,
    delay: float = DEFAULT_DELAY,
) -> dict | None:
    """One photo, cached under ``filename``. ``read_bytes`` returns its pixels.

    A local file and a URL differ only in that call, so both modes run this:
    a second copy of the crop, the two calls and the atomic cache write is how
    the streaming path once stopped recording the crop rectangle.
    """
    cache_file = cache_dir / f"{filename}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    jpeg_bytes, orig_w, orig_h, crop_box = center_crop_jpeg_from_bytes(read_bytes())

    if survey_url:
        result = with_retry(call_survey, jpeg_bytes, filename, api_key,
                                      survey_url)
    else:
        pn_cfg = config["plantnet"]
        id_resp = with_retry(
            call_identify, jpeg_bytes, filename, api_key, pn_cfg["identify_url"],
            pn_cfg["identify_nb_results"], pn_cfg["identify_organs"], pn_cfg["identify_lang"]
        )
        time.sleep(delay)
        emb_resp = with_retry(
            call_embeddings, jpeg_bytes, filename, api_key, pn_cfg["embeddings_api_url"]
        )
        result = identify_to_survey_json(id_resp, emb_resp)

    stamp_geometry(result, orig_w, orig_h, crop_box)

    tmp = cache_file.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(result, f)
    tmp.replace(cache_file)
    return result


def parse_args():
    """One source of photos, a local directory or a CSV of URLs, and the knobs
    for how they are called and scored."""
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
    return ap.parse_args()


def photo_sources(args):
    """Pair every photo with a way to get its bytes, without getting them yet.

    Each entry is a name and a callable. In CSV mode the callable downloads from
    the bucket when the photo is due, so a run streams and never writes image
    data to disk. Returns the pairs and the words to add to the run banner.
    """
    if args.csv:
        rows = load_csv_urls(args.csv)
        if not rows:
            sys.exit(f"No valid rows in {args.csv}")
        return ([(gk, lambda url=url: download_image_bytes(url)) for gk, url in rows],
                " (streaming from URLs)")

    files = sorted(p for p in args.photos.iterdir()
                   if p.suffix.lower() in IMG_EXTENSIONS)
    if not files:
        sys.exit(f"No image files found in {args.photos}")
    return [(p.name, p.read_bytes) for p in files], ""


def fetch_all(photos, api_key, config, cache_dir, *, survey_url, delay):
    """Call the API once per photo, cache as you go, and say so on every line.

    A run is long enough to be watched, so each photo prints its own result
    rather than a bar. A quota refusal stops the loop and is safe to resume
    from, because the cache is what the next run skips on.
    """
    processed, failed = 0, []
    for i, (name, read_bytes) in enumerate(photos, 1):
        print(f"  [{i}/{len(photos)}] {name} ... ", end="", flush=True)
        try:
            result = process_image(
                name, read_bytes, api_key, config, cache_dir,
                survey_url=survey_url, delay=delay,
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
            failed.append(name)

        if i < len(photos):
            time.sleep(delay)
    return processed, failed


def read_cache(cache_dir):
    """One embedding and one species list per cached photo, skipping the
    unparseable. Reads the whole cache, not this run: two half-runs aggregate
    into the same thing one whole run would have."""
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
    return embeddings, dataset_species


def score_photos(dataset_species, args, out_dir):
    """Rank photos by how much labelling them would buy, against what is labelled.

    The count of existing labels comes from the GT file, so a photo full of
    species the botanists have already named scores low and a photo of something
    rare scores high. Missing GT is not an error: everything is rare then.
    """
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
    return score_path


def main() -> None:
    """Fetch what is missing, then aggregate the whole cache into embeddings and
    priority scores. --no-aggregate stops after the fetch, for when the calls
    happen on one machine and the numpy work on another."""
    args = parse_args()
    load_dotenv()
    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        sys.exit("ERROR: PLANTNET_API_KEY not found in .env")

    config = load_config()
    out_dir = args.out_dir
    cache_dir = out_dir / "cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    photos, streaming = photo_sources(args)
    if args.test:
        photos = photos[:1]
        print("TEST MODE: 1 image only\n")

    mode = "survey" if args.survey_endpoint else "identify+embeddings"
    cached = sum(1 for name, _ in photos if (cache_dir / f"{name}.json").exists())
    print(f"Ingesting {len(photos)} photos via {mode}{streaming}")
    print(f"  Cached: {cached}, remaining: {len(photos) - cached}\n")

    processed, failed = fetch_all(
        photos, api_key, config, cache_dir,
        survey_url=args.survey_endpoint, delay=args.delay)

    print(f"\nAPI calls done: {processed} processed, {len(failed)} failed")
    if failed:
        print(f"  Failed: {', '.join(failed[:10])}")

    if args.no_aggregate:
        n_cached = len(list(cache_dir.glob("*.json")))
        print(f"\n--no-aggregate: {n_cached} JSONs in {cache_dir}")
        print("Aggregate locally with:")
        print(f"  python3 predict/aggregate_survey.py --survey-dir {cache_dir}")
        return

    print("\nAggregating ...")
    embeddings, dataset_species = read_cache(cache_dir)

    emb_path = out_dir / "survey_embeddings.json"
    with open(emb_path, "w") as f:
        json.dump(embeddings, f)
    print(f"  Embeddings: {len(embeddings)} photos -> {emb_path}")

    score_path = score_photos(dataset_species, args, out_dir)

    print("\nDone. Rebuild the dashboard over the new cache:")
    print("  python3 dashboard/measure.py && python3 dashboard/build_external.py")
    print(f"  embeddings: {emb_path}")
    print(f"  species scores: {score_path}")


if __name__ == "__main__":
    main()
