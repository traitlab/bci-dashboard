"""Dispatch a round selection to Labelbox Project B.

Reads a selection CSV (from the send-first queue (dashboard/measure.py)), upserts a
``selection_round`` metadata field on the chosen data rows, and creates
a labelling batch in Project B.

Safety: only CREATES new batches and upserts metadata. Never deletes,
modifies, or moves existing resources. Follows the three-stage protocol
(--test for 5 rows, then full).

`send_batches.csv` holds every batch in one file, so --batch picks the one to
send. One batch there is one Labelbox batch.

Usage:
    # Stage 1, test with 5 rows:
    python labelling/dispatch_round.py \\
        --round 1 --csv build/tables/send_batches.csv --batch 1 --test

    # Stage 2, full dispatch:
    python labelling/dispatch_round.py \\
        --round 1 --csv build/tables/send_batches.csv --batch 1
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


def load_selection_csv(csv_path: Path, batch_id: str | None = None) -> list[str]:
    """The global keys to send, in file order.

    `send_batches.csv` holds every batch in one file, and one batch is one
    Labelbox batch, so `batch_id` picks the one to send. A file without that
    column is sent whole: an older selection CSV is still a valid selection.
    An id that is not in the file is a stop, never an empty send.
    """
    global_keys, seen, n_control = [], set(), 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            in_file = (row.get("batch_id") or "").strip()
            seen.add(in_file)
            if batch_id is not None and in_file != batch_id:
                continue
            gk = row["global_key"].strip()
            if gk:
                global_keys.append(gk)
                n_control += (row.get("picked_by") or "").strip() == "control"
    if batch_id is not None and batch_id not in seen:
        sys.exit(f"ERROR: batch {batch_id} is not in {csv_path}. "
                 f"It holds {len(seen - {''})} batches.")
    if n_control:
        # Said out loud, because the botanist will not see it: the batch reaches
        # Labelbox as global keys and nothing marks these frames there. The
        # record that they were the comparison is the CSV, and this run.
        print(f"  {n_control} of these were drawn at random from the whole pool, not "
              f"from the head of the queue. They are the comparison; keep the CSV.")
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
    """Map every global key in the dataset to its Labelbox data row id.

    The queue names photos by global key; Labelbox wants row ids. Exporting the
    whole dataset once beats one lookup per photo in a batch of hundreds.
    """
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


def parse_args():
    """Which round, which selection, and how urgently the botanists should see it."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--round", type=int, required=True, help="round number (1, 2, ...)")
    ap.add_argument("--csv", type=Path, required=True, help="selection CSV from the send-first queue (dashboard/measure.py)")
    ap.add_argument("--batch", help="send one batch_id out of the CSV (send_batches.csv "
                    "holds all of them; one batch is one Labelbox batch)")
    ap.add_argument("--test", action="store_true", help="process first 5 rows only (Stage 1)")
    ap.add_argument("--priority", type=int, default=1, choices=[1, 2, 3, 4, 5],
                    help="labelling priority (1=highest, default 1)")
    return ap.parse_args()


def match_keys(global_keys, key_to_id):
    """The selected photos that Labelbox actually has, and a warning for the rest.

    A key in the queue and not in the dataset is not fatal, it is a photo that
    was never uploaded. Sending the rest is better than sending nothing, so the
    gap is reported and the round goes out.
    """
    missing = [gk for gk in global_keys if gk not in key_to_id]
    if missing:
        print(f"  WARNING: {len(missing)} keys not found in dataset (first 5: {missing[:5]})")
    matched = [gk for gk in global_keys if gk in key_to_id]
    if not matched:
        sys.exit("ERROR: No matching data rows found.")
    return matched, missing


def tag_round(client, matched_keys, key_to_id, round_no):
    """Stamp the round number onto each data row, in chunks Labelbox accepts.

    The tag is what a closed round is found by later: `close_round.py` reads
    the batch, and the metadata is what survives if the batch is renamed.
    """
    mdo = client.get_data_row_metadata_ontology()
    schema_id = get_or_create_round_schema(mdo)

    updates = [
        lb.DataRowMetadata(
            data_row_id=key_to_id[gk],
            fields=[lb.DataRowMetadataField(schema_id=schema_id, value=float(round_no))],
        )
        for gk in matched_keys
    ]
    for i in range(0, len(updates), UPSERT_CHUNK):
        batch = updates[i:i + UPSERT_CHUNK]
        mdo.bulk_upsert(batch)
        print(f"  Batch {i // UPSERT_CHUNK + 1}: {len(batch)} rows tagged")


def create_batch(client, project_name, matched_keys, round_no, priority):
    """Put the round in front of the botanists, named so a human can find it.

    The name carries the round number and the day it went out, which is what
    `close_round.py` matches on and what anyone reading the project sees.
    """
    project = next((p for p in client.get_projects() if p.name == project_name), None)
    if project is None:
        sys.exit(f"ERROR: Project '{project_name}' not found.")

    batch_name = f"Round {round_no} - {date.today().isoformat()}"
    batch = project.create_batch(
        name=batch_name,
        global_keys=matched_keys,
        priority=priority,
    )
    print(f"  Created batch: {batch.name} ({len(matched_keys)} data rows, priority={priority})")
    return batch_name


def main() -> None:
    """Send one round of photos to the botanists: read the selection, find the
    rows, tag them with the round number, and create the batch. Four numbered
    steps, because any of them can be the one that finds nothing."""
    args = parse_args()
    if not args.csv.exists():
        sys.exit(f"ERROR: {args.csv} not found.")

    config = settings.load_config()
    combined_dataset_name = config["labelbox"]["combined_dataset_name"]
    project_b_name = config["labelbox"]["project_b_name"]

    global_keys = load_selection_csv(args.csv, args.batch)
    if not global_keys:
        sys.exit(f"ERROR: no global keys to send from {args.csv}.")
    if args.test:
        global_keys = global_keys[:5]
        print(f"TEST MODE: processing {len(global_keys)} rows only")
    where = f"{args.csv}" + (f" batch {args.batch}" if args.batch else "")
    print(f"Step 1 - Loaded {len(global_keys)} global keys from {where}")

    client = lb.Client(api_key=settings.api_key())

    print(f"\nStep 2 - Fetching data row IDs from '{combined_dataset_name}'...")
    key_to_id = fetch_data_row_ids(client, combined_dataset_name)
    print(f"  Exported {len(key_to_id)} data rows")
    matched_keys, missing = match_keys(global_keys, key_to_id)

    print(f"\nStep 3 - Upserting '{METADATA_SCHEMA_NAME}' = {args.round} on {len(matched_keys)} rows...")
    tag_round(client, matched_keys, key_to_id, args.round)

    print("\nStep 4 - Creating labelling batch in Project B...")
    batch_name = create_batch(client, project_b_name, matched_keys,
                              args.round, args.priority)

    rule = "=" * 50
    print(f"\n{rule}\nDISPATCH COMPLETE\n{rule}")
    print(f"  Round:          {args.round}")
    print(f"  Batch:          {batch_name}")
    print(f"  Data rows:      {len(matched_keys)}")
    print(f"  Missing keys:   {len(missing)}")
    print(f"  Project:        {project_b_name}")
    print(f"  Metadata field: {METADATA_SCHEMA_NAME} = {args.round}")
    print(rule)


if __name__ == "__main__":
    main()
