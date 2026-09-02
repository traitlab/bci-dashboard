"""
Fetch a small picture of each photo at the head of the queue.

The queue page can say a photo is next, but it cannot show it. Every number on
that page is about frames nobody reading it has seen, and "least like everything
already labelled" is a claim about how things *look*, which is the one claim a
table cannot carry. This writes one small JPEG per queued frame so the page can
put the head of each queue on screen.

The picture is the **centre crop**, taken with ``predict/photo.center_crop_jpeg``,
the one crop in this repo. That is deliberate: it is the region Pl@ntNet scored
and embedded, so what a reader sees is what the ordering was decided on, not a
wider frame that would flatter it.

This makes network calls and reads no credential. It is out of ``bin/refresh.sh``
for the same reason ``predict/embed.py`` is. It resumes: a frame whose thumbnail
already exists at the requested size is skipped, so a stopped run costs nothing.

  .venv/bin/python labelling/fetch_thumbs.py
  .venv/bin/python labelling/fetch_thumbs.py --per-queue 12 --size 112
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# predict/ on the path, so the crop below is the one predict/embed.py took and
# not a second one written here. Same shape as labelling/rank_queue.py.
sys.path.insert(0, str(REPO / "predict"))

from PIL import Image
from photo import center_crop_jpeg_box, download_image

DEFAULT_QUEUE = REPO / "build" / "tables" / "send_first_queue.csv"
DEFAULT_FRAMES = REPO / "input" / "boxes" / "bci_images_for_plantnet_w_split.csv"
DEFAULT_OUT = REPO / "data" / "thumbs"
KEY_PREFIX = "comb_"
# 78 is where the artefacts around a leaf edge stop being visible at this size.
# Measured, not guessed: at 112 px, quality 70 shows blocking on bright sky and
# quality 90 costs 2.4x the bytes for a picture nobody zooms into.
JPEG_QUALITY = 78


def head_of_each_queue(path: Path, per_queue: int) -> list[tuple[str, str]]:
    """The first ``per_queue`` keys of every queue, in the order the file has.

    The file is already sorted the way the page shows it, so reading it in order
    is the same answer the page gives. Nothing is re-sorted here: a second sort
    would be a second opinion about the queue, and the page's is the one that
    matters.
    """
    out: list[tuple[str, str]] = []
    seen: dict[str, int] = defaultdict(int)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"queue", "global_key"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing column(s) {sorted(missing)}")
        for row in reader:
            q = row["queue"]
            if seen[q] >= per_queue:
                continue
            seen[q] += 1
            out.append((q, row["global_key"]))
    return out


def frame_urls(path: Path) -> dict[str, str]:
    """Key to image URL. The frame list has a row per box, so the first URL for
    a key wins; every row for one frame names the same file."""
    urls: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            urls.setdefault(KEY_PREFIX + row["global_key"], row["image_url"])
    return urls


def thumbnail(image_bytes: bytes, size: int) -> bytes:
    jpeg, _, _, _ = center_crop_jpeg_box(image_bytes)
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--queue-csv", type=Path, default=DEFAULT_QUEUE)
    p.add_argument("--frames-csv", type=Path, default=DEFAULT_FRAMES)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--per-queue", type=int, default=12,
                   help="how many frames from the head of each queue")
    p.add_argument("--size", type=int, default=112, help="pixels, square")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    wanted = head_of_each_queue(args.queue_csv, args.per_queue)
    urls = frame_urls(args.frames_csv)
    out_dir = args.out_dir / str(args.size)
    out_dir.mkdir(parents=True, exist_ok=True)

    fetched = skipped = 0
    errors: list[str] = []
    for queue, key in wanted:
        dest = out_dir / f"{key}.jpg"
        if dest.exists():
            skipped += 1
            continue
        url = urls.get(key)
        if not url:
            errors.append(f"{key}: no image URL in {args.frames_csv.name}")
            continue
        try:
            dest.write_bytes(thumbnail(download_image(url), args.size))
        except Exception as exc:  # noqa: BLE001  (one bad frame must not stop the run)
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
            continue
        fetched += 1
        print(f"  [{fetched + skipped}/{len(wanted)}] {queue} {key}")

    total = sum(p.stat().st_size for p in out_dir.glob("*.jpg"))
    print(f"{fetched} fetched, {skipped} already there, {len(errors)} failed")
    print(f"{len(list(out_dir.glob('*.jpg')))} thumbnails in {out_dir}, "
          f"{total / 1024:.0f} KB on disk")
    for e in errors:
        print(f"  ! {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
