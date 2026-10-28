"""Pack the 2024_bci catalog pool into labelling batches, offline.

The catalog pool is the Labelbox dataset rows that sit in no project, with a
Pl@ntNet answer cached for each frame (`predict/photo.py --input
data/predictions_catalog_2026/input.csv`). This does for that pool what
`dashboard/measure.py` does for the main one, by calling the same code: the
queue of each frame is `queues.send_first_rows` (so `queue_of_prediction`), the
packing into 65 queue / 20 low-confidence / 15 random control per batch of 100
is `queues.chunk_send_batches`. Per-species label support and accuracy, and the
name canonicaliser, come from the labelled history exactly as `measure.send_queue`
reads them (`health.load_health`). Nothing here decides a queue rule.

Two things differ from the main queue. The catalog frames have no embedding
vectors, so inside each queue they run in ecological rarity order instead of
novelty order (`rarity_rank`): IUCN threatened species first, then by stems in
the BCI 50-ha census (`input/bci_census.csv`, fewest first), then the species
the census does not list by WCVP range size (`input/species_range.csv`, fewest
botanical regions first, the endemism proxy), confidence breaking ties. Label scarcity decides the
queue, rarity decides the order inside it. And every frame of a mission listed
in `input/priority_missions.txt` (ground data on its crowns) goes out first, in
its own batches, whatever its queue.

Writes to --out:
  send_batches.csv      what `dispatch_round.py --batch N` sends. data_row_id is
                        blank: no local inventory has these rows, and the
                        dispatcher looks the ids up in the dataset by global key.
  send_first_queue.csv  the same frames in queue order, beside it because
                        `dispatch_round.py` reads the species, confidence and
                        support for the round ledger from there.
  frames.csv            every pool frame: its queue and batch, or why it has none.

    python labelling/catalog_batches.py --pool data/predictions_catalog_2026/input.csv \\
        --cache data/predictions_catalog_2026/cache --out build/catalog_batches
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import growth_form
from core import (
    LEDGER_DIR,
    add_input_flags,
    add_label_source_flag,
    fmt,
    ledger_keys,
    mission_of_url,
)
from health import load_health, scan_cache
from queues import (
    BATCH_SIZE,
    GROUP_BY,
    QUEUE_ORDER,
    SEND_BATCH_COLUMNS,
    SEND_BATCH_HEADER,
    SEND_FIRST_COLUMNS,
    SEND_FIRST_HEADER,
    chunk_send_batches,
    load_priority_missions,
    send_first_rows,
    with_batch_ids,
)

FRAME_FIELDS = ["global_key", "status", "queue", "batch_id", "picked_by", "mission",
                "priority_mission", "predicted_species", "confidence", "census_stems",
                "iucn_category", "wcvp_regions", "crown_id", "label_from", "propagated_label"]
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
# How many batches the summary spells out. The first are the ones sent first.
SUMMARY_BATCHES = 3
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


def pack_priority_first(queue_rows: list, priority: set, mission: dict | None = None) -> list:
    """Every priority-mission frame in the first batches, then the 65/20/15 batches.

    Ground data makes these frames a double verification of the botanists, so all
    of them are wanted, whatever their queue: as a census of the transect, not the
    queue's pick of it. They split evenly into as few batches as fit `BATCH_SIZE`
    (203 frames: 68, 68, 67), with no control, since nothing in them was chosen.
    The rest are packed as before and numbered on from there.
    """
    key_at = SEND_FIRST_COLUMNS.index("global_key")
    first = [r for r in queue_rows if r[key_at] in priority]
    rest = [r for r in queue_rows if r[key_at] not in priority]
    cap = {"group_caps": spread_caps(mission) if mission else ()}
    if not first:
        return chunk_send_batches(rest, **cap)
    n = -(-len(first) // BATCH_SIZE)
    head = chunk_send_batches(first, batch_size=-(-len(first) // n), control_fraction=0,
                              share=0)
    offset = max(b[0] for b in head)
    return head + [[b[0] + offset, *b[1:]] for b in chunk_send_batches(rest, **cap)]


def build(pool: dict[str, str], predictions: dict, h, sent: set, priority_missions,
          census: dict | None = None, iucn: dict | None = None,
          wcvp_range: dict | None = None, labels: dict | None = None) -> dict:
    """Queue, batch and tracking rows for the frames that have an answer.

    ``h`` supplies support, top-1 accuracy and the canonicaliser, the same three
    things `measure.send_queue` hands `send_first_rows`. Frames without a cached
    answer are left out and returned by key, never dropped without a word.
    ``census`` (species -> stems), ``iucn`` (species -> category) and ``wcvp_range``
    (species -> regions) order each queue through `rarity_rank`; None reads the
    `input/` files. The low-confidence
    rule reads the top-1 minus top-2 margin (``by_margin``), a batch holds at most
    `MISSION_CAP` queue frames of one mission, `SITE_CAP` of one site and `SEASON_CAP`
    of one season, and one frame per crown is queued; the others take the label of
    the queued frame once it is in ``labels`` (key -> species).
    """
    census = read_species_column(CENSUS_CSV, "n") if census is None else census
    iucn = read_species_column(IUCN_CSV, "iucn_category") if iucn is None else iucn
    wcvp_range = (read_species_column(RANGE_CSV, "wcvp_regions") if wcvp_range is None
                  else wcvp_range)
    support = {d["species"]: d["n_labelled_frames"] for d in h.per_species}
    top1_of = {d["species"]: d["top1_accuracy"] for d in h.per_species}
    missing = [k for k in pool if k not in predictions]
    mission = {k: mission_of_url(u) for k, u in pool.items()}
    priority = {k for k, m in mission.items() if m in priority_missions}
    crown, same_crown = one_frame_per_crown(pool, mission)
    answered = {k: predictions[k] for k in pool if k in predictions and k not in same_crown}
    species = {k: h.canon(r[0][0]) for k, r in answered.items() if r}
    # The rarity rank rides in the novelty slot: same in-queue ordering, no vectors.
    decided, n_no_answer, _ = send_first_rows(
        answered, set(), h.canon, support, top1_of, sent=sent, priority=priority,
        novelty=rarity_rank(species, census, iucn, wcvp_range), by_margin=True)
    queue_rows = [[q, key, "", pred, f"{conf:.6f}", support.get(pred, 0),
                   fmt(top1_of.get(pred)) if pred in top1_of else "", "", ""]
                  for q, key, pred, conf, _ in decided]
    batch_rows = pack_priority_first(queue_rows, priority, mission)
    rarity = {k: [census.get(sp.lower(), ""), iucn.get(sp.lower(), ""),
                  wcvp_range.get(sp.lower(), "")]
              for k, sp in species.items()}
    return {"queue_rows": with_batch_ids(queue_rows, batch_rows), "batch_rows": batch_rows,
            "missing": missing, "n_no_answer": n_no_answer, "mission": mission,
            "priority": priority, "already_sent": [k for k in pool if k in sent],
            "rarity": rarity, "crown": crown, "same_crown": same_crown,
            "propagated": propagate_crown_labels(same_crown, labels or {})}


def write_files(out: Path, built: dict, pool: dict[str, str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    mission, forms = built["mission"], growth_form.load()
    q = {r[SEND_FIRST_COLUMNS.index("global_key")]: r for r in built["queue_rows"]}
    species_at = SEND_FIRST_COLUMNS.index("predicted_species")
    with open(out / "send_first_queue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SEND_FIRST_HEADER + RARITY_COLUMNS)
        for r in built["queue_rows"]:
            w.writerow(r + ["", mission[r[1]], site_of(mission[r[1]])] + built["rarity"][r[1]])
    key_at = SEND_BATCH_COLUMNS.index("global_key")
    with open(out / "send_batches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SEND_BATCH_HEADER)
        for b in built["batch_rows"]:
            m = mission[b[key_at]]
            # s3_uri and labelbox_url stay blank: the first needs a bucket row per
            # mission, the second is a link for a frame that has a data row id.
            w.writerow(b + ["", "", "", "", m, site_of(m),
                            forms.get(q[b[key_at]][species_at], growth_form.UNKNOWN), GROUP_BY])
    why = ({k: "no_prediction" for k in built["missing"]}
           | {k: "already_sent" for k in built["already_sent"]}
           | {k: "same_crown" for k in built["same_crown"]})
    placed = {b[key_at]: b for b in built["batch_rows"]}
    with open(out / "frames.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FRAME_FIELDS)
        for k in pool:
            b, row = placed.get(k), q.get(k)
            status = "batched" if b else why.get(k, "no_answer")
            w.writerow([k, status, b[3] if b else "", b[0] if b else "", b[4] if b else "",
                        mission[k], k in built["priority"],
                        row[species_at] if row else "", row[4] if row else ""]
                       + built["rarity"].get(k, ["", "", ""])
                       + [built["crown"][k], built["same_crown"].get(k, ""),
                          built["propagated"].get(k, "")])
    # Same columns as gt_dominant_taxon.csv plus the frame the label came from,
    # so the propagated labels merge into the ground truth like any other.
    with open(out / "propagated_labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "wcvp_canonical_name", "label_from"])
        for k, name in built["propagated"].items():
            w.writerow([k, name, built["same_crown"][k]])


def summary(pool: dict, built: dict) -> str:
    """Pool size, what was left out, per-queue counts, the first batches' mix."""
    key_at = SEND_BATCH_COLUMNS.index("global_key")
    queue_at = SEND_BATCH_COLUMNS.index("queue")
    pick_at = SEND_BATCH_COLUMNS.index("picked_by")
    batches: dict = {}
    for b in built["batch_rows"]:
        batches.setdefault(b[0], []).append(b)
    queues = Counter(r[0] for r in built["queue_rows"])
    lines = [f"pool: {len(pool)} frames",
             (f"predicted: {len(built['queue_rows']) + built['n_no_answer']} "
              f"(queued {len(built['queue_rows'])}, answer with no species {built['n_no_answer']})"),
             f"left out, no cached prediction: {len(built['missing'])}"
             + (f" (first 5: {built['missing'][:5]})" if built["missing"] else ""),
             f"left out, already in a round ledger: {len(built['already_sent'])}",
             (f"left out, another frame of the same crown is queued: {len(built['same_crown'])}"
              f" (labelled through it: {len(built['propagated'])})"),
             "queue sizes: " + ", ".join(f"{q} {queues[q]}" for q in QUEUE_ORDER),
             f"batches: {len(batches)} of up to {BATCH_SIZE}"]
    for bid in sorted(batches)[:SUMMARY_BATCHES]:
        rows = batches[bid]
        by_q = Counter(r[queue_at] for r in rows if r[pick_at] == "queue")
        rarity = [built["rarity"][r[key_at]] for r in rows]
        lines.append(
            f"  batch {bid}: {len(rows)} frames, "
            + ", ".join(f"{q} {by_q[q]}" for q in QUEUE_ORDER if by_q[q])
            + f", control {sum(r[pick_at] == 'control' for r in rows)}, "
            f"priority mission {sum(r[key_at] in built['priority'] for r in rows)} "
            f"(of the control {sum(r[key_at] in built['priority'] for r in rows if r[pick_at] == 'control')}), "
            f"IUCN-listed {sum(bool(c) for _, c, _ in rarity)}, "
            f"census stems <= 10: {sum(bool(n) and int(n) <= 10 for n, _, _ in rarity)}, "
            f"not in census {sum(not n for n, _, _ in rarity)}, "
            f"WCVP regions <= 5: {sum(bool(r) and int(r) <= 5 for _, _, r in rarity)}")
    return "\n".join(lines)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", type=Path, required=True,
                    help="global_key,image_url of every frame in the catalog pool")
    ap.add_argument("--cache", type=Path, required=True,
                    help="folder of cached Pl@ntNet answers for the pool, one file per frame")
    ap.add_argument("--out", type=Path, required=True, help="folder to write the files to")
    ap.add_argument("--priority-missions", type=Path, default=None,
                    help="missions to sort first (default: input/priority_missions.txt)")
    add_input_flags(ap)
    add_label_source_flag(ap)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    pool = read_pool(args.pool)
    h = load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                    wcvp_cache=args.wcvp_cache, label_source=args.label_source)
    priority_missions = (load_priority_missions(str(args.priority_missions))
                         if args.priority_missions else load_priority_missions())
    with open(args.gt, encoding="utf-8") as f:
        labels = {r["global_key"]: r["wcvp_canonical_name"] for r in csv.DictReader(f)}
    built = build(pool, scan_cache(str(args.cache)).predictions, h,
                  ledger_keys(LEDGER_DIR), priority_missions, labels=labels)
    write_files(args.out, built, pool)
    print(summary(pool, built))
    print(f"wrote send_batches.csv, send_first_queue.csv, frames.csv, propagated_labels.csv"
          f" to {args.out}")


if __name__ == "__main__":
    main()
