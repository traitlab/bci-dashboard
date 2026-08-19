"""Inventory the Labelbox dataset with a read-only key.

Pages every data row in the ``2024_bci`` dataset and writes one JSON object per
row to ``data/dataset_rows.jsonl``. This is the one network call in the
selection path; everything downstream (``labelling/next_batch.py``) runs offline
against the cached file, the same way the dashboard runs offline against a
project export.

Why paging rather than ``dataset.export()``: a read-only key cannot create an
export task, for a dataset any more than for a project. ``data_rows()`` is a
plain paged read and is permitted. The cost is that embeddings and annotations
are not reachable this way, only identifiers, media attributes, and metadata.

Usage:
    python labelling/fetch_dataset.py
    python labelling/fetch_dataset.py --dataset-id <id> --out data/other.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import labelbox as lb
from dotenv import load_dotenv

DATASET_ID = "cmon3zoss00wu0705ertl0vd7"  # 2024_bci
OUT_PATH = "data/dataset_rows.jsonl"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset-id", default=DATASET_ID)
    p.add_argument("--out", default=OUT_PATH)
    return p.parse_args(argv)


def row_to_dict(row) -> dict:
    metadata = {}
    for field in (row.metadata_fields or []):
        metadata[field.get("name")] = field.get("value")
    return {
        "uid": row.uid,
        "global_key": row.global_key,
        "external_id": row.external_id,
        "row_data": row.row_data,
        "media_attributes": row.media_attributes,
        "metadata": metadata,
        "created_at": str(row.created_at),
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    load_dotenv()
    api_key = os.environ.get("LABELBOX_API_KEY")
    if not api_key:
        print("MISSING LABELBOX_API_KEY", file=sys.stderr)
        return 2

    client = lb.Client(api_key=api_key)
    dataset = client.get_dataset(args.dataset_id)
    print(f"dataset {dataset.name} ({dataset.uid}), row_count={dataset.row_count}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    started = time.time()
    written = 0
    with open(args.out, "w") as out:
        for row in dataset.data_rows():
            out.write(json.dumps(row_to_dict(row)) + "\n")
            written += 1
            if written % 500 == 0:
                print(f"  {written} rows  {time.time() - started:.0f}s", flush=True)

    print(f"wrote {written} rows to {args.out} in {time.time() - started:.0f}s")
    if written != dataset.row_count:
        print(f"WARNING: paged {written} rows but row_count reports "
              f"{dataset.row_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
