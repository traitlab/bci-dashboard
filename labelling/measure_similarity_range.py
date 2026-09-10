"""
How far apart do two photos have to be before the model stops seeing kin?

A held-back set drawn frame by frame leaks: the frame next to a held-back one
was shot from the same hover over the same crown, and the model has as good as
seen the answer. Drawing by spatial block stops that only if the block, and
the buffer around it, is wider than the distance over which a photo still
looks like its neighbours. This measures that distance on the labelled frames,
where the species is known.

For every within-site pair of labelled zoom frames: the cosine similarity of
their Pl@ntNet embeddings (``predict/embed.py``, 768 numbers a photo) against
the metres between the drone positions Labelbox recorded. Binned by distance,
for all pairs, for same-species pairs, and for same-species pairs from
different flights. The range is where the same-species curve reaches its
plateau: past it, two frames of one species look no more alike for being near.

The drone position is where the aircraft hovered, not where the crown is
(``polygon_identity.py``), so every metre here is a hover-to-hover distance.

Runs against the speciesfirst virtualenv, which carries labelfirst for the run
record; the measurement itself is numpy only:

  "$SPECIESFIRST/.venv/bin/python" labelling/measure_similarity_range.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "dashboard"))

import core as hc
from draw_field_sample import flight_of, site_of
from embeddings_io import l2_normalise, load_embeddings
from polygon_identity import gps_of

REPO = Path(__file__).resolve().parents[1]
DEFAULT_NPZ = REPO / "data" / "embeddings_labelled" / "embeddings.npz"
DEFAULT_CACHE = REPO / "data" / "embeddings_labelled" / "cache"
DEFAULT_INVENTORY = REPO / "data" / "dataset_rows_combined.jsonl"
DEFAULT_OUT = REPO / "data" / "model_health" / "similarity_range.json"
# The sidecar name ``rank_queue.write_run_record`` uses. Not imported from
# there: that module needs labelfirst at import and this one only at the end.
RUN_RECORD_SUFFIX = ".run.json"

# Bin edges in metres. Fine near zero, where one hover holds several frames,
# and coarse past a few hundred metres, where nothing is expected to change.
BIN_EDGES = (0, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 1000, 2000)
MAX_DISTANCE_M = BIN_EDGES[-1]
# The plateau is the mean over the last PLATEAU_BINS bins; a bin whose
# same-species similarity sits within PLATEAU_TOL of it is "at the plateau".
PLATEAU_BINS = 3
PLATEAU_TOL = 0.01
# A bin with fewer same-species pairs than this does not vote on the plateau.
# On the labelled frames today the 1000-2000 m bin holds 16 pairs, and its
# mean sits 0.05 under the bins before it, which is one thin bin, not the
# curve. The literal rule over every bin is written to the file as well.
MIN_PLATEAU_PAIRS = 100
# The sanity check: a frame with another frame this close is one hover.
NEAR_M = 5.0
METRES_PER_DEGREE = 111320.0
TELE_SUFFIX = "tele"


def is_tele(key: str) -> bool:
    """The telephoto camera, off the filename stem. Never labelled and a
    different lens, so it is out even if a label appears one day."""
    return hc.frame_key(key).endswith(TELE_SUFFIX)


def load_flights(path: Path) -> dict[str, dict]:
    """global_key -> {flight, site, gps} for every inventory row with a
    readable position. A row without one is left out, and counted by the
    caller."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            key = row.get("global_key")
            if not key:
                continue
            url = row.get("row_data") or ""
            out[key] = {"flight": flight_of(url), "site": site_of(url), "gps": gps_of(row)}
    return out


def local_xy(gps: np.ndarray) -> np.ndarray:
    """Equirectangular metres, the same rule ``polygon_identity.gps_clusters``
    uses: 111,320 m a degree, longitude scaled by cos(latitude)."""
    lat, lon = gps[:, 0], gps[:, 1]
    x = lon * METRES_PER_DEGREE * np.cos(np.radians(lat))
    y = lat * METRES_PER_DEGREE
    return np.column_stack([x, y])


def pair_table(X: np.ndarray, xy: np.ndarray, species: list[str], flights: list[str],
               sites: list[str], max_m: float = MAX_DISTANCE_M) -> dict[str, np.ndarray]:
    """Every unordered within-site pair up to ``max_m`` apart, as flat arrays.

    Within site only: a cross-site pair is kilometres apart and says nothing
    about the block size a site would be cut into.
    """
    n = len(X)
    i, j = np.triu_indices(n, k=1)
    site_arr = np.asarray(sites)
    keep = site_arr[i] == site_arr[j]
    i, j = i[keep], j[keep]
    metres = np.hypot(*(xy[i] - xy[j]).T)
    keep = metres <= max_m
    i, j, metres = i[keep], j[keep], metres[keep]
    sp = np.asarray(species)
    fl = np.asarray(flights)
    return {"i": i, "j": j, "metres": metres,
            "cosine": np.einsum("ij,ij->i", X[i], X[j]),
            "same_species": sp[i] == sp[j],
            "same_flight": fl[i] == fl[j]}


def bin_table(metres: np.ndarray, cosine: np.ndarray, masks: dict[str, np.ndarray],
              edges=BIN_EDGES) -> list[dict]:
    """Mean cosine similarity and pair count per distance bin, per population.

    Bins are ``[lo, hi)`` except the last, which is closed so a pair at exactly
    ``max_m`` is counted once rather than dropped. An empty bin reports
    ``None`` for its mean, not zero: zero is a similarity.
    """
    rows = []
    for k, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        in_bin = (metres >= lo) & ((metres < hi) | ((k == len(edges) - 2) & (metres == hi)))
        row = {"lo_m": lo, "hi_m": hi}
        for name, mask in masks.items():
            sel = in_bin & mask
            n = int(sel.sum())
            row[name] = {"n": n, "mean": float(cosine[sel].mean()) if n else None}
        rows.append(row)
    return rows


def plateau_range(rows: list[dict], population: str = "same_species",
                  last: int = PLATEAU_BINS, tol: float = PLATEAU_TOL,
                  min_pairs: int = 1) -> dict:
    """Where the curve flattens.

    Plateau: the mean over the last ``last`` bins of the population that hold
    at least ``min_pairs`` pairs. Range: the lower edge of the first non-empty
    bin whose mean is within ``tol`` of the plateau. The bins past it are
    checked too, and any that leave the plateau again are named, so a range
    picked off a single noisy bin is visible. When no bin reaches the plateau
    the range is ``None`` and the reason is written, not a guess.
    """
    filled = [r for r in rows if r[population]["mean"] is not None]
    voting = [r for r in filled if r[population]["n"] >= min_pairs]
    base = {"tolerance": tol, "min_plateau_pairs": min_pairs,
            "plateau_bins": [r["lo_m"] for r in voting[-last:]]}
    if len(voting) < last + 1:
        return {**base, "range_m": None, "plateau": None, "bins_in_plateau": [],
                "reason": f"{len(voting)} bins with >= {min_pairs} pairs, need > {last}"}
    plateau = float(np.mean([r[population]["mean"] for r in voting[-last:]]))
    at = [r for r in filled if abs(r[population]["mean"] - plateau) <= tol]
    if not at:
        return {**base, "range_m": None, "plateau": plateau, "bins_in_plateau": [],
                "reason": f"no bin within {tol} of the last-{last}-bin mean"}
    first = at[0]
    after = [r for r in filled if r["lo_m"] > first["lo_m"]]
    leaves = [r["lo_m"] for r in after if abs(r[population]["mean"] - plateau) > tol]
    return {**base, "range_m": first["lo_m"], "plateau": plateau,
            "bins_in_plateau": [r["lo_m"] for r in at],
            "bins_leaving_plateau_after_range": leaves}


def rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared, the way scipy does it; numpy only."""
    order = np.argsort(a, kind="mergesort")
    s = a[order]
    boundary = np.concatenate([[True], s[1:] != s[:-1]])
    group = np.cumsum(boundary) - 1
    starts = np.flatnonzero(boundary)
    ends = np.append(starts[1:], len(s))
    mean_rank = (starts + ends - 1) / 2.0 + 1.0
    ranks = np.empty(len(a))
    ranks[order] = mean_rank[group]
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2:
        return float("nan")
    ra, rb = rankdata(a), rankdata(b)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float(ra @ ra) * float(rb @ rb))
    return float(ra @ rb) / denom if denom else float("nan")


def nearest_neighbours(xy: np.ndarray, species: list[str], flights: list[str]) -> dict:
    """Per frame, the nearest other frame of any species, and the nearest
    frame of the same species from another flight. No site cap, no distance
    cap: this is a check on the data, not on the blocks."""
    n = len(xy)
    d = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    np.fill_diagonal(d, np.inf)
    any_nn = d.min(axis=1)
    sp = np.asarray(species)
    fl = np.asarray(flights)
    kin = (sp[:, None] == sp[None, :]) & (fl[:, None] != fl[None, :])
    kin_d = np.where(kin, d, np.inf).min(axis=1)
    has_kin = np.isfinite(kin_d)
    return {"n_frames": n,
            "nearest_any_under_5m": int((any_nn < NEAR_M).sum()),
            "nearest_any_median_m": float(np.median(any_nn)),
            "frames_with_same_species_other_flight": int(has_kin.sum()),
            "nearest_same_species_other_flight_median_m":
                float(np.median(kin_d[has_kin])) if has_kin.any() else None}


def load_species(path: Path, col: str) -> dict[str, str]:
    """global_key -> accepted name, frames without a name left out."""
    return {r["global_key"]: r[col] for r in hc.read_csv_rows(str(path))
            if r.get("global_key") and r.get(col)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assemble(keys: list[str], emb: np.ndarray, species: dict[str, str],
             inventory: dict[str, dict]) -> tuple[dict, dict]:
    """The frames the measurement runs on, and why each excluded one is out."""
    excluded = {"tele": 0, "no_species": 0, "no_inventory_row": 0, "no_gps": 0,
                "no_flight": 0}
    idx = []
    for k, key in enumerate(keys):
        row = inventory.get(key)
        if is_tele(key):
            excluded["tele"] += 1
        elif key not in species:
            excluded["no_species"] += 1
        elif row is None:
            excluded["no_inventory_row"] += 1
        elif row["gps"] is None:
            excluded["no_gps"] += 1
        elif not row["flight"] or not row["site"]:
            excluded["no_flight"] += 1
        else:
            idx.append(k)
    used = {"keys": [keys[k] for k in idx],
            "X": l2_normalise(emb[idx]),
            "species": [species[keys[k]] for k in idx],
            "flights": [inventory[keys[k]]["flight"] for k in idx],
            "sites": [inventory[keys[k]]["site"] for k in idx],
            "xy": local_xy(np.array([inventory[keys[k]]["gps"] for k in idx]))}
    return used, excluded


def measure(used: dict) -> dict:
    pairs = pair_table(used["X"], used["xy"], used["species"], used["flights"],
                       used["sites"])
    masks = {"all": np.ones(len(pairs["metres"]), dtype=bool),
             "same_species": pairs["same_species"],
             "same_species_other_flight": pairs["same_species"] & ~pairs["same_flight"]}
    rows = bin_table(pairs["metres"], pairs["cosine"], masks)
    rng = plateau_range(rows, min_pairs=MIN_PLATEAU_PAIRS)
    first, at = rows[0], next((r for r in rows if r["lo_m"] == rng["range_m"]), None)
    return {
        "bins": rows,
        "range": rng,
        "range_every_bin_votes": plateau_range(rows),
        "at_0_10m": {p: first[p]["mean"] for p in ("all", "same_species")},
        "at_plateau_bin": {p: at[p]["mean"] for p in ("all", "same_species")} if at else None,
        "spearman_cosine_distance_vs_metres":
            spearman(1.0 - pairs["cosine"], pairs["metres"]),
        "n_pairs_within_site_under_cap": int(len(pairs["metres"])),
        "n_species": len(set(used["species"])),
        "n_flights": len(set(used["flights"])),
        "n_sites": len(set(used["sites"])),
        "nearest": nearest_neighbours(used["xy"], used["species"], used["flights"]),
    }


def run_record(npz: Path, n_used: int, n_keys: int, **extra) -> dict:
    """labelfirst's envelope, the shape ``rank_queue.write_run_record`` writes.
    Imported here so the measurement itself stays numpy only."""
    from labelfirst.io.queue import RunRecord
    return asdict(RunRecord(
        strategy="similarity_range", seed=0, k=n_used, n_pool=n_keys, n_labeled=n_used,
        embedding_path=str(npz), embedding_sha256=sha256_file(npz),
        extra={"by": Path(__file__).name,
               "written": dt.datetime.now(dt.timezone.utc).date().isoformat(), **extra}))


def print_table(result: dict) -> None:
    print(f"{'bin (m)':>12} {'all n':>8} {'all':>7} {'same n':>8} {'same':>7} "
          f"{'xflight n':>10} {'xflight':>8}")
    for r in result["bins"]:
        cells = [f"{r['lo_m']:>5}-{r['hi_m']:<6}"]
        for p in ("all", "same_species", "same_species_other_flight"):
            m = r[p]["mean"]
            cells.append(f"{r[p]['n']:>8}" + (f" {m:>7.4f}" if m is not None else "     n/a"))
        print("  ".join(cells))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=hc.summarise(__doc__))
    p.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--species-csv", type=Path, default=Path(hc.GT_CSV))
    p.add_argument("--species-col", default="wcvp_canonical_name")
    p.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    keys, emb = load_embeddings(args.npz, args.cache_dir)
    species = load_species(args.species_csv, args.species_col)
    inventory = load_flights(args.inventory)
    used, excluded = assemble(keys, emb, species, inventory)
    if len(used["keys"]) < 2:
        raise SystemExit(f"{len(used['keys'])} usable frames of {len(keys)}: {excluded}")
    print(f"{len(used['keys'])} of {len(keys)} embedded frames used; excluded {excluded}")
    result = measure(used)
    print_table(result)
    print(f"range {result['range']['range_m']} m, plateau {result['range']['plateau']}, "
          f"spearman {result['spearman_cosine_distance_vs_metres']:+.4f}")
    print(f"nearest: {result['nearest']}")
    doc = {"kind": "similarity_range",
           "inputs": {"embeddings_npz": os.path.relpath(args.npz, REPO),
                      "embeddings_sha256": sha256_file(args.npz),
                      "gt_csv": os.path.relpath(args.species_csv, REPO),
                      "gt_sha256": sha256_file(args.species_csv),
                      "inventory": os.path.relpath(args.inventory, REPO),
                      "inventory_sha256": sha256_file(args.inventory)},
           "params": {"bin_edges_m": list(BIN_EDGES), "plateau_bins": PLATEAU_BINS,
                      "plateau_tolerance": PLATEAU_TOL,
                      "min_plateau_pairs": MIN_PLATEAU_PAIRS, "near_m": NEAR_M,
                      "metres_per_degree": METRES_PER_DEGREE},
           "population": {"n_embedded": len(keys), "n_used": len(used["keys"]),
                          "excluded": excluded},
           **result}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record = run_record(args.npz, len(used["keys"]), len(keys), excluded=excluded)
    run_path = args.out.with_suffix(args.out.suffix + RUN_RECORD_SUFFIX)
    run_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out} and {run_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
