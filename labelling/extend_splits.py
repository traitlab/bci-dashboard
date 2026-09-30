"""Extend data/splits.csv to the frames it never covered, without moving a row.

data/splits.csv is the split the Pl@ntNet runs were graded on, drawn frame by
frame in March 2026. It is frozen: a frame it names keeps its split, and a
frame it lists with a blank split was still sent to Pl@ntNet, so it is treated
as seen and lands in train. Nothing here can change what a model has already
been shown, so the file is the record of what was shown, and this script only
adds to it.

Everything since then is placed by the drone position Labelbox carries on every
frame (`gpsPoint`) and by the flight, one date over one site, read from the
`mission` metadata. A new frame shot within the buffer of a seen frame is a
re-photograph of a tree the models were shown, and it is `buffered`: out of
every set, on record. A new frame on a flight the legacy split already covers
joins its neighbours instead, or is `buffered` when they disagree or it has
none. Every other new frame is `clean_test`. So no flight has frames on both
sides, and no `clean_test` frame stands within the buffer of a seen one. That
is the same unit and the same buffer as labelling/draw_holdout.py, for the
same reasons.

The `polygon` metadata is not used to say two frames show one tree: its
numbers restart with every mission, so number 7 on one flight and number 7 on
another are different crowns hundreds of metres apart. Position is the only
link across dates the data carries.

Nothing is drawn at random. Every clean frame is held, so the clean set grows
by itself as new ground is flown, and a frame's split is decided on the day it
is ingested, not after a model has been trained on it. Labels are not needed:
a frame gets its split before anyone labels it.

    .venv/bin/python labelling/extend_splits.py
    .venv/bin/python labelling/extend_splits.py --write
    .venv/bin/python labelling/extend_splits.py --verify
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "dashboard"))

import core as hc

REPO = Path(__file__).resolve().parents[1]
VERSION = "v2"
LEGACY = REPO / "data" / "splits.csv"
INVENTORIES = (REPO / "data" / "dataset_rows_combined.jsonl",
               REPO / "data" / "dataset_rows.jsonl")
OUT = REPO / "input" / f"splits_{VERSION}.csv"
META = REPO / "input" / f"splits_{VERSION}.json"

# Metres. The same default as draw_holdout.BUFFER_M, and as unmeasured.
BUFFER_M = 30.0
METRES_PER_DEGREE = 111320.0

LEGACY_SPLITS = ("train", "valid", "test")
SPLITS = LEGACY_SPLITS + ("clean_test", "buffered")
# Why a frame has the split it has, most trusted first.
SOURCES = ("legacy", "sent_blank", "near", "flight", "conflict", "unplaced")
FIELDS = ["frame", "global_key", "flight", "split", "source"]

MISSION_RE = re.compile(r"^(\d{8})_([a-z0-9]+)_")


def frame_of(global_key: str) -> str:
    """The file name, the one id a frame keeps across the `comb_`, `migrated/`
    and flight-folder keys the three inventories use."""
    return re.sub(r"^comb_", "", global_key.rsplit("/", 1)[-1])


def flight_of(mission: str) -> str:
    """"yyyymmdd/site" from the mission metadata, or "" when it has no date."""
    m = MISSION_RE.match(mission or "")
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def local_xy(lat: float, lon: float) -> tuple[float, float]:
    return (lon * METRES_PER_DEGREE * math.cos(math.radians(lat)),
            lat * METRES_PER_DEGREE)


def load_inventory(paths=INVENTORIES) -> dict[str, dict]:
    """frame -> {global_key, flight, xy}. A frame in two inventories is one
    frame; the first inventory's key is kept."""
    out = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                key = row.get("global_key")
                if not key:
                    continue
                frame = frame_of(key)
                if frame in out:
                    continue
                md = row.get("metadata") or {}
                point = (row.get("media_attributes") or {}).get("gpsPoint")
                xy = local_xy(*map(float, point.split(","))) if point else None
                out[frame] = {"global_key": key, "xy": xy,
                              "flight": flight_of(md.get("mission", ""))}
    return out


def load_legacy(path: Path = LEGACY) -> dict[str, str]:
    """frame -> split, "" for a frame sent with no split."""
    out = {}
    for r in hc.read_csv_rows(str(path)):
        frame = frame_of(r["global_key"])
        split = r.get("split") or ""
        if out.get(frame, split) != split:
            raise ValueError(f"{path.name}: {frame} carries two splits")
        out[frame] = split
    return out


def _grid(seen_xy: dict[str, tuple[float, float]], cell: float):
    cells = defaultdict(list)
    for frame, (x, y) in seen_xy.items():
        cells[(int(x // cell), int(y // cell))].append(frame)
    return cells


def _neighbours(xy, cells, cell: float, buffer: float, seen_xy):
    cx, cy = int(xy[0] // cell), int(xy[1] // cell)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for frame in cells.get((cx + dx, cy + dy), ()):
                sx, sy = seen_xy[frame]
                if math.hypot(sx - xy[0], sy - xy[1]) <= buffer:
                    yield frame


def assign(inventory: dict[str, dict], legacy: dict[str, str], *,
           buffer: float = BUFFER_M) -> list[dict]:
    """Every inventory frame with a split and the reason for it, sorted by frame."""
    split, source = {}, {}
    for frame, s in legacy.items():
        if frame not in inventory:
            continue
        split[frame], source[frame] = (s, "legacy") if s else ("train", "sent_blank")
    seen = dict(split)
    seen_flights = {inventory[f]["flight"] for f in seen}
    seen_xy = {f: inventory[f]["xy"] for f in seen if inventory[f]["xy"]}
    cells = _grid(seen_xy, buffer)

    for frame in sorted(f for f in inventory if f not in seen):
        row = inventory[frame]
        if not row["flight"] or row["xy"] is None:
            split[frame], source[frame] = "buffered", "unplaced"
            continue
        near = {seen[n] for n in _neighbours(row["xy"], cells, buffer, buffer, seen_xy)}
        if row["flight"] in seen_flights:
            # A late frame on a flight the legacy split already covers joins
            # its neighbours, or stays out when they disagree or it has none.
            if len(near) == 1:
                split[frame], source[frame] = next(iter(near)), "near"
            else:
                split[frame], source[frame] = "buffered", "conflict" if near else "flight"
        elif near:
            split[frame], source[frame] = "buffered", "near"
        else:
            split[frame], source[frame] = "clean_test", "flight"

    return [{"frame": f, "global_key": inventory[f]["global_key"],
             "flight": inventory[f]["flight"], "split": split[f], "source": source[f]}
            for f in sorted(split)]


def to_csv_text(rows: list[dict]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def manifest(rows: list[dict], legacy: dict[str, str], *, buffer: float) -> dict:
    by_split = Counter(r["split"] for r in rows)
    by_source = Counter(r["source"] for r in rows)
    sites = defaultdict(Counter)
    for r in rows:
        sites[r["flight"].split("/")[-1] or "?"][r["split"]] += 1
    clean_flights = sorted({r["flight"] for r in rows if r["split"] == "clean_test"})
    return {"version": VERSION, "buffer_m": buffer, "unit": "flight (one date over one site)",
            "legacy_rows": len(legacy), "legacy_in_inventory": by_source["legacy"] + by_source["sent_blank"],
            "n_frames": len(rows), "by_split": dict(sorted(by_split.items())),
            "by_source": dict(sorted(by_source.items())),
            "by_site": {s: dict(sorted(c.items())) for s, c in sorted(sites.items())},
            "clean_flights": clean_flights}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def report(doc: dict, text: str) -> None:
    print(f"frames      : {doc['n_frames']:,}, legacy rows kept "
          f"{doc['legacy_in_inventory']:,} of {doc['legacy_rows']:,}")
    print("by split    : " + ", ".join(f"{k} {v:,}" for k, v in doc["by_split"].items()))
    print("by source   : " + ", ".join(f"{k} {v:,}" for k, v in doc["by_source"].items()))
    print(f"clean       : {doc['by_split'].get('clean_test', 0):,} frames on "
          f"{len(doc['clean_flights'])} flights")
    print("by site     :")
    for site, c in doc["by_site"].items():
        print(f"  {site:18s} " + ", ".join(f"{k} {v}" for k, v in c.items()))
    print(f"buffer      : {doc['buffer_m']:.0f} m")
    print(f"sha256      : {sha256(text)}")


def verify(text: str, doc: dict) -> int:
    for path in (OUT, META):
        if not path.exists():
            print(f"MISSING {path}", file=sys.stderr)
            return 1
    if OUT.read_text(encoding="utf-8") != text:
        print(f"DRIFT: {OUT} is not what the inventories and {LEGACY.name} produce",
              file=sys.stderr)
        return 1
    on_disk = json.loads(META.read_text(encoding="utf-8"))
    moved = [k for k in doc if on_disk.get(k) != doc[k]]
    if moved:
        print(f"DRIFT: {META} differs in {moved}", file=sys.stderr)
        return 1
    print(f"{OUT.name} reproduces byte for byte, sha256 {sha256(text)}")
    return 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=hc.summarise(__doc__),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the csv and the json")
    ap.add_argument("--verify", action="store_true",
                    help="rebuild and exit non-zero if the committed files differ")
    ap.add_argument("--buffer", type=float, default=BUFFER_M, help="metres")
    ap.add_argument("--legacy", type=Path, default=LEGACY)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    legacy = load_legacy(args.legacy)
    rows = assign(load_inventory(), legacy, buffer=args.buffer)
    text = to_csv_text(rows)
    doc = manifest(rows, legacy, buffer=args.buffer)
    if args.verify:
        return verify(text, doc)
    report(doc, text)
    if args.write:
        OUT.write_text(text, encoding="utf-8")
        META.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {OUT} and {META}")
    else:
        print("nothing written, pass --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
