"""Check that a round in Labelbox is a round: right name, right tag, right rows.

`dispatch_round.py` builds a round correctly by construction. A batch built by
hand in the Labelbox interface does not, and the two things it usually misses
are invisible until months later: a name nothing can match, and no
``selection_round`` tag. This reads the round back and says which of the three
checks failed.

Read-only on Labelbox: one project export. It writes nothing and creates
nothing, so it is safe to run against a live round at any time.

    # Is round 3 a round?
    python labelling/verify_round.py --round 3

    # And is it the sample that was drawn, frame for frame?
    python labelling/verify_round.py --round 3 --csv input/field_sample_2026-09.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import close_round
import labelbox as lb
import rounds
import settings

REPO = Path(__file__).resolve().parents[1]


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--round", type=int, required=True, help="round number to check")
    ap.add_argument("--csv", type=Path, help="the selection CSV the round was drawn "
                    "from. Given, the check is set equality: no frame missing and "
                    "none added")
    return ap.parse_args()


def selection_keys(csv_path: Path) -> list[str]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [r["global_key"].strip() for r in csv.DictReader(f)
                if r["global_key"].strip()]


def round_tag(row: dict) -> float | None:
    """The `selection_round` value on one exported row, or None if it carries none.

    Read defensively: the field is absent on an untagged row, and the export
    names it by schema name in a list rather than by key.
    """
    for field in row.get("metadata_fields") or []:
        if field.get("schema_name") == rounds.METADATA_SCHEMA_NAME:
            value = field.get("value")
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def check_name(name: str, round_no: int) -> list[str]:
    """The name has to be the convention, not merely close to it."""
    if rounds.round_of(name) == round_no:
        return []
    return [(f"the batch is named '{name}', and a round is named "
             f"'{rounds.batch_name(round_no)}'. Rename it: nothing can close "
             f"a round it cannot find by name.")]


def check_tags(rows: list[dict], round_no: int) -> list[str]:
    """Every row in the batch carries this round's number, or the round is not
    findable once the batch is renamed or a second batch is added."""
    untagged = [r.get("data_row", {}).get("global_key", "?")
                for r in rows if round_tag(r) is None]
    wrong = {r.get("data_row", {}).get("global_key", "?"): round_tag(r)
             for r in rows if round_tag(r) not in (None, float(round_no))}
    problems = []
    if untagged:
        problems.append(f"{len(untagged)} of {len(rows)} rows carry no "
                        f"'{rounds.METADATA_SCHEMA_NAME}' (first 5: {untagged[:5]}). "
                        f"Upsert it as a number = {round_no}.")
    if wrong:
        problems.append(f"{len(wrong)} rows carry another round's number "
                        f"(first 5: {list(wrong.items())[:5]}).")
    return problems


def check_membership(rows: list[dict], csv_path: Path) -> list[str]:
    """The batch and the drawn list are the same set of frames.

    Set equality, not a count: a batch of the right size with one frame swapped
    is no longer the sample that was drawn, and a count would not show it.
    """
    drawn = set(selection_keys(csv_path))
    sent = {r.get("data_row", {}).get("global_key", "") for r in rows}
    sent.discard("")
    problems = []
    if drawn - sent:
        problems.append(f"{len(drawn - sent)} drawn frames are not in the batch "
                        f"(first 5: {sorted(drawn - sent)[:5]}). A partial round "
                        f"is not the sample that was drawn.")
    if sent - drawn:
        problems.append(f"{len(sent - drawn)} frames in the batch were not drawn "
                        f"(first 5: {sorted(sent - drawn)[:5]}).")
    return problems


def main() -> None:
    """Read one round back and report every way it is not one, not just the
    first: whoever fixes a hand-built batch would rather see all of it."""
    args = parse_args()
    if args.csv and not args.csv.exists():
        sys.exit(f"ERROR: {args.csv} not found.")

    config = settings.load_config()
    project_b_name = config["labelbox"]["project_b_name"]
    client = lb.Client(api_key=settings.api_key())

    print(f"Step 1 - Finding Project B '{project_b_name}'...")
    project = close_round.find_project(client, project_b_name)

    print(f"\nStep 2 - Finding the batch for round {args.round}...")
    batch = close_round.find_batch(project, args.round)
    if batch is None:
        near = close_round.near_misses(project, args.round)
        hint = f" Named close to it: {near}." if near else ""
        sys.exit(f"FAIL: no batch named '{rounds.batch_name_prefix(args.round)}...' "
                 f"in the project.{hint} A round starts as a batch named "
                 f"'{rounds.batch_name(args.round)}'.")
    print(f"  Found batch: {batch.name}")

    print("\nStep 3 - Exporting the batch with its metadata...")
    rows = close_round.export_rows(project, batch, metadata=True)
    print(f"  Exported {len(rows)} data rows")

    problems = check_name(batch.name, args.round) + check_tags(rows, args.round)
    if args.csv:
        problems += check_membership(rows, args.csv)

    rule = "=" * 50
    if problems:
        print(f"\n{rule}\nROUND {args.round} IS NOT DISPATCH-SHAPED\n{rule}")
        for problem in problems:
            print(f"  - {problem}")
        print(rule)
        sys.exit(1)

    print(f"\n{rule}\nROUND {args.round} CHECKS OUT\n{rule}")
    print(f"  Batch:          {batch.name}")
    print(f"  Data rows:      {len(rows)}")
    print(f"  Metadata field: {rounds.METADATA_SCHEMA_NAME} = {args.round} on every row")
    if args.csv:
        print(f"  Membership:     the same {len(rows)} frames as {args.csv}")
    print(rule)


if __name__ == "__main__":
    main()
