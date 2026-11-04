"""Per-frame reading and derivation for `catalog_batches.py`, offline.

The pool, the pin file and the rarity tables (`input/bci_census.csv`,
`species_iucn.csv`, `species_range.csv`) it reads, the rarity rank of a species,
the crown, site and season of a frame, the spread caps of the packer, the liana
share that splits trees from lianas, and the seeded shuffle inside a batch. The
only file written is the pin file. Nothing here packs a batch.
"""
from __future__ import annotations

import csv
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

from queues import CONTROL_SEED

RARITY_COLUMNS = ["census_stems", "iucn_category", "wcvp_regions"]
# Spread caps on the queue places of a batch (85 of 100): at most this many
# frames of one mission, one site, one season. The site and season caps leave a
# fifth of the places to the other sites and seasons while they have frames; the
# packer fills from capped rows only when nothing else is left, so no batch
# comes out short. The pool's species-grouped packing already lands at most 14
# per mission, so that cap binds only on a lopsided pool.
MISSION_CAP = 20
SITE_CAP = 68
SEASON_CAP = 68
# The crown a frame shows: the number before "tele" in a waypoint-mission key
# (DJI_..._V_7524tele.JPG is crown 7524 of its mission). Numbers restart per
# mission, so the crown is the pair. A key without one is its own crown.
CROWN_SUFFIX = re.compile(r"_(\d+)tele\.JPG$", re.IGNORECASE)
# A frame whose top-5 Pl@ntNet score is at least this much on liana species goes
# to the liana batches. Probe on 2,945 labelled tree or liana frames: AUC 0.96.
LIANA_SHARE = 0.5
INPUT = Path(__file__).resolve().parents[1] / "input"
CENSUS_CSV = INPUT / "bci_census.csv"       # species,n: stems in the BCI 50-ha census
IUCN_CSV = INPUT / "species_iucn.csv"       # species,iucn_category: every non-LC category
RANGE_CSV = INPUT / "species_range.csv"     # species,wcvp_regions: WGSRPD regions in WCVP
# IUCN categories in the order a label serves conservation. Anything else, or no
# category (which includes LC: the file lists only non-LC), sorts after them.
IUCN_ORDER = ["EW", "CR", "EN", "VU", "NT", "LR/nt", "DD"]


def read_species_column(path: Path, column: str) -> dict:
    """species (lower-cased) -> column value, or empty when the file is absent."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["species"].strip().lower(): r[column].strip() for r in csv.DictReader(f)}


def rarity_rank(species_of_key: dict, census: dict, iucn: dict, wcvp_range: dict) -> dict:
    """global_key -> rank, lower first: threatened (IUCN_ORDER), then fewest census
    stems, then (among species the census does not list, or with equal stems) the
    fewest WCVP regions, then no range data. Ties keep the queue's own order."""
    def key(sp):
        sp = sp.lower()
        cat = iucn.get(sp)
        n, regions = census.get(sp), wcvp_range.get(sp)
        return (IUCN_ORDER.index(cat) if cat in IUCN_ORDER else len(IUCN_ORDER),
                int(n) if n else float("inf"), int(regions) if regions else float("inf"))
    order = sorted({key(sp) for sp in species_of_key.values()})
    rank_of = {k: i for i, k in enumerate(order)}
    return {k: rank_of[key(sp)] for k, sp in species_of_key.items()}


def read_pool(path: Path) -> dict[str, str]:
    """global_key -> image_url, in file order. A key twice is a stop: it would be
    packed twice into one round."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pool = {r["global_key"].strip(): r["image_url"].strip() for r in rows}
    if len(pool) != len(rows):
        sys.exit(f"ERROR: {path} lists {len(rows) - len(pool)} global keys more than once.")
    return pool


def crown_of(key: str, mission: str) -> str:
    m = CROWN_SUFFIX.search(key)
    return f"{mission}/{m.group(1)}" if m else f"{mission}/{key}"


def one_frame_per_crown(pool: dict, mission: dict) -> tuple[dict, dict]:
    """(crown_id of every key, key -> the earlier key of the same crown). One
    frame of a crown goes to the botanist; its label is propagated to the rest
    (`label_from` in frames.csv) instead of costing a second look."""
    crown = {k: crown_of(k, mission[k]) for k in pool}
    first: dict = {}
    same = {}
    for k, c in crown.items():
        if c in first:
            same[k] = first[c]
        else:
            first[c] = k
    return crown, same


def site_of(mission: str) -> str:
    """The second part of `<yyyymmdd>_<site>_<waypoint>_<aircraft>`, or blank."""
    parts = mission.split("_")
    return parts[1] if len(parts) > 2 else ""


def season_of(mission: str) -> str:
    """BCI's dry season (December to April) or wet season (May to November) of
    the mission date, as `<year>-dry` or `<year>-wet`; blank without a date."""
    m = re.match(r"(\d{4})(\d{2})\d{2}_", mission)
    if not m:
        return ""
    year, month = m.group(1), int(m.group(2))
    return f"{year}-dry" if month <= 4 or month == 12 else f"{year}-wet"


def spread_caps(mission: dict) -> tuple:
    """The `group_caps` of `chunk_send_batches` for the pool: mission, site, season."""
    return ((mission, MISSION_CAP),
            ({k: site_of(m) for k, m in mission.items()}, SITE_CAP),
            ({k: season_of(m) for k, m in mission.items()}, SEASON_CAP))


def propagate_crown_labels(same_crown: dict, labels: dict) -> dict:
    """Labels for the frames not sent because another frame of their crown was:
    key -> the label of the frame it was held behind, where that one is labelled."""
    return {k: labels[src] for k, src in same_crown.items() if src in labels}


def liana_share(ranked: list, form_of) -> float:
    """The share of the top-5 score (``ranked``: (species, score) pairs) on species
    ``form_of`` calls liana. A species with no growth form counts as not liana."""
    top = ranked[:5]
    total = sum(s for _, s in top)
    return sum(s for sp, s in top if form_of(sp) == "liana") / total if total else 0.0


def growth_group(share: float, threshold: float = LIANA_SHARE) -> str:
    return "liana" if share >= threshold else "tree"


# The batches kept as handed out to the collaborator.
PINS_CSV = Path(__file__).resolve().parents[1] / "input" / "pinned_batches.csv"
PIN_FIELDS = ["batch_id", "global_key", "picked_by"]


def read_pins(path: Path) -> list[tuple[int, str, str]]:
    """(batch number, global_key, picked_by) of the pin file; absent is empty.
    A blank picked_by reads as a queue pick."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [(int(r["batch_id"]), r["global_key"].strip(),
                 (r.get("picked_by") or "queue").strip()) for r in csv.DictReader(f)]


def write_pins(path: Path, batch_rows: list, pins: list, sent_nums: set,
               hand_out: int = 0, ahead: int = 0) -> list[int]:
    """Write the pinned batches of the output, topped up to ``ahead`` unsent ones,
    plus ``hand_out`` more (the lowest numbers neither pinned nor sent); returns
    the pinned numbers."""
    pinned = {b for b, _, _ in pins} - sent_nums
    free = sorted({b[0] for b in batch_rows} - pinned - sent_nums)
    pinned |= set(free[:max(0, ahead - len(pinned)) + hand_out])
    rows = [(b[0], b[2], b[4]) for b in batch_rows if b[0] in pinned]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(PIN_FIELDS)
        w.writerows(sorted(rows))
    return sorted({r[0] for r in rows})


def shuffle_within(batch_rows: list) -> list:
    """The same batches, each in a seeded random order: the botanist must not read
    the prediction off the species grouping. Seeded per batch, so a refresh that keeps
    a batch's frames keeps its order."""
    by_batch: dict = {}
    for b in batch_rows:
        by_batch.setdefault(b[0], []).append(b)
    for n, rows in by_batch.items():
        random.Random(f"{CONTROL_SEED}:{n}").shuffle(rows)
    return [b for rows in by_batch.values() for b in rows]
