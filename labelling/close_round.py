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

import labelbox as lb
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
    target_prefix = f"Round {round_num} -"
    for batch in project.batches():
        if batch.name.startswith(target_prefix):
            return batch
    return None


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


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--round", type=int, required=True, help="round number to close")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be appended without writing")
    ap.add_argument("--gt", type=Path, default=GT_CSV,
                    help=f"GT CSV path (default: {GT_CSV.relative_to(REPO)})")
    args = ap.parse_args()

    api_key = settings.api_key()

    config = settings.load_config()
    project_b_name = config["labelbox"]["project_b_name"]

    client = lb.Client(api_key=api_key)

    print(f"Step 1 - Finding Project B '{project_b_name}'...")
    project = next(
        (p for p in client.get_projects() if p.name == project_b_name), None
    )
    if project is None:
        sys.exit(f"ERROR: Project '{project_b_name}' not found.")
    print(f"  Project ID: {project.uid}")

    print(f"\nStep 2 - Finding batch for round {args.round}...")
    batch = find_batch(project, args.round)
    if batch is None:
        sys.exit(f"ERROR: No batch matching 'Round {args.round} -' found in project.")
    print(f"  Found batch: {batch.name}")

    print("\nStep 3 - Exporting labels from batch...")
    export_task = project.export(
        params={
            "data_row_details": True,
            "label_details": True,
            "metadata_fields": False,
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
    print(f"  Exported {len(rows)} data rows")

    print("\nStep 4 - Parsing dominant species per image...")
    existing_keys = load_existing_gt(args.gt)
    new_entries: list[tuple[str, str]] = []
    skipped_existing = 0
    skipped_no_label = 0
    skipped_no_species = 0

    for row in rows:
        gk = row.get("data_row", {}).get("global_key", "")
        if not gk:
            continue
        if gk in existing_keys:
            skipped_existing += 1
            continue

        project_labels = row.get("projects", {}).get(project.uid, {}).get("labels", [])
        if not project_labels:
            skipped_no_label += 1
            continue

        label_data = project_labels[0]
        species = extract_dominant_species(label_data)
        if not species:
            skipped_no_species += 1
            continue

        new_entries.append((gk, species))

    print(f"  New labels:         {len(new_entries)}")
    print(f"  Already in GT:      {skipped_existing}")
    print(f"  No labels yet:      {skipped_no_label}")
    print(f"  No species parsed:  {skipped_no_species}")

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
    write_header = not args.gt.exists()
    with open(args.gt, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["global_key", "wcvp_canonical_name"])
        for gk, species in sorted(new_entries):
            writer.writerow([gk, species])

    print(f"\n{'=' * 50}")
    print("ROUND CLOSED")
    print(f"{'=' * 50}")
    print(f"  Round:              {args.round}")
    print(f"  New GT rows:        {len(new_entries)}")
    print(f"  Total GT rows:      {len(existing_keys) + len(new_entries)}")
    print(f"  New unique species: {len(species_counts)}")
    print(f"  GT file:            {args.gt}")
    print("\n  Next: python3 dashboard/measure.py, then dispatch the top of")
    print(f"        send_batches.csv with labelling/dispatch_round.py --round {args.round + 1}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
