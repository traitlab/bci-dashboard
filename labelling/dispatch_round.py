"""Dispatch a round selection to Labelbox Project B.

Reads a selection CSV (from the send-first queue (dashboard/measure.py)), upserts a
``batch_id`` metadata field (the batch name) on the chosen data rows, and creates
a labelling batch in Project B.

Safety: only CREATES new batches and upserts metadata. Never deletes,
modifies, or moves existing resources. Follows the three-stage protocol:
--dry-run (writes nothing, calls no API), then --test (5 rows, WRITES LIVE),
then full.

Keys sent before are skipped, not re-sent. "Before" is two local records: the
closed rounds' ground truth (data/gt_dominant_taxon.csv) and the per-round
ledger this script writes just before it creates each batch (input/rounds/round_N.csv,
tracked: commit it, it is the only record of which frames were the control). Rows
Labelbox reports as failed are dropped from it again, so they can be re-sent.
A round sent without committing its ledger is not seen; Labelbox is not asked.

The CSV is the file the queue page downloads (send_batch_1.csv, or
send_batches_filtered.csv): send_batches.csv's columns, with data_row_id,
batch_id and global_key required. The whole file is one Labelbox batch. Given
the full send_batches.csv instead, --batch picks the one batch to send. --round
defaults to the round after the last ledger.

Usage:
    # Stage 0, always first: nothing is written, no API call is made.
    python labelling/dispatch_round.py ~/Downloads/send_batch_1.csv --dry-run

    # Stage 1, test with 5 rows. This writes to Labelbox like a full run:
    python labelling/dispatch_round.py ~/Downloads/send_batch_1.csv --test

    # Stage 2, full dispatch:
    python labelling/dispatch_round.py ~/Downloads/send_batch_1.csv
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import labelbox as lb
import rounds
import settings
from lbox.exceptions import (
    AuthorizationError, LabelboxError, MalformedQueryException)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard"))

import core  # same GT path as read_round, BCI_DASHBOARD_DATA included

GT_CSV = Path(core.GT_CSV)
# Tracked, one file per round. No expert labels belong in it.
LEDGER_DIR = REPO / "input" / "rounds"
# The species columns freeze the state that put a frame in its queue: later
# labels move a species between queues, so a read-out must not re-derive it.
LEDGER_FIELDS = ["round", "batch_id", "global_key", "data_row_id", "picked_by", "queue",
                 "predicted_species", "confidence", "species_labelled_crowns",
                 "species_top1_accuracy", "mission", "site", "dispatched_at"]

# How many metadata rows go up in one bulk_upsert call. Not the botanist-session
# batch size: `queues.BATCH_SIZE` is that one, and it is a different number for a
# different reason, so the two do not share a name.
UPSERT_CHUNK = 500
EXPORT_TIMEOUT_SEC = 300

# The batch name and the metadata field are the round's contract with whoever
# closes it, and with anyone who builds a batch by hand instead of running this.
# `rounds` holds both so the two scripts cannot drift apart.
METADATA_SCHEMA_NAME = rounds.METADATA_SCHEMA_NAME

# What a queue-page download carries, the whole file and the filtered one alike.
REQUIRED_COLUMNS = ["data_row_id", "batch_id", "global_key"]


def load_selection_csv(csv_path: Path, batch_id: str | None = None,
                       whole: bool = False) -> list[str]:
    """The global keys to send, in file order.

    `send_batches.csv` holds every batch in one file, and one batch is one
    Labelbox batch, so `batch_id` picks the one to send. A file without that
    column is sent whole. An id that is not in the file is a stop, never an
    empty send. A file missing a column in `REQUIRED_COLUMNS` is a stop too:
    it is not a queue-page download.
    """
    global_keys, seen, n_control, no_id = [], set(), 0, []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        have = reader.fieldnames or []
        absent = [c for c in REQUIRED_COLUMNS if c not in have]
        if absent:
            sys.exit(f"ERROR: {csv_path} has no {', '.join(absent)} column. Send a CSV "
                     f"downloaded from the queue page; it has {', '.join(REQUIRED_COLUMNS)}. "
                     f"This one has: {', '.join(have) or 'no header'}.")
        for row in reader:
            in_file = (row.get("batch_id") or "").strip()
            seen.add(in_file)
            if batch_id is not None and in_file != batch_id:
                continue
            gk = row["global_key"].strip()
            if gk:
                global_keys.append(gk)
                if not (row.get("data_row_id") or "").strip():
                    no_id.append(gk)
                n_control += (row.get("picked_by") or "").strip() == "control"
    if no_id and len(no_id) == len(global_keys):
        # Every id blank is a file nobody could resolve offline: the catalog pool
        # (`catalog_batches.py`) is in no local inventory. Step 2 looks each key up
        # in the dataset, and a key it lacks is reported there as missing.
        print("  No data_row_id in this file: Labelbox is asked for them by global key.")
    elif no_id:
        # Some rows have one and some do not: the missing ones are not in the
        # dispatch dataset, so Labelbox would only report them missing.
        sys.exit(f"ERROR: {len(no_id)} of the {len(global_keys)} selected rows have no data_row_id, "
                 f"so they are not in Labelbox and cannot be sent (first 5: {no_id[:5]}). "
                 f"Re-run measure.py, or drop them from the CSV.")
    # The full send_batches.csv sent whole would be every batch as one Labelbox batch.
    if batch_id is None and not whole and len(seen - {""}) > 1:
        sys.exit(f"ERROR: {csv_path} holds {len(seen - {''})} batches. Pick one with "
                 f"--batch, or pass --whole to send them as one Labelbox batch "
                 f"(a filtered download).")
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


def already_sent(gt_path: Path = GT_CSV, ledger_dir: Path = LEDGER_DIR) -> set[str]:
    """Keys that went out in an earlier round: closed-round GT plus every ledger."""
    gt = ({(r.get("global_key") or "").strip() for r in core.read_csv_rows(str(gt_path))}
          if gt_path.exists() else set())  # an absent file is an empty record
    return (gt - {""}) | core.ledger_keys(str(ledger_dir))


def skip_sent(global_keys: list[str], sent: set[str]) -> tuple[list[str], list[str]]:
    """(keys still to send, keys skipped), both in file order."""
    return ([k for k in global_keys if k not in sent],
            [k for k in global_keys if k in sent])


def _by_key(path: Path, batch_id: str | None = None) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["global_key"].strip(): r for r in csv.DictReader(f)
                if batch_id is None or (r.get("batch_id") or "").strip() == batch_id}


def record_sent(keys, round_no, csv_path: Path, batch_id: str | None,
                key_to_id: dict, ledger_dir: Path = LEDGER_DIR) -> Path:
    """Write what was just dispatched to input/rounds/round_<N>.csv.

    A later measure.py run rewrites send_batches.csv and drops dispatched rows
    from the queue, which would destroy the record of which frames were the
    random control. This file is that record, so it is tracked, and it is also
    what the already-sent check reads. Fields come from the selection CSV, then
    from the send_first_queue.csv beside it; a field neither has is blank.
    """
    sent_rows = _by_key(csv_path, batch_id)
    queue_rows = _by_key(csv_path.with_name("send_first_queue.csv"))
    now = datetime.now().isoformat(timespec="seconds")
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"round_{round_no}.csv"
    fresh = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(LEDGER_FIELDS)
        for k in keys:
            row = {**queue_rows.get(k, {}), **{c: v for c, v in sent_rows.get(k, {}).items() if v}}
            row.update(round=round_no, global_key=k, dispatched_at=now,
                       data_row_id=key_to_id.get(k) or row.get("data_row_id", ""),
                       batch_id=row.get("batch_id") or batch_id or "")
            w.writerow([row.get(c, "") for c in LEDGER_FIELDS])
    return path


def commit_ledger(path: Path, round_no: int) -> bool:
    """Commit the round ledger in place, so the control-arm record cannot be
    lost to an uncommitted checkout. False, with the manual command printed,
    when git refuses (no repo, hook failure, nothing to commit)."""
    git = ["git", "-C", str(path.parent)]
    try:
        subprocess.run([*git, "add", "--", str(path)], check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "-m", f"data(rounds): round {round_no} ledger"],
                       check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        err = getattr(e, "stderr", b"") or b""
        print(f"  WARNING: ledger not committed ({err.decode(errors='replace').strip() or e}). "
              f"Run: git add {path} && git commit -m 'data(rounds): round {round_no} ledger'")
        return False


def fragment_species(keys, csv_path: Path, batch_id: str | None) -> tuple[int, int]:
    """(species with 1 or 2 photos in this send, species in this send). Tracks the
    open question whether tiny species fragments slow the botanists down."""
    sent, queue = _by_key(csv_path, batch_id), _by_key(csv_path.with_name("send_first_queue.csv"))
    per_species = {}
    for k in keys:
        # same precedence as record_sent: the batch row, then the queue row
        sp = (sent.get(k, {}).get("predicted_species")
              or queue.get(k, {}).get("predicted_species") or "").strip()
        if sp:
            per_species[sp] = per_species.get(sp, 0) + 1
    return sum(n <= 2 for n in per_species.values()), len(per_species)


def drop_rows(path: Path, data_row_ids: set[str]) -> None:
    """Remove ledger rows by data_row_id: rows Labelbox refused were not sent."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["data_row_id"] not in data_row_ids]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, LEDGER_FIELDS)
        w.writeheader()
        w.writerows(rows)


def get_or_create_round_schema(mdo) -> str:
    """The `batch_id` field's id, creating the field the first time.

    `get_by_name` RAISES on a field that does not exist, it does not return
    None, so the create half of this function was unreachable and every first
    dispatch died on a KeyError before writing anything. That is the whole
    reason no round has ever gone out. Catch it and create, which is what the
    name of this function has always promised.
    """
    try:
        existing = mdo.get_by_name(METADATA_SCHEMA_NAME)
    except KeyError:
        existing = None
    if existing:
        return existing.uid
    from labelbox.schema.data_row_metadata import DataRowMetadataKind
    schema = mdo.create_schema(
        name=METADATA_SCHEMA_NAME,
        kind=DataRowMetadataKind.string,
    )
    print(f"  Created metadata schema '{METADATA_SCHEMA_NAME}' (id={schema.uid})")
    return schema.uid


# What creating the field needs, said in the script rather than only in a
# handover: on 2026-09-07 our key read the ontology fine, found no
# `batch_id`, and was refused the create with `Forbidden resource`. The
# same key is refused `export` on every project and pages instead. So the field
# has to be made once by someone with organisation rights, and after that this
# function takes the reuse path. Until then no round can go out, whatever the
# queue says.
FORBIDDEN_HELP = (
    f"Creating the '{METADATA_SCHEMA_NAME}' field was refused. This key can read the "
    f"metadata ontology but not add to it. Ask whoever administers the Labelbox "
    f"organisation to create a Data Row Metadata field named '{METADATA_SCHEMA_NAME}' "
    f"of kind Text (String), once, then run this again: it will find the field and reuse it.")


def page_data_row_ids(dataset) -> dict[str, str]:
    """The same map, read a row at a time instead of exported in bulk.

    A key can be allowed to read a dataset and still be refused an export task,
    which is what ours is: every `export` on every project and on this dataset
    answers "Insufficient permissions", while `data_rows()` pages fine. Paging
    the whole dataset is the slower route and the only one such a key has, so a
    refused export falls through to here rather than ending the dispatch.
    """
    return {row.global_key: row.uid for row in dataset.data_rows()
            if row.global_key}


def fetch_data_row_ids(client: lb.Client, dataset_name: str) -> dict[str, str]:
    """Map every global key in the dataset to its Labelbox data row id.

    The queue names photos by global key; Labelbox wants row ids. Exporting the
    whole dataset once beats one lookup per photo in a batch of hundreds, and
    `page_data_row_ids` is the fallback when the key may not export.
    """
    dataset = next((d for d in client.get_datasets() if d.name == dataset_name), None)
    if dataset is None:
        sys.exit(f"ERROR: Dataset '{dataset_name}' not found.")

    try:
        export_task = dataset.export(params={
            "attachments": False,
            "metadata_fields": False,
            "data_row_details": True,
            "embeddings": False,
            "labels": False,
        })
    except (AuthorizationError, MalformedQueryException) as refused:
        print(f"  export refused ({refused}), paging {dataset.name} instead")
        return page_data_row_ids(dataset)
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
    ap.add_argument("--round", type=int, default=None,
                    help="round number (1, 2, ...). Default: the round after the last ledger")
    ap.add_argument("path", nargs="?", type=Path, help="the CSV downloaded from the queue page")
    ap.add_argument("--csv", type=Path, dest="csv_flag", help="same as the positional path")
    ap.add_argument("--batch", help="send one batch_id out of the CSV (send_batches.csv "
                    "holds all of them; one batch is one Labelbox batch)")
    ap.add_argument("--whole", action="store_true",
                    help="send a CSV that spans several batches as one Labelbox batch, "
                         "e.g. a filtered download")
    ap.add_argument("--dry-run", action="store_true",
                    help="read the CSV, skip keys sent before, print the plan, then "
                         "stop: no Labelbox client, no write. Run this first")
    ap.add_argument("--test", action="store_true",
                    help="process first 5 rows only (Stage 1). Still WRITES to "
                         "Labelbox: it is a smaller send, not a rehearsal")
    ap.add_argument("--priority", type=int, default=None, choices=[1, 2, 3, 4, 5],
                    help="labelling priority (1=highest). Default: derived from "
                         "--batch, so the queue order survives into Labelbox")
    args = ap.parse_args()
    if args.path and args.csv_flag and args.path != args.csv_flag:
        ap.error("give the CSV once, as a path or with --csv, not both")
    args.csv = args.path or args.csv_flag
    if args.csv is None:
        ap.error("a CSV is required: the file downloaded from the queue page")
    args.csv = args.csv.expanduser()
    return args


# Labelbox has five priority levels and the queue has fifty batches, so the
# mapping saturates: batch 1 is priority 1, batch 4 is priority 4, and every
# batch from 5 on is priority 5. Sending every batch at priority 1 is what
# throws the queue order away at the Labelbox door, which is the whole point of
# ordering it.
MAX_PRIORITY = 5


def priority_for_batch(batch_id, explicit=None):
    """The Labelbox priority to send a batch at.

    An explicit --priority always wins: a batch re-sent out of order is a human
    decision. Without one, the batch number is the priority, capped at
    `MAX_PRIORITY`. A run with no --batch has no order to preserve and goes out
    at 1, which is what this script did for every batch before.
    """
    if explicit is not None:
        return explicit
    try:
        n = int(str(batch_id).strip())
    except (TypeError, ValueError):
        return 1
    return min(max(n, 1), MAX_PRIORITY)


def with_basename_aliases(key_to_id: dict[str, str]) -> dict[str, str]:
    """Also answer to each photo's bare file name when exactly one key ends in it.

    The 2024_bci dataset keys photos as `<flight folder>/<file name>` while the
    catalog pool names them by file name alone. A name two keys share stays
    unmatched and is reported missing, never guessed.
    """
    by_name: dict[str, list[str]] = {}
    for key, uid in key_to_id.items():
        by_name.setdefault(key.rsplit("/", 1)[-1], []).append(uid)
    return {n: ids[0] for n, ids in by_name.items() if len(ids) == 1} | key_to_id


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


def tag_round(client, matched_keys, key_to_id, name):
    """Stamp the batch name onto each data row, in chunks Labelbox accepts.

    The tag is what a closed round is found by later: `close_round.py` reads
    the batch, and the metadata is what survives if the batch is renamed.
    """
    mdo = client.get_data_row_metadata_ontology()
    try:
        schema_id = get_or_create_round_schema(mdo)
    except LabelboxError as e:
        # A stack trace ending in "Unknown error: Forbidden resource" says
        # nothing a reader can act on. This is the one refusal we have met, and
        # it has a one-sentence fix somebody else has to make.
        if "FORBIDDEN" in str(e).upper():
            sys.exit(f"ERROR: {FORBIDDEN_HELP}")
        raise

    updates = [
        lb.DataRowMetadata(
            data_row_id=key_to_id[gk],
            fields=[lb.DataRowMetadataField(schema_id=schema_id, value=name)],
        )
        for gk in matched_keys
    ]
    for i in range(0, len(updates), UPSERT_CHUNK):
        batch = updates[i:i + UPSERT_CHUNK]
        mdo.bulk_upsert(batch)
        print(f"  Batch {i // UPSERT_CHUNK + 1}: {len(batch)} rows tagged")


def create_batch(client, project_name, data_row_ids, round_no, priority):
    """Put the round in front of the botanists, named so a human can find it.

    The name carries the round number and the day it went out, which is what
    `close_round.py` matches on and what anyone reading the project sees. Its
    shape is `rounds.batch_name`, and a batch built by hand has to match it.
    """
    project = next((p for p in client.get_projects() if p.name == project_name), None)
    if project is None:
        sys.exit(f"ERROR: Project '{project_name}' not found.")

    batch = project.create_batch(
        name=rounds.batch_name(round_no),
        data_rows=data_row_ids,
        priority=priority,
    )
    print(f"  Created batch: {batch.name} ({len(data_row_ids)} data rows, priority={priority})")
    return batch


def main() -> None:
    """Send one round of photos to the botanists: read the selection, find the
    rows, tag them with the round number, and create the batch. Four numbered
    steps, because any of them can be the one that finds nothing."""
    args = parse_args()
    if args.round is None:
        args.round = core.next_round(str(LEDGER_DIR))
    if not args.csv.exists():
        sys.exit(f"ERROR: {args.csv} not found.")

    # Checked before the dry run too, so it fails exactly as the real send would.
    if not GT_CSV.exists():
        # Without it every closed round's keys look unsent and would go out again.
        sys.exit(f"ERROR: ground-truth file {GT_CSV} not found; cannot tell what was "
                 f"already sent. Set BCI_DASHBOARD_DATA or restore the file.")

    config = settings.load_config()
    combined_dataset_name = config["labelbox"]["combined_dataset_name"]
    project_b_name = config["labelbox"]["project_b_name"]

    global_keys = load_selection_csv(args.csv, args.batch, args.whole)
    if not global_keys:
        sys.exit(f"ERROR: no global keys to send from {args.csv}.")
    global_keys, skipped = skip_sent(global_keys, already_sent(GT_CSV, LEDGER_DIR))
    print(f"Skipped {len(skipped)} keys already sent in an earlier round "
          f"(first 5: {skipped[:5]})" if skipped else "Skipped 0 keys already sent")
    if not global_keys:
        sys.exit("ERROR: every key in the selection was sent in an earlier round.")
    if args.test:
        global_keys = global_keys[:5]
        print(f"TEST MODE: processing {len(global_keys)} rows only")
    where = f"{args.csv}" + (f" batch {args.batch}" if args.batch else "")
    print(f"Step 1 - Loaded {len(global_keys)} global keys from {where}")

    small, n_species = fragment_species(global_keys, args.csv, args.batch)
    print(f"  Species in this send: {n_species}, of which {small} with 1 or 2 photos")
    if args.dry_run:
        print(f"\nDRY RUN: would tag and batch {len(global_keys)} keys as round "
              f"{args.round}, batch '{rounds.batch_name(args.round)}'. Nothing written, "
              f"no API call made.")
        return

    client = lb.Client(api_key=settings.api_key())

    print(f"\nStep 2 - Fetching data row IDs from '{combined_dataset_name}'...")
    key_to_id = fetch_data_row_ids(client, combined_dataset_name)
    print(f"  Exported {len(key_to_id)} data rows")
    key_to_id = with_basename_aliases(key_to_id)
    matched_keys, missing = match_keys(global_keys, key_to_id)

    name = rounds.batch_name(args.round)
    print(f"\nStep 3 - Upserting '{METADATA_SCHEMA_NAME}' = {name} on {len(matched_keys)} rows...")
    tag_round(client, matched_keys, key_to_id, name)

    priority = priority_for_batch(args.batch, args.priority)
    print(f"\nStep 4 - Creating labelling batch in Project B at priority {priority}...")
    # Ledger first: a crash after the batch exists must not let a rerun send again.
    ledger = record_sent(matched_keys, args.round, args.csv, args.batch, key_to_id, LEDGER_DIR)
    try:
        batch = create_batch(client, project_b_name, [key_to_id[k] for k in matched_keys],
                             args.round, priority)
    except (Exception, SystemExit):
        print(f"  Ledger rows kept in {ledger}. If Labelbox made no batch, delete them "
              f"there before re-running, or they are skipped as sent.")
        raise
    failed = set(batch.failed_data_row_ids)
    if failed:
        drop_rows(ledger, failed)
        print(f"  WARNING: Labelbox refused {len(failed)} data rows; dropped from the ledger "
              f"so a re-run sends them (first 5: {sorted(failed)[:5]})")
    batch_name = batch.name

    rule = "=" * 50
    print(f"\n{rule}\nDISPATCH COMPLETE\n{rule}")
    print(f"  Round:          {args.round}")
    print(f"  Batch:          {batch_name}")
    print(f"  Data rows:      {len(matched_keys) - len(failed)}")
    print(f"  Missing keys:   {len(missing)}")
    print(f"  Project:        {project_b_name}")
    print(f"  Metadata field: {METADATA_SCHEMA_NAME} = {rounds.batch_name(args.round)}")
    print(f"  Ledger:         {ledger} (the record of the control arm)")
    print(f"  Priority:       {priority}"
          + ("" if args.priority is not None else f" (from batch {args.batch})"
             if args.batch else " (no batch given)"))
    print(rule)
    if commit_ledger(ledger, args.round):
        print("  Ledger committed. Push it: git push")


if __name__ == "__main__":
    main()
