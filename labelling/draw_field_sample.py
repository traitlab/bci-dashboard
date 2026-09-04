"""Draw the field sample from today's unlabelled pool, before it moves.

Every number on the model-health page is read off the historical labelling
record, and that record was never a random sample: a botanist labelled what was
in front of them. So every per-species status, and every rule the queue applies,
is fit and graded on the same convenience sample. Adding labels does not fix it.
Drawing at random from the labelled frames does not fix it either, because the
bias is in which frames got labelled at all.

The one thing that does fix it is a random draw made *before* the next round of
labelling, from the frames that are about to be labelled. Those frames then
carry labels that were not chosen for any reason, so a number read off them
answers "how does the model do on BCI frames" instead of "how does the model do
on the frames a botanist happened to pick". This is a one-way door: after the
next batch ships, the pool has been reshaped by the queue and the draw cannot be
reconstructed.

The pool gets its own committed manifest for the same reason
`predict/draw_confirmatory.py` commits one: it is derived from the live send
queue and a Labelbox inventory, both of which move. The manifest is the frozen
record of what the pool was on the day of the draw, so `--verify` re-draws from
it rather than re-deriving it.

Sending is not this script's job and the queue is not changed. A drawn frame
rides in whatever batch it lands in; what makes the set an evaluation set is
that the draw was recorded before the pool moved, not the order it goes out in.

    python3 labelling/draw_field_sample.py --rebuild-pool          # derive, report
    python3 labelling/draw_field_sample.py --rebuild-pool --write  # commit both
    python3 labelling/draw_field_sample.py --verify                # re-draw, compare
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "input" / "field_sample_2026-09.csv"
POOL = REPO / "input" / "field_sample_pool_2026-09.csv"

# The send queue as the page published it, and the Labelbox inventory that says
# which mission a frame was flown on. Both are generated and gitignored, which
# is why the pool is committed rather than re-derived.
QUEUE_CSV = REPO / "build" / "tables" / "send_first_queue.csv"
INVENTORY = REPO / "data" / "dataset_rows_combined.jsonl"

# 300 to match the confirmatory sample, which is the size this project has
# already agreed is worth a botanist's time. At the labelling team's stated few
# hundred frames a month it is about one month of work, and it is 7.7% of the
# 3,875 frames in the queue.
N = 300
SEED = 20260904
# No site may carry more than a quarter of the set. The largest site is 20.8% of
# the pool today, so the cap binds nothing yet; it is here so a later re-draw on
# a pool one site dominates cannot put that site behind the headline.
CAP = 0.25

# Mission folders are named <yyyymmdd>_<site>_<waypoint>_<aircraft>, and the
# folder is in every frame's Labelbox URL. Same shape as the confirmatory draw
# reads, and the reason a frame with no site is a stop rather than a guess.
MISSION_RE = re.compile(r"/(\d{8})_([a-z0-9]+)_")

FIELDS = ["global_key", "site", "queue", "predicted_species", "confidence"]


def _load(name: str, path: Path):
    """A sibling script as a module. `predict/` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# `allocate` and `draw` are the stratified draw the confirmatory sample was made
# with, reviewed once and left alone since. A second copy of a largest-remainder
# allocation is a second thing to get wrong, so this imports them.
_confirmatory = _load("_draw_confirmatory_for_field_sample",
                      REPO / "predict" / "draw_confirmatory.py")
allocate = _confirmatory.allocate


def site_of(url: str) -> str:
    m = MISSION_RE.search(url or "")
    return m.group(2) if m else ""


def load_sites(path: Path = INVENTORY) -> dict[str, str]:
    """global_key -> site, read from the Labelbox inventory's frame URLs."""
    sites = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            key = row.get("global_key")
            if key:
                sites[key] = site_of(row.get("row_data") or "")
    return sites


def eligible(queue_csv: Path = QUEUE_CSV, inventory: Path = INVENTORY) -> list[dict]:
    """The draw pool: every unlabelled frame the queue would send today.

    A frame whose site cannot be read is a stop, not a row with an empty
    stratum: the draw is stratified by site, and a frame with no site would be
    drawn under a name that means "we did not look".
    """
    sites = load_sites(inventory)
    pool, no_site, spoken_for = [], [], 0
    with open(queue_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["global_key"]
            # A frame already carrying a split belongs to another evaluation and
            # is held out of sends, so it cannot be labelled next round and
            # cannot be drawn into this set as well.
            if (row.get("split") or "").strip():
                spoken_for += 1
                continue
            site = sites.get(key, "")
            if not site:
                no_site.append(key)
                continue
            pool.append({"global_key": key, "site": site, "queue": row["queue"],
                         "predicted_species": row["predicted_species"],
                         "confidence": row["confidence"]})
    if no_site:
        sys.exit(f"ERROR: {len(no_site)} queue frames have no readable site, "
                 f"first {no_site[0]}. Re-page the dataset inventory "
                 f"({inventory.name}) before drawing.")
    if spoken_for:
        print(f"  {spoken_for} queue frames already carry a split and were "
              f"left out of the pool")
    return sorted(pool, key=lambda r: r["global_key"])


def draw(pool: list[dict], n: int = N, seed: int = SEED, cap: float = CAP):
    """The drawn list and the per-site quota it was drawn under.

    Delegates to the method sample's draw so the two samples are drawn the same
    way. That one keys a row by ``base_image``; ours are global keys, so the key
    is aliased for the length of the call rather than renamed on disk.
    """
    aliased = [{**row, "base_image": row["global_key"]} for row in pool]
    picked, quota = _confirmatory.draw(aliased, n=n, seed=seed, cap=cap)
    return [{k: row[k] for k in FIELDS} for row in picked], quota


def to_csv_text(rows: list[dict]) -> str:
    import io
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row[k] for k in FIELDS})
    return buf.getvalue()


def read_pool(path: Path = POOL) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return sorted(csv.DictReader(fh), key=lambda r: r["global_key"])


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def report(pool: list[dict], rows: list[dict], quota: dict) -> None:
    """The four facts a later reader needs to trust the set."""
    print(f"pool            : {len(pool):,} unlabelled frames, "
          f"{len({r['site'] for r in pool})} sites")
    print(f"field sample    : {len(rows)} frames, {len(quota)} sites, "
          f"seed {SEED}, cap {CAP:.0%}")
    print(f"sha256          : {sha256(to_csv_text(rows))}")
    biggest = max(quota.items(), key=lambda kv: (kv[1], kv[0]))
    print(f"largest stratum : {biggest[0]} {biggest[1]} "
          f"({biggest[1] / len(rows):.1%} of the set)")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild-pool", action="store_true",
                    help="derive the pool from the live queue and inventory "
                         "instead of reading the committed manifest. Only "
                         "correct before the freeze")
    ap.add_argument("--write", action="store_true",
                    help="write the pool manifest and the drawn list")
    ap.add_argument("--verify", action="store_true",
                    help="re-draw from the committed manifest and exit "
                         "non-zero on any drift")
    ap.add_argument("--n", type=int, default=N)
    ap.add_argument("--seed", type=int, default=SEED)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    """Draw the set, or prove the committed one still redraws byte for byte."""
    args = parse_args(argv)
    pool = eligible() if args.rebuild_pool else read_pool()
    rows, quota = draw(pool, n=args.n, seed=args.seed)
    text = to_csv_text(rows)

    if args.verify:
        if not OUT.exists():
            print(f"MISSING {OUT}", file=sys.stderr)
            return 1
        on_disk = OUT.read_text(encoding="utf-8")
        if on_disk != text:
            print(f"DRIFT: {OUT} is not what seed {args.seed} draws from "
                  f"{POOL.name}", file=sys.stderr)
            return 1
        print(f"{OUT.name} redraws byte for byte, sha256 {sha256(text)}")
        return 0

    report(pool, rows, quota)
    if args.write:
        POOL.write_text(to_csv_text(pool), encoding="utf-8")
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {POOL} and {OUT}")
    else:
        print("nothing written, pass --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
