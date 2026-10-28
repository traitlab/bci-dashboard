"""Record the catalog batches a collaborator sent by hand, from the Labelbox export.

A collaborator creates the `batchNNNN_<yyyy-mm>` batches of `2024_bci` with their
own script, which writes no send record. The weekly export says what went out:
each row carries its batch name at `projects.<id>.project_details.batch_name`.
For every row of the project in a batch named like `rounds.batch_name`, this adds
the frame to `input/rounds/round_<N>.csv` through `dispatch_round.record_sent`,
the same writer and fields a dispatch uses. A frame already in a ledger is left
alone, so a second run with the same export changes nothing. Local only: nothing
is written to Labelbox.

    python labelling/record_sends.py --export data/exports/01_x.ndjson \\
        --sent docs/send_batches.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard"))

import core
import dispatch_round
import rounds

PROJECT_ID = "cmp375mkq0dhr07w92diwbmuh"  # 2024_bci; Project B's rounds are not these


def sent_batches(exports, project_id: str = PROJECT_ID) -> dict[int, dict[str, str]]:
    """batch number -> {frame basename: data_row_id} for the project's batched rows.
    The catalog keys a frame by file name, the dataset by `<flight folder>/<file>`."""
    out: dict[int, dict[str, str]] = {}
    for path in exports:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                details = ((row.get("projects") or {}).get(project_id) or {}).get("project_details") or {}
                n = rounds.round_of(details.get("batch_name") or "")
                if n is None:
                    continue
                key = row["data_row"]["global_key"].rsplit("/", 1)[-1]
                out.setdefault(n, {}).setdefault(key, row["data_row"].get("id") or "")
    return out


def record(exports, sent_csv: Path, ledger_dir: Path, project_id: str = PROJECT_ID) -> dict[int, int]:
    """Add the unrecorded frames of each sent batch to the ledger; batch -> rows added."""
    known = core.ledger_keys(str(ledger_dir))
    added = {}
    for n, frames in sorted(sent_batches(exports, project_id).items()):
        new = [k for k in frames if k not in known]
        if new:
            dispatch_round.record_sent(new, n, sent_csv, str(n), frames, ledger_dir)
            added[n] = len(new)
    return added


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", type=Path, action="append", required=True,
                    help="Labelbox project export (ndjson); repeat for several")
    ap.add_argument("--sent", type=Path, default=REPO / "docs" / "send_batches.csv",
                    help="the published send_batches.csv, for picked_by, queue and species "
                         "(blank where absent)")
    ap.add_argument("--ledger-dir", type=Path, default=dispatch_round.LEDGER_DIR)
    ap.add_argument("--project", default=PROJECT_ID)
    args = ap.parse_args()
    added = record(args.export, args.sent, args.ledger_dir, args.project)
    print("recorded " + (", ".join(f"batch {n}: {c} frames" for n, c in added.items())
                         if added else "nothing new"))


if __name__ == "__main__":
    main()
