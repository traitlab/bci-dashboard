"""
Fetch a 480px-wide WebP thumbnail of every photo the photo pages show.

The explorer and atlas pages embed the full 4000x3000 JPEG URL (about 7.8 MB)
for cards a few hundred pixels wide. This reads those URLs out of the built
pages and writes one small WebP per photo, resumably: a thumbnail that exists
is skipped. It makes network calls, so like fetch_thumbs.py it is out of
bin/refresh.sh.

File name is urllib.parse.quote(key, safe="!'()*") + '.webp', the same as
encodeURIComponent(key) + '.webp' in the page JS.

  .venv/bin/python labelling/fetch_photo_thumbs.py --limit 20
  .venv/bin/python labelling/fetch_photo_thumbs.py --workers 6
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlsplit

from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
# (page, script id, list name)
PAGES = [("explorer.html", "explorer-data", "photos"),
         ("embedding-atlas.html", "atlas-data", "points"),
         ("crownfirst-atlas.html", "atlas-data", "points")]
HOST = "object-arbutus.cloud.computecanada.ca"
USER_AGENT = "bci-dashboard-thumbnails (traitlab)"
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


def read_photos(paths: list[Path]) -> tuple[dict[str, str], int]:
    """Unique key to URL across the pages, and the count of rows skipped for a bad URL."""
    photos: dict[str, str] = {}
    bad = 0
    for path, (_, script_id, field) in zip(paths, PAGES):
        html = path.read_text(encoding="utf-8")
        m = re.search(f'<script id="{script_id}" type="application/json">(.*?)</script>',
                      html, re.DOTALL)
        if not m:
            raise SystemExit(f"{path}: no <script id=\"{script_id}\"> block")
        for row in json.loads(m.group(1))[field]:
            key, url = row.get("key"), row.get("image")
            if not key or key in photos:
                continue
            if valid_url(url):
                photos[key] = url
            else:
                bad += 1
    return photos, bad


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
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
    p.add_argument("--pages", type=Path, nargs=3, default=[DOCS / n for n, _, _ in PAGES],
                   metavar=("EXPLORER", "ATLAS", "CROWNFIRST"))
    p.add_argument("--out", type=Path, default=REPO / "data" / "thumbs" / "480")
    p.add_argument("--width", type=int, default=480)
    p.add_argument("--quality", type=int, default=65)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--limit", type=int, help="only the first N photos")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    photos, bad = read_photos(args.pages)
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

    failures_path = args.out.parent / f"failures-{args.out.name}.txt"
    failures_path.write_text("\n".join(failures) + ("\n" if failures else ""), encoding="utf-8")
    mean = total / fetched / 1024 if fetched else 0
    print(f"{fetched} fetched, {skipped} skipped, {len(failures)} failed, "
          f"{total / 1e6:.1f} MB written, mean {mean:.1f} KB; failures in {failures_path}")
    return 1 if len(failures) > MAX_FAIL_FRACTION * max(len(items), 1) else 0


if __name__ == "__main__":
    sys.exit(main())
