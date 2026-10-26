"""
Fetch a 480px-wide WebP thumbnail of every photo the photo pages show.

The pages show only these thumbnails: they carry no full-resolution URL, and
the 4000x3000 JPEGs (about 7.8 MB) sit in private Arbutus buckets. This reads
every frame's key and URL from data/dataset_rows_combined.jsonl, downloads it
with the ARBUTUS_S3_* credentials (predict/photo.py) and writes one small WebP
per photo, resumably: a thumbnail that exists is skipped. It makes network
calls, so like fetch_thumbs.py it is out of bin/refresh.sh.

With --pages DOCS only the photos the built pages in DOCS show are fetched, and
the run fails if any of them still has no thumbnail afterwards. CI uses this to
fill what the thumbs-480 release lacks, so a thumbnail gap never ships silently.

File name is urllib.parse.quote(key, safe="!'()*") + '.webp', the same as
encodeURIComponent(key) + '.webp' in the page JS.

  .venv/bin/python labelling/fetch_photo_thumbs.py --limit 20
  .venv/bin/python labelling/fetch_photo_thumbs.py --workers 6
  python labelling/fetch_photo_thumbs.py --out docs/thumbs/480 --pages docs
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlsplit

REPO = Path(__file__).resolve().parents[1]
# predict/ on the path, so the download is the one predict/embed.py makes.
sys.path.insert(0, str(REPO / "predict"))
sys.path.insert(0, str(REPO / "dashboard"))

from mission_buckets import LEGACY_HOST as HOST
from mission_buckets import UnknownMission
from photo import MissingStorageCredentials, download_image
from PIL import Image, ImageOps

ROWS = REPO / "data" / "dataset_rows_combined.jsonl"
# (page, script id, list name) of the data each built page embeds.
PAGES = (("explorer.html", "explorer-data", "photos"),
         ("embedding-atlas.html", "atlas-data", "points"),
         ("crownfirst-atlas.html", "atlas-data", "points"))
RETRIES = 4
TIMEOUT = 60
MAX_FAIL_FRACTION = 0.01


def thumb_name(key: str) -> str:
    return quote(key, safe="!'()*") + ".webp"  # what encodeURIComponent leaves unescaped


def valid_url(url) -> bool:
    if not isinstance(url, str):
        return False
    u = urlsplit(url)
    return u.scheme == "https" and u.hostname == HOST


def read_photos(path: Path) -> tuple[dict[str, str], int]:
    """Unique global_key to row_data URL, and the count of rows skipped for a bad URL."""
    photos: dict[str, str] = {}
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        key, url = row.get("global_key"), row.get("row_data")
        if not key or key in photos:
            continue
        if valid_url(url):
            photos[key] = url
        else:
            bad += 1
    return photos, bad


def page_keys(docs: Path) -> set[str]:
    """Every key a built page in ``docs`` shows a thumbnail for."""
    keys: set[str] = set()
    for name, script_id, field in PAGES:
        path = docs / name
        if not path.exists():
            continue
        m = re.search(f'<script id="{script_id}" type="application/json">(.*?)</script>',
                      path.read_text(encoding="utf-8"), re.DOTALL)
        if not m:
            raise SystemExit(f"{path}: no <script id=\"{script_id}\"> block")
        keys.update(r["key"] for r in json.loads(m.group(1))[field] if r.get("key"))
    return keys


def download(url: str) -> bytes:
    for attempt in range(RETRIES):
        try:
            return download_image(url, timeout=TIMEOUT)
        except (MissingStorageCredentials, UnknownMission):  # retrying cannot fix either
            raise
        except Exception:
            if attempt == RETRIES - 1:
                raise
            time.sleep(2 ** attempt)


def make_thumb(data: bytes, width: int, quality: int) -> bytes:
    img = Image.open(io.BytesIO(data))
    height = round(width * img.height / img.width)
    img.draft("RGB", (width * 2, height * 2))  # JPEG decodes at 1/2, 1/4 or 1/8 scale
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((width, height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality)
    return buf.getvalue()


def fetch_one(key: str, url: str, out: Path, width: int, quality: int) -> int:
    """Bytes written, or 0 if the thumbnail was already there."""
    dest = out / thumb_name(key)
    if dest.exists():
        return 0
    data = make_thumb(download(url), width, quality)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    return len(data)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rows", type=Path, default=ROWS)
    p.add_argument("--out", type=Path, default=REPO / "data" / "thumbs" / "480")
    p.add_argument("--width", type=int, default=480)
    p.add_argument("--quality", type=int, default=65)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--limit", type=int, help="only the first N photos")
    p.add_argument("--failures", type=Path, help="where to list failed photos (default: beside --out)")
    p.add_argument("--pages", type=Path, metavar="DOCS",
                   help="only photos the built pages in DOCS show; fail if any lacks a thumbnail after")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    photos, bad = read_photos(args.rows)
    wanted = page_keys(args.pages) if args.pages else None
    if wanted is not None:
        photos = {k: u for k, u in photos.items() if k in wanted}
    items = list(photos.items())[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(items)} photos, {bad} skipped for a non-https or non-arbutus URL", flush=True)

    fetched = skipped = total = 0
    failures: list[str] = []
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(fetch_one, k, u, args.out, args.width, args.quality): k
                for k, u in items}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                n = fut.result()
            except Exception as exc:  # noqa: BLE001  (one bad photo must not stop the run)
                failures.append(f"{futs[fut]}\t{type(exc).__name__}: {exc}")
            else:
                if n:
                    fetched, total = fetched + 1, total + n
                else:
                    skipped += 1
            if i % 200 == 0:
                print(f"  [{i}/{len(items)}] {fetched} fetched, {skipped} skipped, "
                      f"{len(failures)} failed", flush=True)

    failures_path = args.failures or args.out.parent / f"failures-{args.out.name}.txt"
    failures_path.write_text("\n".join(failures) + ("\n" if failures else ""), encoding="utf-8")
    mean = total / fetched / 1024 if fetched else 0
    print(f"{fetched} fetched, {skipped} skipped, {len(failures)} failed, "
          f"{total / 1e6:.1f} MB written, mean {mean:.1f} KB; failures in {failures_path}")
    if wanted is not None:
        gaps = sorted(k for k in wanted if not (args.out / thumb_name(k)).exists())
        print(f"{len(gaps)} of {len(wanted)} page photos have no thumbnail")
        return 1 if gaps else 0
    return 1 if len(failures) > MAX_FAIL_FRACTION * max(len(items), 1) else 0


if __name__ == "__main__":
    sys.exit(main())
