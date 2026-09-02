"""
Pl@ntNet embeddings, one 768-dim vector per photo.

Calls the embeddings endpoint config.yaml names. This is a *different* endpoint from
/v2/identify and it does not draw on the daily identify credits, so the whole
unsent pool can be embedded without competing with the prediction runs.

An embedding is what the active-learning selectors need. Labelbox can store one
per data row, but reading it back needs an export task, which the current key
cannot create. Computing it here from the image pixels sidesteps that entirely:
the vector is the model's, not Labelbox's, and Labelbox is only ever a place to
put it.

Reuses the download, centre-crop, and cache-naming helpers from photo.py so the
two runs crop identically and their caches key the same way.

Input:
  data/next_batch/unsent_for_plantnet.csv   (global_key, image_url)

Output:
  data/embeddings/cache/<global_key>.json:  per-image cache
  data/embeddings/embeddings.npz:           keys + float32 matrix

Usage:
  python predict/embed.py --test
  python predict/embed.py
  python predict/embed.py --input data/next_batch/unsent_for_plantnet.csv
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from photo import (
    QuotaExceededError,
    cache_name,
    center_crop_jpeg,
    download_image,
    load_config,
    load_image_list,
    post_image,
    save_cache,
    with_retry,
)

EMBEDDING_DIMS = 768
DEFAULT_DELAY = 0.5
DEFAULT_INPUT = "data/next_batch/unsent_for_plantnet.csv"
DEFAULT_OUT   = "data/embeddings"


def call_embeddings_api(jpeg_bytes: bytes, filename: str, api_key: str,
                        api_url: str) -> dict:
    """Post one crop to the embeddings endpoint. ``api_url`` comes from
    config.yaml, the same place ingest_photos.py reads it: an endpoint typed
    here as well would keep posting to the old one after a Pl@ntNet move.

    The post, the retry and the 429 come from photo.py, so this path stops and
    resumes on a spent key exactly the way the other two do.
    """
    return with_retry(post_image, api_url, "image", jpeg_bytes, filename,
                      params={"api-key": api_key})


def extract_embedding(response: dict) -> list[float]:
    """Pull the vector out of an /v2/embeddings response.

    v7.5 returns a flat list of floats under ``embeddings``. Older tile-style
    responses returned one dict per tile; those are mean-pooled and re-normalised
    so a caller downstream cannot tell the two apart.
    """
    vec = response.get("embeddings")
    if not isinstance(vec, list) or not vec:
        raise ValueError(f"no embedding in response, keys={list(response)}")
    if isinstance(vec[0], dict):
        tiles = np.asarray([t["embeddings"] for t in vec], dtype=np.float64)
        pooled = tiles.mean(axis=0)
        norm = np.linalg.norm(pooled)
        return (pooled / norm if norm else pooled).tolist()
    return [float(v) for v in vec]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default=DEFAULT_INPUT)
    p.add_argument("--out-dir", default=DEFAULT_OUT)
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    p.add_argument("--test", action="store_true", help="one image, verbose")
    return p.parse_args(argv)


def fetch_all(todo, api_key, api_url, cache_dir, *, delay, test):
    """One embedding call per photo, each answer cached as it lands.

    The narrow except is deliberate. One unreachable URL or undecodable JPEG
    must not end a 3,000-image run, and anything outside that set is a bug that
    should propagate rather than be counted as an error and skipped.
    """
    ok = errors = 0
    for i, row in enumerate(todo):
        gk = row["global_key"]
        try:
            jpeg, w, h, crop_s = center_crop_jpeg(download_image(row["image_url"]))
            response = call_embeddings_api(jpeg, f"{gk}.jpg", api_key, api_url)
            entry = {
                "global_key":    gk,
                "image_url":     row["image_url"],
                "embedding":     extract_embedding(response),
                "version":       response.get("version"),
                "orig_width":    w,
                "orig_height":   h,
                "crop_size":     crop_s,
            }
            save_cache(cache_dir / f"{cache_name(gk)}.json", entry)
            ok += 1
            if test:
                print(json.dumps({k: v for k, v in entry.items()
                                  if k != "embedding"}, indent=2))
                print(f"embedding dims: {len(entry['embedding'])}")
            elif (i + 1) % 100 == 0 or i == 0:
                print(f"  [{i+1}/{len(todo)}] {gk}", flush=True)
        except QuotaExceededError as e:
            print(f"QUOTA EXCEEDED: {e}. Re-run to resume.", file=sys.stderr)
            break
        except (requests.RequestException, OSError, ValueError, RuntimeError) as e:
            errors += 1
            print(f"  [{i+1}/{len(todo)}] ERROR {gk}: {e}", file=sys.stderr)
        if i < len(todo) - 1:
            time.sleep(delay)
    return ok, errors


def write_matrix(cache_dir, out_dir):
    """Stack the cache into one array, dropping any vector of the wrong length.

    A short vector is a truncated answer, not a photo with less to say. Loading
    it would put a row of the wrong width into a matrix nothing downstream
    re-checks, so it is named on stderr and left out.
    """
    keys, vectors = [], []
    for p in sorted(cache_dir.glob("*.json")):
        entry = json.loads(p.read_text(encoding="utf-8"))
        vec = entry.get("embedding")
        if not vec or len(vec) != EMBEDDING_DIMS:
            print(f"  SKIP {p.name}: {len(vec) if vec else 0} dims", file=sys.stderr)
            continue
        keys.append(entry["global_key"])
        vectors.append(vec)

    npz_path = out_dir / "embeddings.npz"
    np.savez_compressed(npz_path, keys=np.array(keys),
                        embeddings=np.asarray(vectors, dtype=np.float32))
    return npz_path, len(keys)


def main(argv=None) -> int:
    """Fetch the embeddings that are missing, then write the whole cache as one
    array. Resumable: the cache is what a second run skips on."""
    args = parse_args(argv)
    load_dotenv()
    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        print("MISSING PLANTNET_API_KEY", file=sys.stderr)
        return 2

    api_url = load_config()["plantnet"]["embeddings_api_url"]
    out_dir   = Path(args.out_dir)
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows = load_image_list(Path(args.input))
    if args.test:
        rows = rows[:1]
    cached = {p.stem for p in cache_dir.glob("*.json")}
    todo = [r for r in rows if cache_name(r["global_key"]) not in cached]
    print(f"{len(rows)} images, {len(cached)} cached, {len(todo)} to fetch")

    ok, errors = fetch_all(todo, api_key, api_url, cache_dir,
                           delay=args.delay, test=args.test)
    npz_path, n = write_matrix(cache_dir, out_dir)
    print(f"fetched {ok}, errors {errors}, wrote {n} vectors to {npz_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
