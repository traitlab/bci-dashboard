"""Record the catalog batches a collaborator sent by hand, from the Labelbox export.

A collaborator creates the `batchNNNN_<yyyy-mm>` batches of `2024_bci` with their
own script, which writes no send record. The weekly export says what went out:
each row carries its batch name at `projects.<id>.project_details.batch_name`.
The live batch list (`fetch_live_batches.py`) says sooner that a batch exists,
with its size but not its frames: when that size equals the pinned batch of the
same number, the pinned frames are recorded without waiting for the export.
The export runs first and stays authoritative. For every row of the project in a batch named like `rounds.batch_name`, this adds
the frame to `input/rounds/round_<N>.csv` through `dispatch_round.record_sent`,
the same writer and fields a dispatch uses. A frame already in a ledger is left
alone, so a second run with the same export changes nothing; an export whose
frames for a batch differ from its ledger only warns. Local only: nothing is
written to Labelbox.

    python labelling/record_sends.py --export data/exports/01_x.ndjson \\
        --live data/live_batches.json --sent docs/send_batches.csv
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
from catalog_batches import PINS_CSV, read_pins

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


def ledger_frames(ledger_dir: Path, n: int) -> set[str]:
    path = ledger_dir / f"round_{n}.csv"
    return {(r.get("global_key") or "").strip() for r in core.read_csv_rows(str(path))} if path.exists() else set()


def live_sizes(path: Path | None) -> dict[int, int]:
    """batch number -> size from the live list; absent, "not checked" or unparsable names give none."""
    if not path or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for b in data.get("batches") or []:
        n = rounds.round_of(b.get("name") or "")
        if n is not None:
            out[n] = b["size"]
    return out


def record_live(live: Path | None, pins_csv: Path, sent_csv: Path, ledger_dir: Path) -> dict[int, int]:
    """Record the pinned frames of each live batch with no ledger yet and a matching size.

    The list gives a size, not frames. Equal to the pinned batch's size, the pins are what
    was sent; unequal (the batch was edited), nothing is recorded until the export has it."""
    sizes = live_sizes(live)
    pinned: dict[int, list[str]] = {}
    for n, key, _ in read_pins(pins_csv) if sizes else []:
        pinned.setdefault(n, []).append(key)
    have = core.sent_rounds(str(ledger_dir))
    added = {}
    for n, size in sorted(sizes.items()):
        if n in have:
            continue
        frames = pinned.get(n, [])
        if not frames or len(frames) != size:
            print(f"live batch {n}: {size} frames in Labelbox, {len(frames)} pinned; "
                  "not recorded, waits for the export")
            continue
        dispatch_round.record_sent(frames, n, sent_csv, str(n), {}, ledger_dir)
        added[n] = len(frames)
    return added


def record(exports, sent_csv: Path, ledger_dir: Path, project_id: str = PROJECT_ID,
           live: Path | None = None, pins_csv: Path = PINS_CSV) -> dict[int, int]:
    """Add the unrecorded frames of each sent batch to the ledger; batch -> rows added.
    The export first (authoritative), then the live list for batches it does not carry yet."""
    known = core.ledger_keys(str(ledger_dir))
    added = {}
    for n, frames in sorted(sent_batches(exports, project_id).items()):
        recorded = ledger_frames(ledger_dir, n)
        if recorded and recorded != set(frames):
            print(f"WARNING: batch {n}: the export has {len(frames)} frames, the ledger "
                  f"{len(recorded)}, {len(recorded ^ set(frames))} differ; the ledger is left as it is")
        new = [k for k in frames if k not in known]
        if new:
            dispatch_round.record_sent(new, n, sent_csv, str(n), frames, ledger_dir)
            added[n] = len(new)
    for n, count in record_live(live, pins_csv, sent_csv, ledger_dir).items():
        added[n] = added.get(n, 0) + count
    return added


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", type=Path, action="append", default=[],
                    help="Labelbox project export (ndjson); repeat for several")
    ap.add_argument("--live", type=Path, help="data/live_batches.json from fetch_live_batches.py")
    ap.add_argument("--pins", type=Path, default=PINS_CSV)
    ap.add_argument("--sent", type=Path, default=REPO / "docs" / "send_batches.csv",
                    help="the published send_batches.csv, for picked_by, queue and species "
                         "(blank where absent)")
    ap.add_argument("--ledger-dir", type=Path, default=dispatch_round.LEDGER_DIR)
    ap.add_argument("--project", default=PROJECT_ID)
    args = ap.parse_args()
    added = record(args.export, args.sent, args.ledger_dir, args.project, args.live, args.pins)
    print("recorded " + (", ".join(f"batch {n}: {c} frames" for n, c in added.items())
                         if added else "nothing new"))


if __name__ == "__main__":
    main()
