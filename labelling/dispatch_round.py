"""Dispatch a round selection to Labelbox Project B.

Reads a selection CSV (from the send-first queue (dashboard/measure.py)), upserts a
``selection_round`` metadata field on the chosen data rows, and creates
a labelling batch in Project B.

Safety: only CREATES new batches and upserts metadata. Never deletes,
modifies, or moves existing resources. Follows the three-stage protocol
(--test for 5 rows, then full).

Usage:
    # Stage 1 — test with 5 rows:
    python labelling/dispatch_round.py \\
        --round 1 --csv data/round_01_coreset_selection.csv --test

    # Stage 2 — full dispatch:
    python labelling/dispatch_round.py \\
        --round 1 --csv data/round_01_coreset_selection.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import labelbox as lb
import settings

# How many metadata rows go up in one bulk_upsert call. Not the botanist-session
# batch size: `queues.BATCH_SIZE` is that one, and it is a different number for a
# different reason, so the two do not share a name.
UPSERT_CHUNK = 500
EXPORT_TIMEOUT_SEC = 300
METADATA_SCHEMA_NAME = "selection_round"


def load_selection_csv(csv_path: Path) -> list[str]:
    global_keys = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gk = row["global_key"].strip()
            if gk:
                global_keys.append(gk)
    return global_keys


def get_or_create_round_schema(mdo) -> str:
    existing = mdo.get_by_name(METADATA_SCHEMA_NAME)
    if existing:
        return existing.uid
    from labelbox.schema.data_row_metadata import DataRowMetadataKind
    schema = mdo.create_schema(
        name=METADATA_SCHEMA_NAME,
        kind=DataRowMetadataKind.number,
    )
    print(f"  Created metadata schema '{METADATA_SCHEMA_NAME}' (id={schema.uid})")
    return schema.uid


def fetch_data_row_ids(client: lb.Client, dataset_name: str) -> dict[str, str]:
    dataset = next((d for d in client.get_datasets() if d.name == dataset_name), None)
    if dataset is None:
        sys.exit(f"ERROR: Dataset '{dataset_name}' not found.")

    export_task = dataset.export(params={
        "attachments": False,
        "metadata_fields": False,
        "data_row_details": True,
        "embeddings": False,
        "labels": False,
    })
    export_task.wait_till_done(timeout_seconds=EXPORT_TIMEOUT_SEC)

    try:
        errors = []
        export_task.get_buffered_stream(stream_type=lb.StreamType.ERRORS).start(
            stream_handler=lambda output: errors.append(output.json)
        )
        if errors:
            sys.exit(f"ERROR: Export failed: {errors}")
    except ValueError:
        pass

    key_to_id = {}
    export_task.get_buffered_stream(stream_type=lb.StreamType.RESULT).start(
        stream_handler=lambda output: key_to_id.update({
            output.json["data_row"]["global_key"]: output.json["data_row"]["id"]
        }) if "data_row" in output.json else None
    )
    return key_to_id


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--round", type=int, required=True, help="round number (1, 2, ...)")
    ap.add_argument("--csv", type=Path, required=True, help="selection CSV from the send-first queue (dashboard/measure.py)")
    ap.add_argument("--test", action="store_true", help="process first 5 rows only (Stage 1)")
    ap.add_argument("--priority", type=int, default=1, choices=[1, 2, 3, 4, 5],
                    help="labelling priority (1=highest, default 1)")
    args = ap.parse_args()

    if not args.csv.exists():
        sys.exit(f"ERROR: {args.csv} not found.")

    api_key = settings.api_key()

    config = settings.load_config()
    combined_dataset_name = config["labelbox"]["combined_dataset_name"]
    project_b_name = config["labelbox"]["project_b_name"]

    global_keys = load_selection_csv(args.csv)
    if args.test:
        global_keys = global_keys[:5]
        print(f"TEST MODE: processing {len(global_keys)} rows only")
    print(f"Step 1 - Loaded {len(global_keys)} global keys from {args.csv}")

    client = lb.Client(api_key=api_key)

    print(f"\nStep 2 - Fetching data row IDs from '{combined_dataset_name}'...")
    key_to_id = fetch_data_row_ids(client, combined_dataset_name)
    print(f"  Exported {len(key_to_id)} data rows")

    missing = [gk for gk in global_keys if gk not in key_to_id]
    if missing:
        print(f"  WARNING: {len(missing)} keys not found in dataset (first 5: {missing[:5]})")
    matched_keys = [gk for gk in global_keys if gk in key_to_id]
    if not matched_keys:
        sys.exit("ERROR: No matching data rows found.")

    print(f"\nStep 3 - Upserting '{METADATA_SCHEMA_NAME}' = {args.round} on {len(matched_keys)} rows...")
    mdo = client.get_data_row_metadata_ontology()
    schema_id = get_or_create_round_schema(mdo)

    updates = []
    for gk in matched_keys:
        updates.append(lb.DataRowMetadata(
            data_row_id=key_to_id[gk],
            fields=[lb.DataRowMetadataField(
                schema_id=schema_id,
                value=float(args.round),
            )],
        ))

    for i in range(0, len(updates), UPSERT_CHUNK):
        batch = updates[i:i + UPSERT_CHUNK]
        mdo.bulk_upsert(batch)
        print(f"  Batch {i // UPSERT_CHUNK + 1}: {len(batch)} rows tagged")

    print(f"\nStep 4 - Creating labelling batch in Project B...")
    project = next(
        (p for p in client.get_projects() if p.name == project_b_name), None
    )
    if project is None:
        sys.exit(f"ERROR: Project '{project_b_name}' not found.")

    batch_name = f"Round {args.round} - {date.today().isoformat()}"
    batch = project.create_batch(
        name=batch_name,
        global_keys=matched_keys,
        priority=args.priority,
    )
    print(f"  Created batch: {batch.name} ({len(matched_keys)} data rows, priority={args.priority})")

    print(f"\n{'=' * 50}")
    print("DISPATCH COMPLETE")
    print(f"{'=' * 50}")
    print(f"  Round:          {args.round}")
    print(f"  Batch:          {batch_name}")
    print(f"  Data rows:      {len(matched_keys)}")
    print(f"  Missing keys:   {len(missing)}")
    print(f"  Project:        {project_b_name}")
    print(f"  Metadata field: {METADATA_SCHEMA_NAME} = {args.round}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
