"""Close a labelling round: export botanist labels and update GT.

Exports labels from Project B for a specific batch (round), parses the
BBOX → nested Radio "Taxón" annotations, picks the dominant species per
image (most bboxes), and appends new rows to gt_dominant_taxon.csv.

The updated GT file becomes the anchor set for the next CoreSet round.

Safety: read-only on Labelbox (export only). Only appends to the local
GT CSV. Never modifies or deletes anything in Labelbox.

Usage:
    # Dry run (show what would be appended, don't write):
    python labelling/close_round.py --round 1 --dry-run

    # Append new labels to GT:
    python labelling/close_round.py --round 1
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import labelbox as lb
import rounds
import settings

REPO = Path(__file__).resolve().parents[1]
GT_CSV = REPO / "data" / "gt_dominant_taxon.csv"
EXPORT_TIMEOUT_SEC = 600
TAXON_TOOL_NAME = "Planta"
TAXON_RADIO_NAME = "Taxón"


def load_existing_gt(gt_path: Path) -> set[str]:
    if not gt_path.exists():
        return set()
    keys = set()
    with open(gt_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keys.add(row["global_key"])
    return keys


def find_batch(project, round_num: int):
    """The batch holding round `round_num`, matched on the name it was sent with.

    The prefix comes from `rounds`, the same module `dispatch_round.py` names
    the batch with, so a rename on one side cannot silently stop the other from
    finding a round.
    """
    prefix = rounds.batch_name_prefix(round_num)
    for batch in project.batches():
        if batch.name.startswith(prefix):
            return batch
    return None


def near_misses(project, round_num: int) -> list[str]:
    """Batch names that mention this round but are not named like one.

    A batch built by hand in the Labelbox interface is usually right except for
    its name: `Round 3`, or `Round 3 - Sept 4`. Nothing can close those, and the
    fix is a rename, so the names go in the error rather than leaving whoever
    ran this to guess whether the batch exists at all.
    """
    return [b.name for b in project.batches()
            if str(round_num) in b.name and rounds.round_of(b.name) != round_num]


def extract_dominant_species(label_data: dict) -> str | None:
    """Pick the most-annotated species from BBOX → Radio annotations."""
    species_counts: Counter = Counter()

    objects = label_data.get("annotations", {}).get("objects", [])
    for obj in objects:
        if obj.get("name") != TAXON_TOOL_NAME:
            continue
        classifications = obj.get("classifications", [])
        for clf in classifications:
            if clf.get("name") != TAXON_RADIO_NAME:
                continue
            answer = clf.get("radio_answer", {})
            species_name = answer.get("name", "").strip()
            if species_name:
                species_counts[species_name] += 1

    if not species_counts:
        return None
    return species_counts.most_common(1)[0][0]


def parse_args():
    """One round to close, and a --dry-run that stops before anything is written."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--round", type=int, required=True, help="round number to close")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be appended without writing")
    ap.add_argument("--gt", type=Path, default=GT_CSV,
                    help=f"GT CSV path (default: {GT_CSV.relative_to(REPO)})")
    return ap.parse_args()


def find_project(client, name):
    """The Labelbox project the botanists work in, looked up by its configured
    name. Exits rather than returning None: every step below needs it."""
    project = next((p for p in client.get_projects() if p.name == name), None)
    if project is None:
        sys.exit(f"ERROR: Project '{name}' not found.")
    return project


def export_rows(project, batch, metadata=False):
    """Pull one batch's labels out of Labelbox and wait for the export to finish.

    Errors are drained from their own stream before the results are: a failed
    export still returns an empty result stream, which would otherwise read as
    a round nobody labelled.

    `metadata` is off for closing a round, which reads labels and not tags, and
    on for `verify_round.py`, which reads the round tag and not the labels.
    """
    export_task = project.export(
        params={
            "data_row_details": True,
            "label_details": True,
            "metadata_fields": metadata,
            "attachments": False,
            "embeddings": False,
        },
        filters={"batch_ids": [batch.uid]},
    )
    export_task.wait_till_done(timeout_seconds=EXPORT_TIMEOUT_SEC)

    if export_task.has_errors():
        errors = []
        export_task.get_buffered_stream(stream_type=lb.StreamType.ERRORS).start(
            stream_handler=lambda e: errors.append(e.json)
        )
        sys.exit(f"ERROR: Export failed: {errors[:3]}")

    rows = []
    export_task.get_buffered_stream(stream_type=lb.StreamType.RESULT).start(
        stream_handler=lambda output: rows.append(output.json)
    )
    return rows


def new_gt_entries(rows, project_uid, existing_keys):
    """The rows this round adds to the GT file, and where the rest went.

    Three ways a row is not new: it is already in the GT file, nobody has
    labelled it yet, or the label carries no species. They are counted apart
    because they mean different things. Photos nobody labelled come back in a
    later round; photos with no species parsed are a job for whoever reads the
    export.
    """
    entries: list[tuple[str, str]] = []
    skipped = SimpleNamespace(existing=0, no_label=0, no_species=0)

    for row in rows:
        gk = row.get("data_row", {}).get("global_key", "")
        if not gk:
            continue
        if gk in existing_keys:
            skipped.existing += 1
            continue

        project_labels = row.get("projects", {}).get(project_uid, {}).get("labels", [])
        if not project_labels:
            skipped.no_label += 1
            continue

        species = extract_dominant_species(project_labels[0])
        if not species:
            skipped.no_species += 1
            continue

        entries.append((gk, species))
    return entries, skipped


def append_gt(path, entries):
    """Append the round's labels, writing the header only on a first run.

    Append, not rewrite: the GT file is the accumulated record of every round
    the botanists have closed, and this script has no business holding all of
    it in memory to write it back.
    """
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["global_key", "wcvp_canonical_name"])
        for gk, species in sorted(entries):
            writer.writerow([gk, species])


def main() -> None:
    """Close one round: export what the botanists labelled, keep the rows that
    are new, and append them to the GT file. Five numbered steps, each printing
    what it found, because any of them can be the one that comes back empty."""
    args = parse_args()
    config = settings.load_config()
    project_b_name = config["labelbox"]["project_b_name"]
    client = lb.Client(api_key=settings.api_key())

    print(f"Step 1 - Finding Project B '{project_b_name}'...")
    project = find_project(client, project_b_name)
    print(f"  Project ID: {project.uid}")

    print(f"\nStep 2 - Finding batch for round {args.round}...")
    batch = find_batch(project, args.round)
    if batch is None:
        near = near_misses(project, args.round)
        hint = (f" Named close to it: {near}. A round is named "
                f"'{rounds.batch_name(args.round)}'; rename it and run this again."
                if near else "")
        sys.exit(f"ERROR: no batch named "
                 f"'{rounds.batch_name_prefix(args.round)}...' in the project.{hint}")
    print(f"  Found batch: {batch.name}")

    print("\nStep 3 - Exporting labels from batch...")
    rows = export_rows(project, batch)
    print(f"  Exported {len(rows)} data rows")

    print("\nStep 4 - Parsing dominant species per image...")
    existing_keys = load_existing_gt(args.gt)
    new_entries, skipped = new_gt_entries(rows, project.uid, existing_keys)

    print(f"  New labels:         {len(new_entries)}")
    print(f"  Already in GT:      {skipped.existing}")
    print(f"  No labels yet:      {skipped.no_label}")
    print(f"  No species parsed:  {skipped.no_species}")

    if not new_entries:
        print("\nNothing to append.")
        return

    species_counts = Counter(sp for _, sp in new_entries)
    print(f"\n  Species found ({len(species_counts)} unique):")
    for sp, count in species_counts.most_common(10):
        print(f"    {sp}: {count}")
    if len(species_counts) > 10:
        print(f"    ... and {len(species_counts) - 10} more")

    if args.dry_run:
        print(f"\nDRY RUN: would append {len(new_entries)} rows to {args.gt}")
        return

    print(f"\nStep 5 - Appending {len(new_entries)} rows to {args.gt}...")
    append_gt(args.gt, new_entries)

    rule = "=" * 50
    print(f"\n{rule}\nROUND CLOSED\n{rule}")
    print(f"  Round:              {args.round}")
    print(f"  New GT rows:        {len(new_entries)}")
    print(f"  Total GT rows:      {len(existing_keys) + len(new_entries)}")
    print(f"  New unique species: {len(species_counts)}")
    print(f"  GT file:            {args.gt}")
    print("\n  Next: python3 dashboard/measure.py, then dispatch the top of")
    print(f"        send_batches.csv with labelling/dispatch_round.py --round {args.round + 1}")
    print(rule)


if __name__ == "__main__":
    main()
