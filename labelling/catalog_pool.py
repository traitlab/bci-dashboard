"""Rebuild the catalog pool from the Labelbox dataset, so new photos enter by themselves.

The pool (`data/predictions_catalog_2026/input.csv`, read by `catalog_batches.py`) was a
hand-built snapshot in the encrypted bundle. It is now the rows of dataset `2024_bci` that
sit in none of the weekly project exports. The catalog keys a frame by file name, the
dataset by `<flight folder>/<file>`, so both sides are compared and written by file name,
as `record_sends.py` does. A file name seen twice in the dataset keeps its first row,
because `catalog_batches.read_pool` stops on a repeated key.

Pl@ntNet is then called only for photos the per-photo cache lacks (`predict/photo.py`
skips cached ones), so the bundled cache stays the seed. photo.py's `--max-calls` caps one
run; the rest follows on later runs.

Strictly read-only: no Labelbox write call. It never fails the refresh. With no key, no
export, an empty listing or an API error the bundled input.csv is left as it is and the
log says so, the same contract as `check_photo_links.py`.

    LABELBOX_API_KEY=... PLANTNET_API_KEY=... python labelling/catalog_pool.py \\
        --export data/exports/01_x.ndjson [--export ...] [--pool-dir data/predictions_catalog_2026]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from check_photo_links import dataset_rows, make_client

POOL_DIR = "data/predictions_catalog_2026"
REPO = Path(__file__).resolve().parents[1]


def name_of(global_key: str) -> str:
    return global_key.rsplit("/", 1)[-1]


def in_a_project(exports) -> set[str]:
    """File names of every row in the exports: each export row sits in a project."""
    keys: set[str] = set()
    for path in exports:
        with open(path, encoding="utf-8") as f:
            keys.update(name_of(json.loads(line)["data_row"]["global_key"])
                        for line in f if line.strip())
    return keys


def pool_rows(rows, taken: set[str]) -> list[tuple[str, str]]:
    """(file name, row_data) for the dataset rows outside `taken`, first one per name."""
    pool: dict[str, str] = {}
    for r in rows:
        name = name_of(r.global_key)
        if name not in taken and r.row_data:
            pool.setdefault(name, r.row_data)
    return list(pool.items())


def write_pool(path: Path, pool: list[tuple[str, str]]) -> None:
    """The columns of the existing input.csv, swapped in whole so a crash keeps the old one."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "image_url"])
        w.writerows(pool)
    tmp.replace(path)


def rebuild(pool_dir: Path, exports, client_factory=make_client) -> int:
    """Rewrite pool_dir/input.csv from the live dataset; returns the row count."""
    key = os.environ.get("LABELBOX_API_KEY")
    if not key:
        raise RuntimeError("LABELBOX_API_KEY is not set")
    if not exports:
        raise RuntimeError("no project export, so the rows already in a project are unknown")
    pool = pool_rows(dataset_rows(client_factory(key)), in_a_project(exports))
    if not pool:
        raise RuntimeError("the live listing left no pool rows")
    write_pool(pool_dir / "input.csv", pool)
    return len(pool)


def fetch_answers(pool_dir: Path) -> None:
    """Pl@ntNet answers for the photos the cache lacks. photo.py reads the key and stops
    without one; a failure either way keeps what was cached."""
    done = subprocess.run([sys.executable, str(REPO / "predict" / "photo.py"),
                           "--input", str(pool_dir / "input.csv"), "--out-dir", str(pool_dir)],
                          check=False)
    if done.returncode:
        print(f"catalog pool: photo.py exited {done.returncode}; the answers cached so far stay")


def listing_failures() -> tuple[type[BaseException], ...]:
    """What a live listing can raise: a missing SDK, the network (requests errors are
    OSError), a bad export line, our own checks, and the SDK's API errors."""
    known: tuple[type[BaseException], ...] = (ImportError, OSError, ValueError, KeyError,
                                              RuntimeError, LookupError)
    try:
        from lbox.exceptions import LabelboxError
    except ImportError:
        return known
    return (*known, LabelboxError)


def run(pool_dir: Path, exports, client_factory=make_client, fetch=fetch_answers) -> bool:
    try:
        n = rebuild(pool_dir, exports, client_factory)
    except listing_failures() as exc:  # never fail the refresh
        # The class name only: SDK messages can carry signed URLs or the key.
        reason = str(exc) if isinstance(exc, (RuntimeError, LookupError)) else type(exc).__name__
        print(f"catalog pool: kept the bundled snapshot, live listing failed: {reason}")
        return False
    print(f"catalog pool: {n:,} dataset rows in no project written to {pool_dir / 'input.csv'}")
    fetch(pool_dir)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", type=Path, action="append", default=[],
                    help="Labelbox project export (ndjson); repeat for several")
    ap.add_argument("--pool-dir", type=Path, default=Path(POOL_DIR))
    args = ap.parse_args(argv)
    run(args.pool_dir, args.export)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
