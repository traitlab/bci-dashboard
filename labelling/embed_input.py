"""
List the photos in the label queue that need a Pl@ntNet vector.

``predict/embed.py`` reads a two-column file of photos to fetch. This writes
that file for the queue: every tracked frame that carries no botanist label yet.
The labelled side already has its vectors in ``data/embeddings_labelled/``, and
``labelling/rank_queue.py`` compares the two sets, so both have to be keyed the
same way. ``input/boxes/`` names a frame without the ``comb_`` prefix and every
other file in the project keeps it, so the prefix is put back here.

The output is a small superset of the queue: a frame that Pl@ntNet gave no
answer for is tracked and unlabelled but has no place in a queue, so it is
listed here and ignored later. Seventeen frames, against a queue of 3,919.

Stdlib only, and no network call. The fetch is the next step, by hand:

  python3 labelling/embed_input.py
  python3 predict/embed.py --input data/next_batch/queue_for_embed.csv \
      --out-dir data/embeddings_queue

``--named`` lists the other side: every frame that carries a botanist label,
with its photo URL read off the Labelbox inventory, or off ``--export`` for a
frame uploaded since the inventory was drawn. ``bin/refresh_snapshot.py``
runs it after each label merge so a frame named since the labelled embeddings
were drawn gets a vector and anchors the next ranking:

  python3 labelling/embed_input.py --named
  python3 predict/embed.py --input data/next_batch/labelled_for_embed.csv \
      --out-dir data/embeddings_labelled
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FRAMES = REPO / "input" / "boxes" / "bci_images_for_plantnet_w_split.csv"
DEFAULT_LABELS = REPO / "data" / "gt_dominant_taxon.csv"
DEFAULT_OUT = REPO / "data" / "next_batch" / "queue_for_embed.csv"
DEFAULT_INVENTORY = REPO / "data" / "dataset_rows_combined.jsonl"
DEFAULT_NAMED_OUT = REPO / "data" / "next_batch" / "labelled_for_embed.csv"
KEY_PREFIX = "comb_"


def read_column(path: Path, column: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            raise SystemExit(f"{path}: no {column} column")
        return [r[column] for r in reader if r[column]]


def unlabelled_rows(frames: Path, labels: Path) -> list[tuple[str, str]]:
    """``(global_key, image_url)`` for each tracked frame with no label yet.

    A label file key carries the prefix and a frame list key does not, so the
    two are compared with the prefix off and written with it on. The frame list
    has one row per box, so a frame with two crowns in it appears twice and is
    kept once here: the fetch works on the whole photo, not on a box.
    """
    labelled = {k.removeprefix(KEY_PREFIX) for k in read_column(labels, "global_key")}
    with open(frames, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"global_key", "image_url"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{frames}: missing column(s) {sorted(missing)}")
        seen, out = set(), []
        for r in reader:
            key = r["global_key"]
            if not key or key in labelled or key in seen:
                continue
            seen.add(key)
            out.append((KEY_PREFIX + key, r["image_url"]))
        return out


def export_urls(paths) -> dict[str, str]:
    """``global_key`` -> photo URL from Labelbox export NDJSON, keyed like the GT."""
    url = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)["data_row"]
                if row.get("row_data"):
                    url[KEY_PREFIX + row["global_key"].rsplit("/", 1)[-1]] = row["row_data"]
    return url


def named_rows(labels: Path, inventory: Path, exports=()) -> list[tuple[str, str]]:
    """``(global_key, image_url)`` for each named frame the inventory can place.

    The label file is keyed the way every other file is, so no prefix work.
    A named frame missing from the inventory has no photo URL to fetch, so it
    is left out, and the caller is told how many were. The inventory wins
    where both have a URL, so a frame keeps the photo its cached vector came
    from; the exports only fill frames the inventory predates.
    """
    url = export_urls(exports)
    with open(inventory, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                if row.get("global_key") and row.get("row_data"):
                    url[row["global_key"]] = row["row_data"]
    named = dict.fromkeys(read_column(labels, "global_key"))
    out = [(k, url[k]) for k in named if k in url]
    print(f"{len(named) - len(out)} named frames have no photo URL in {inventory.name}")
    return out


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", type=Path, default=DEFAULT_FRAMES,
                   help="the tracked frame list, which defines the population")
    p.add_argument("--labels", type=Path, default=DEFAULT_LABELS,
                   help="one row per frame a botanist has already named")
    p.add_argument("--out", type=Path, default=None,
                   help="default: queue_for_embed.csv, or labelled_for_embed.csv with --named")
    p.add_argument("--named", action="store_true",
                   help="list the named frames instead, with URLs from --inventory")
    p.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                   help="Labelbox inventory, one JSON row per frame with its photo URL")
    p.add_argument("--export", type=Path, action="append", default=[],
                   help="Labelbox export NDJSON, repeatable; fills URLs the inventory lacks")
    args = p.parse_args(argv)
    if args.out is None:
        args.out = DEFAULT_NAMED_OUT if args.named else DEFAULT_OUT
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.named:
        rows = named_rows(args.labels, args.inventory, args.export)
        if not rows:
            raise SystemExit("no named frame has a photo URL; nothing to embed")
    else:
        rows = unlabelled_rows(args.frames, args.labels)
        if not rows:
            raise SystemExit("every tracked frame carries a label; nothing to embed")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "image_url"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
