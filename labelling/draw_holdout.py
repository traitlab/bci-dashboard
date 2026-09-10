"""Hold whole flights out of the labelled frames, and keep the draw on record.

The split in data/splits.csv is drawn frame by frame. Drone frames from one
flight over one site are shot seconds apart from the same hover, so a test
frame there is a near-copy of a train frame and the test score says more about
the flight than about the species. tests/test_split_blocking.py pins that every
test frame today shares its flight with a train frame. This draws the set that
does not: whole flights, held together, tele frames included.

The unit is the flight because the flight is the structure that produces the
dependence. Two frames of one crown from one hover are not two observations;
they are one observation photographed twice, and a holdout that splits them
grades the model on frames it has as good as seen (Roberts et al. 2017;
Kattenborn et al. 2022). Holding a flight whole is what makes "a flight the
labels never saw" a true sentence. A flight is one date over one site, read
out of the mission folder in each frame's Labelbox URL, the same way
labelling/draw_field_sample.py reads it.

Around every held frame a 30 m buffer drops train frames from another flight.
labelling/measure_similarity_range.py measured how far two frames of one species
still look alike to the model: the lift is inside the same hover, under 30 m,
and past it a nearer frame adds nothing the flight did not. Frames in the
buffer are neither held nor train; they are listed under `buffered` so the
count is on record.

The draw is stratified by species. Every species with two or more flights keeps
at least one in train, so every held species can be graded. A species flown
once cannot lose its only flight and is listed as ungradeable rather than
dropped quietly. The pool is every labelled frame that can be placed on a
flight and at a GPS position. A labelled frame with no flight or no position is
counted in the manifest, never silently dropped.

The pool gets a committed manifest for the same reason the field sample has
one: the labels and the inventory move, and the manifest is the frozen record
of what the pool was on the day of the draw. `--verify` re-draws from it rather
than re-deriving it. No count is written into this file; every number is read
off the data on the day it runs.

    "$SPECIESFIRST/.venv/bin/python" labelling/draw_holdout.py --rebuild-pool
    "$SPECIESFIRST/.venv/bin/python" labelling/draw_holdout.py --rebuild-pool --write
    "$SPECIESFIRST/.venv/bin/python" labelling/draw_holdout.py --verify

References:

Roberts, D. R. et al. 2017. Cross-validation strategies for data with temporal,
spatial, hierarchical, or phylogenetic structure. Ecography 40:913-929.

Kattenborn, T. et al. 2022. Spatially autocorrelated training and validation
samples inflate performance assessment of convolutional neural networks. ISPRS
Open Journal of Photogrammetry and Remote Sensing 5:100018.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "dashboard"))

import core as hc
from draw_field_sample import flight_of
from polygon_identity import gps_of
from speciesfirst.grouped_holdout import build_fold

REPO = Path(__file__).resolve().parents[1]
VERSION = "v1"
POOL = REPO / "input" / f"holdout_{VERSION}_pool.csv"
OUT = REPO / "input" / f"holdout_{VERSION}.csv"
META = REPO / "input" / f"holdout_{VERSION}.json"
INVENTORY = REPO / "data" / "dataset_rows_combined.jsonl"
SPECIES_COL = "wcvp_canonical_name"

# The day of the draw, like draw_field_sample.SEED. A redraw under another seed
# is another version, with its own files.
SEED = 20260910
HELD_FRAC = 0.2
MIN_TRAIN_GROUPS = 1
# Metres. Same-hover lift was measured under 30 m; see the module docstring.
BUFFER_M = 30.0
# Equirectangular metres, the rule polygon_identity.gps_clusters uses.
METRES_PER_DEGREE = 111320.0

POOL_FIELDS = ["global_key", "species", "flight", "x", "y"]
FIELDS = ["global_key", "species", "flight", "role"]
ROLES = ("held", "train", "buffered")
EXCLUSIONS = ("no_inventory_row", "no_flight", "no_gps")


def local_xy(lat: float, lon: float) -> tuple[float, float]:
    """Metres east and north of the equator and the prime meridian, longitude
    scaled by the cosine of the latitude. Only differences are ever used."""
    return (lon * METRES_PER_DEGREE * math.cos(math.radians(lat)),
            lat * METRES_PER_DEGREE)


def load_species(path: Path = Path(hc.GT_CSV), col: str = SPECIES_COL) -> dict[str, str]:
    """global_key -> accepted name, frames without a name left out."""
    return {r["global_key"]: r[col] for r in hc.read_csv_rows(str(path))
            if r.get("global_key") and r.get(col)}


def load_flights(path: Path = INVENTORY) -> dict[str, dict]:
    """global_key -> {flight, gps} over the Labelbox inventory. `flight` is
    "" and `gps` is None where the row carries neither, so the caller can
    count each kind of gap by name."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            key = row.get("global_key")
            if key:
                out[key] = {"flight": flight_of(row.get("row_data") or ""),
                            "gps": gps_of(row)}
    return out


def eligible(species: dict[str, str], inventory: dict[str, dict]):
    """The pool rows, sorted by key, and how many labelled frames are out and why.

    A frame is out when the inventory has no row for it, when its URL carries
    no mission folder, or when Labelbox recorded no position for it. Each is
    counted apart: a missing row is a stale inventory, a missing folder is a
    naming slip, a missing position is a camera that did not write one.
    """
    rows, excluded = [], dict.fromkeys(EXCLUSIONS, 0)
    for key in sorted(species):
        row = inventory.get(key)
        if row is None:
            excluded["no_inventory_row"] += 1
        elif not row["flight"]:
            excluded["no_flight"] += 1
        elif row["gps"] is None:
            excluded["no_gps"] += 1
        else:
            x, y = local_xy(*row["gps"])
            rows.append({"global_key": key, "species": species[key],
                         "flight": row["flight"], "x": f"{x:.2f}", "y": f"{y:.2f}"})
    return rows, excluded


def draw(pool: list[dict], *, seed: int = SEED, held_frac: float = HELD_FRAC,
         min_train_groups: int = MIN_TRAIN_GROUPS, buffer: float = BUFFER_M):
    """The role of every pool frame, and the fold it came from.

    Reads x and y back off the pool rows as text, the way `--verify` will, so
    the draw from a freshly derived pool and the draw from the committed one
    see the same metres.
    """
    items = {r["global_key"]: (r["species"], r["flight"]) for r in pool}
    xy = {r["global_key"]: (float(r["x"]), float(r["y"])) for r in pool}
    fold = build_fold(items, seed=seed, held_frac=held_frac,
                      min_train_groups=min_train_groups, xy=xy, buffer=buffer)
    fold.assert_valid(items)
    role_of = {}
    for role, members in zip(ROLES, (fold.held, fold.train, fold.buffered)):
        for key in members:
            role_of[key] = role
    rows = [{"global_key": r["global_key"], "species": r["species"],
             "flight": r["flight"], "role": role_of[r["global_key"]]}
            for r in sorted(pool, key=lambda r: r["global_key"])]
    return rows, fold


def to_csv_text(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row[k] for k in fields})
    return buf.getvalue()


def read_pool(path: Path = POOL) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return sorted(csv.DictReader(fh), key=lambda r: r["global_key"])


def read_roles(path: Path = OUT) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def manifest(fold, excluded: dict, n_pool: int, n_labelled: int, *, seed: int,
             held_frac: float, min_train_groups: int, buffer: float) -> dict:
    """The facts a later reader needs to trust the set, every one read off the
    draw. `stats` is the fold's own dict, counts as floats the way it keeps them."""
    return {"version": VERSION, "seed": seed, "held_frac": held_frac,
            "min_train_groups": min_train_groups, "buffer_m": buffer,
            "group": "flight (one date over one site)",
            "n_labelled": n_labelled, "n_pool": n_pool,
            "excluded": dict(excluded),
            "stats": dict(fold.stats),
            "held_flights": sorted(fold.held_groups),
            "ungradeable_species": sorted(fold.ungradeable_species)}


def to_json_text(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def report(doc: dict, text: str) -> None:
    s = doc["stats"]
    ex = doc["excluded"]
    print(f"labelled        : {doc['n_labelled']:,} frames with a species")
    print(f"pool            : {doc['n_pool']:,} frames on {int(s['n_groups'])} flights; "
          f"out: " + ", ".join(f"{k} {ex[k]}" for k in EXCLUSIONS))
    print(f"held            : {int(s['n_held_groups'])} of {int(s['n_groups'])} flights "
          f"({s['held_frac_achieved']:.1%}), {int(s['n_held']):,} frames")
    print(f"train           : {int(s['n_train']):,} frames, buffered "
          f"{int(s['n_buffered']):,} within {doc['buffer_m']:.0f} m of a held frame")
    print(f"species         : {int(s['n_species_gradeable'])} gradeable, "
          f"{int(s['n_species_ungradeable'])} with one flight only")
    print(f"seed            : {doc['seed']}, held_frac {doc['held_frac']}")
    print(f"sha256          : {sha256(text)}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=hc.summarise(__doc__),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild-pool", action="store_true",
                    help="derive the pool from the labels and the inventory "
                         "instead of reading the committed manifest")
    ap.add_argument("--write", action="store_true",
                    help="write the pool manifest, the roles and the json")
    ap.add_argument("--verify", action="store_true",
                    help="re-draw from the committed manifest and exit "
                         "non-zero on any drift")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--held-frac", type=float, default=HELD_FRAC)
    ap.add_argument("--min-train-groups", type=int, default=MIN_TRAIN_GROUPS)
    ap.add_argument("--buffer", type=float, default=BUFFER_M, help="metres")
    ap.add_argument("--gt", type=Path, default=Path(hc.GT_CSV))
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    return ap.parse_args(argv)


def verify(pool_text: str, text: str, doc: dict) -> int:
    """Byte-compare the pool round trip and the roles, and the drawn facts in
    the json, against what is committed."""
    for path in (POOL, OUT, META):
        if not path.exists():
            print(f"MISSING {path}", file=sys.stderr)
            return 1
    if POOL.read_text(encoding="utf-8") != pool_text:
        print(f"DRIFT: {POOL} does not round-trip through its own columns",
              file=sys.stderr)
        return 1
    if OUT.read_text(encoding="utf-8") != text:
        print(f"DRIFT: {OUT} is not what seed {doc['seed']} draws from {POOL.name}",
              file=sys.stderr)
        return 1
    on_disk = json.loads(META.read_text(encoding="utf-8"))
    drawn = ("version", "seed", "held_frac", "min_train_groups", "buffer_m", "n_pool",
             "stats", "held_flights", "ungradeable_species")
    moved = [k for k in drawn if on_disk.get(k) != doc[k]]
    if moved:
        print(f"DRIFT: {META} differs from the redraw in {moved}", file=sys.stderr)
        return 1
    print(f"{OUT.name} redraws byte for byte, sha256 {sha256(text)}")
    return 0


def main(argv=None) -> int:
    """Draw the set, or prove the committed one still redraws byte for byte."""
    args = parse_args(argv)
    if args.rebuild_pool:
        species = load_species(args.gt)
        pool, excluded = eligible(species, load_flights(args.inventory))
        n_labelled = len(species)
    else:
        pool = read_pool()
        committed = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
        excluded = committed.get("excluded", dict.fromkeys(EXCLUSIONS, 0))
        n_labelled = committed.get("n_labelled", len(pool))
    if not pool:
        print("ERROR: the pool is empty; nothing to hold out", file=sys.stderr)
        return 1
    pool_text = to_csv_text(pool, POOL_FIELDS)
    rows, fold = draw(pool, seed=args.seed, held_frac=args.held_frac,
                      min_train_groups=args.min_train_groups, buffer=args.buffer)
    text = to_csv_text(rows, FIELDS)
    doc = manifest(fold, excluded, len(pool), n_labelled, seed=args.seed,
                   held_frac=args.held_frac, min_train_groups=args.min_train_groups,
                   buffer=args.buffer)

    if args.verify:
        return verify(pool_text, text, doc)

    report(doc, text)
    if args.write:
        POOL.write_text(pool_text, encoding="utf-8")
        OUT.write_text(text, encoding="utf-8")
        META.write_text(to_json_text(doc), encoding="utf-8")
        print(f"wrote {POOL}, {OUT} and {META}")
    else:
        print("nothing written, pass --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
