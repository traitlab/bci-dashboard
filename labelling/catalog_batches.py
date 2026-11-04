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
vectors, so inside each queue they run in confidence order instead of novelty
order. With `--rarity` (off by default: lefolab wants no rarity order before a
model trained on BCI labels) the order is ecological rarity (`rarity_rank`): IUCN threatened species first, then by stems in
the BCI 50-ha census (`input/bci_census.csv`, fewest first), then the species
the census does not list by WCVP range size (`input/species_range.csv`, fewest
botanical regions first, the endemism proxy), confidence breaking ties. Label scarcity decides the
queue, rarity decides the order inside it. And every frame of a mission listed
in `input/priority_missions.txt` (ground data on its crowns) goes out first,
whatever its queue or group: the transect is a census (Antoine, 2026-10).

Of the rest, only predicted trees go out (Antoine's decision), and no `can_wait`
frame: both stay in the queue file with a blank batch_id. A frame is liana when species
WCVP calls liana hold at least `LIANA_SHARE` of the score of its top-5 Pl@ntNet
answers (`liana_share`); every other frame, shrubs and unknowns included, is
tree: two piles, not a taxonomy. The group is a model guess, not a label. The
rows of a batch are written in a seeded random order, so the botanist cannot
read the prediction off the species grouping. A pinned batch keeps its frames
whatever their group or queue, so a change to who goes out empties
`input/pinned_batches.csv` in the same PR while none of those batches is sent;
the next refresh pins them again and numbers continue past the highest sent.

Writes to --out:
  send_batches.csv      what `dispatch_round.py --batch N` sends. data_row_id is
                        blank: no local inventory has these rows, and the
                        dispatcher looks the ids up in the dataset by global key.
                        handed_out is True for a pinned batch.
  send_first_queue.csv  the same frames in queue order, beside it because
                        `dispatch_round.py` reads the species, confidence and
                        support for the round ledger from there. no_batch_reason
                        says why a frame has no batch (pushed_down, predicted_liana).
  frames.csv            every pool frame: its queue and batch, or why it has none.

Batches already handed out stay put. `input/pinned_batches.csv` holds exactly the
batches handed to the collaborator: those frames keep their batch and number across
rebuilds, whatever the labels do, and only a frame since recorded as sent, or gone
from the pool, drops out. A sent batch leaves the file and an absent file pins
nothing. Each build tops the pins up to `--keep-ahead` unsent batches (default
4), so a send is followed by the next batch with no one asking; the held batches
never change. `--hand-out K` pins K more on top (the lowest numbers neither pinned
nor sent). The rest of the pool is
packed after the pinned batches, priority missions first, numbered past the highest
pinned or sent number, so a number is never reused. The pin file is rewritten from
the output.

    python labelling/catalog_batches.py --pool data/predictions_catalog_2026/input.csv \\
        --cache data/predictions_catalog_2026/cache --out build/catalog_batches
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import growth_form
from catalog_frames import (
    CENSUS_CSV,
    CROWN_SUFFIX,
    IUCN_CSV,
    IUCN_ORDER,
    LIANA_SHARE,
    MISSION_CAP,
    PINS_CSV,
    RANGE_CSV,
    RARITY_COLUMNS,
    SEASON_CAP,
    SITE_CAP,
    crown_of,
    growth_group,
    liana_share,
    one_frame_per_crown,
    propagate_crown_labels,
    rarity_rank,
    read_pins,
    read_pool,
    read_species_column,
    season_of,
    shuffle_within,
    site_of,
    spread_caps,
    write_pins,
)
from core import (
    LEDGER_DIR,
    add_input_flags,
    add_label_source_flag,
    fmt,
    ledger_keys,
    mission_of_url,
    sent_rounds,
)
from health import load_health, scan_cache
from mission_buckets import s3_uri
from queues import (
    BATCH_SIZE,
    CONTROL_GROUP,
    CONTROL_SEED,
    GROUP_BY,
    PREDICTED_LIANA,
    PUSHED_DOWN,
    QUEUE_ORDER,
    SEND_BATCH_COLUMNS,
    SEND_BATCH_HEADER,
    SEND_FIRST_COLUMNS,
    SEND_FIRST_HEADER,
    WAIT_QUEUE,
    chunk_send_batches,
    control_size,
    load_priority_missions,
    send_first_rows,
    with_batch_ids,
)

# Names that moved to catalog_frames and stay readable here, for callers and tests.
__all__ = [
    "CENSUS_CSV",
    "CROWN_SUFFIX",
    "IUCN_CSV",
    "IUCN_ORDER",
    "MISSION_CAP",
    "PINS_CSV",
    "RANGE_CSV",
    "SEASON_CAP",
    "SITE_CAP",
    "crown_of",
    "growth_group",
    "liana_share",
    "rarity_rank",
    "read_pins",
    "read_pool",
    "read_species_column",
    "season_of",
    "spread_caps",
]

FRAME_FIELDS = ["global_key", "status", "queue", "batch_id", "picked_by", "mission",
                "priority_mission", "predicted_species", "confidence", "census_stems",
                "iucn_category", "wcvp_regions", "crown_id", "label_from", "propagated_label",
                "liana_share"]
KEEP_AHEAD = 4  # unsent batches the collaborator holds; 4 is what was handed out first
PACKING_INPUTS = "packing_inputs.json"
GROWTH_GROUPS = ("tree", "liana")  # packed in this order, numbers continuous
SENT_GROUPS = ("tree",)  # Antoine's decision: the botanists get predicted trees only
# How many batches the summary spells out. The first are the ones sent first.
SUMMARY_BATCHES = 3


def pack_groups(queue_rows: list, priority: set, mission: dict | None = None,
                group: dict | None = None) -> list:
    """Tree batches only, Antoine's decision (``group``: key -> group, absent is
    tree), packed by `pack_with_reserved_control` with its priority-mission frames
    at the head. Liana rows and `can_wait` rows stay in the queue file but never
    in a batch (a pinned one is kept by `pack_pinned`).

    Ground data makes the priority frames a double verification of the botanists,
    so all of them are wanted, whatever their queue: as a census of the transect,
    not the queue's pick of it. They fill the first batches of their group, the
    queue tops the last of them up to `BATCH_SIZE`, and every batch carries the
    group's control.
    """
    key_at = SEND_FIRST_COLUMNS.index("global_key")
    queue_at, conf_at = (SEND_FIRST_COLUMNS.index(c) for c in ("queue", "confidence"))
    # Soft species cap: a pile of few species still fills every batch but its last.
    cap = {"group_caps": spread_caps(mission) if mission else (), "soft_species_cap": True}
    group = group or {}
    out: list = []
    for g in SENT_GROUPS:
        rows = [r for r in queue_rows if r[key_at] not in priority
                and group.get(r[key_at], "tree") == g and r[queue_at] != WAIT_QUEUE]
        # Every priority frame, whatever its queue or group: the transect is a
        # census, so a can_wait or liana guess still gets its second identification.
        # The queue's order, without rarity: a reorder of the queue never moves a
        # priority frame between the first batches.
        first = sorted((r for r in queue_rows if r[key_at] in priority),
                       key=lambda r: (QUEUE_ORDER.index(r[queue_at]), float(r[conf_at]),
                                      r[key_at])) if g == SENT_GROUPS[0] else []
        packed = pack_with_reserved_control(rows, first=first, **cap)
        offset = max((b[0] for b in out), default=0)
        out += [[b[0] + offset, *b[1:]] for b in packed]
    return out


def pack_with_reserved_control(rows: list, seed: int = CONTROL_SEED, first: list = (),
                               **cap) -> list:
    """The 65/20/15 batches with the control drawn once from the whole pool,
    after the ``first`` rows (uncapped, in their order, no control drawn from them).

    The main queue draws each batch's control from what its queue picks leave,
    so a reorder of the queue (a rarity table, the margin rule) moves the control
    too. Here the control is a seeded draw from the pool in key order, reserved
    before packing: only the pool and the seed decide it. The queue packs the
    rest into batches of `BATCH_SIZE` minus the control, and each batch takes the
    next `control_size()` of the draw; the last batch takes what is left. The draw
    is the control's share of the pool, so a small pool keeps queue work.
    """
    key_at, queue_at = (SEND_FIRST_COLUMNS.index(c) for c in ("global_key", "queue"))
    per = control_size()
    room = BATCH_SIZE - per
    by_key = sorted(rows, key=lambda r: r[key_at])
    # The control's share of the pool, first rows included: they take it too.
    n_control = min(len(by_key), round((len(rows) + len(first)) * per / BATCH_SIZE))
    control = random.Random(seed).sample(by_key, n_control) if per else []
    drawn = {r[key_at] for r in control}
    left = [r for r in rows if r[key_at] not in drawn]
    queued = (chunk_send_batches(list(first), batch_size=room, control_fraction=0, share=0)
              if first else [])
    n_head = max((b[0] for b in queued), default=0)
    gap = room - sum(b[0] == n_head for b in queued) if queued else 0
    if gap and left:
        # The queue tops the last first-rows batch up: its own first batch, cut to the gap.
        top = [b for b in chunk_send_batches(left, batch_size=gap, control_fraction=0, **cap)
               if b[0] == 1]
        queued += [[n_head, *b[1:]] for b in top]
        took = {b[2] for b in top}
        left = [r for r in left if r[key_at] not in took]
    queued += [[b[0] + n_head, *b[1:]] for b in
               chunk_send_batches(left, batch_size=room, control_fraction=0, **cap)]
    n = max((b[0] for b in queued), default=1 if control else 0)
    for b in range(1, n + 1):
        chunk = control[(b - 1) * per:b * per] if b < n else control[(b - 1) * per:]
        queued.extend([b, CONTROL_GROUP, r[key_at], r[queue_at], "control"]
                      for r in sorted(chunk, key=lambda r: r[key_at]))
    return queued


def pack_pinned(queue_rows: list, pins: list, sent: set, sent_nums: set, priority: set,
                mission: dict, group: dict | None = None) -> tuple[list, dict]:
    """(batch rows, dropped counts): pinned frames where they were, the rest after.

    A pinned frame is dropped only when it has been recorded as sent, its batch
    number has been sent (the rest of that batch returns to the pool), or it is no
    longer queued. The rest of the pool is packed by `pack_groups` and numbered past
    the highest pinned or sent number, so no number is reused or restarted at 1.
    """
    key_at, pred_at, queue_at = (SEND_FIRST_COLUMNS.index(c)
                                 for c in ("global_key", "predicted_species", "queue"))
    by_key = {r[key_at]: r for r in queue_rows}
    kept, dropped = {}, Counter()
    for b, key, picked in pins:
        if key in kept:
            continue
        if key in sent:
            dropped["recorded as sent"] += 1
        elif b in sent_nums:
            dropped["its batch number was sent"] += 1
        elif key not in by_key:
            dropped["no longer in the pool or queued"] += 1
        else:
            kept[key] = (b, picked)
    head = [[b, CONTROL_GROUP if picked == "control" else by_key[k][pred_at], k,
             by_key[k][queue_at], picked] for k, (b, picked) in kept.items()]
    head.sort(key=lambda r: (r[0], r[2]))
    offset = max(sent_nums | {b for b, _, _ in pins}, default=0)
    rest = pack_groups([r for r in queue_rows if r[key_at] not in kept], priority, mission,
                       group)
    return head + [[b[0] + offset, *b[1:]] for b in rest], dict(dropped)


def build(pool: dict[str, str], predictions: dict, h, sent: set, priority_missions,
          census: dict | None = None, iucn: dict | None = None,
          wcvp_range: dict | None = None, labels: dict | None = None,
          pins: list | None = None, sent_nums: set | None = None,
          forms: dict | None = None) -> dict:
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
    the queued frame once it is in ``labels`` (key -> species). ``pins`` (`read_pins`)
    keep their batch and ``sent_nums`` (the round numbers sent) are never reused;
    see `pack_pinned`. ``forms`` (species -> WCVP growth form, None reads
    input/growth_form.csv) splits trees from lianas through `liana_share`.
    """
    forms = growth_form.load() if forms is None else forms
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
    # Rounded as frames.csv writes it, so the page check replays the same split.
    share = {k: round(liana_share(r, lambda sp: forms.get(h.canon(sp))), 6)
             for k, r in answered.items()}
    group = {k: growth_group(s) for k, s in share.items()}
    # The rarity rank rides in the novelty slot: same in-queue ordering, no vectors.
    decided, n_no_answer, _ = send_first_rows(
        answered, set(), h.canon, support, top1_of, sent=sent, priority=priority,
        novelty=rarity_rank(species, census, iucn, wcvp_range), by_margin=True)
    queue_rows = [[q, key, "", pred, f"{conf:.6f}", support.get(pred, 0),
                   fmt(top1_of.get(pred)) if pred in top1_of else "", "", ""]
                  for q, key, pred, conf, _ in decided]
    batch_rows, pins_dropped = pack_pinned(queue_rows, pins or [], sent, sent_nums or set(),
                                           priority, mission, group)
    batch_rows = shuffle_within(batch_rows)
    rarity = {k: [census.get(sp.lower(), ""), iucn.get(sp.lower(), ""),
                  wcvp_range.get(sp.lower(), "")]
              for k, sp in species.items()}
    batched = {b[2] for b in batch_rows}
    stray = [r[1] for r in queue_rows if r[1] not in batched and r[0] != WAIT_QUEUE
             and group.get(r[1], "tree") in SENT_GROUPS]
    if stray:  # only liana and can_wait rows may stay out of a batch
        raise ValueError(f"{len(stray)} sendable frames were never packed, first {stray[0]}")
    return {"queue_rows": with_batch_ids(queue_rows, batch_rows, allow_unbatched=True),
            "batch_rows": batch_rows,
            "missing": missing, "n_no_answer": n_no_answer, "mission": mission,
            "priority": priority, "already_sent": [k for k in pool if k in sent],
            "pins_dropped": pins_dropped, "n_pins": len(pins or []),
            "packing_inputs": {"pins": pins or [], "sent_nums": sorted(sent_nums or ()),
                               "sent": sorted(k for _, k, _ in pins or [] if k in sent),
                               "liana_share": LIANA_SHARE},
            "liana_share": share, "group": group,
            "rarity": rarity, "crown": crown, "same_crown": same_crown,
            "propagated": propagate_crown_labels(same_crown, labels or {})}


def write_files(out: Path, built: dict, pool: dict[str, str], pinned=frozenset()) -> None:
    """``pinned``: the batch numbers handed out, marked in send_batches.csv."""
    out.mkdir(parents=True, exist_ok=True)
    mission, forms = built["mission"], growth_form.load()
    q = {r[SEND_FIRST_COLUMNS.index("global_key")]: r for r in built["queue_rows"]}
    species_at = SEND_FIRST_COLUMNS.index("predicted_species")
    with open(out / "send_first_queue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SEND_FIRST_HEADER + RARITY_COLUMNS + ["no_batch_reason"])
        batch_at = SEND_FIRST_COLUMNS.index("batch_id")
        for r in built["queue_rows"]:
            # Only `can_wait` and liana rows stay out (`build` raises on any other).
            why = "" if r[batch_at] != "" else PUSHED_DOWN if r[0] == WAIT_QUEUE else PREDICTED_LIANA
            w.writerow(r + ["", mission[r[1]], site_of(mission[r[1]])] + built["rarity"][r[1]] + [why])
    key_at = SEND_BATCH_COLUMNS.index("global_key")
    with open(out / "send_batches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SEND_BATCH_HEADER + ["growth_group", "handed_out"])
        for b in built["batch_rows"]:
            m = mission[b[key_at]]
            # labelbox_url stays blank: it is a link for a frame that has a data row id.
            w.writerow(b + ["", s3_uri(pool[b[key_at]]), "", "", m, site_of(m),
                            forms.get(q[b[key_at]][species_at], growth_form.UNKNOWN), GROUP_BY,
                            built["group"].get(b[key_at], "tree"), b[0] in pinned])
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
                          built["propagated"].get(k, ""), built["liana_share"].get(k, "")])
    # What pack_pinned read besides the queue, so the page check can replay it.
    with open(out / PACKING_INPUTS, "w", encoding="utf-8") as f:
        json.dump(built["packing_inputs"], f)
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
             f"pinned frames read: {built['n_pins']}, dropped: "
             + (", ".join(f"{n} {why}" for why, n in built["pins_dropped"].items()) or "none"),
             (f"left out, another frame of the same crown is queued: {len(built['same_crown'])}"
              f" (labelled through it: {len(built['propagated'])})"),
             "queue sizes: " + ", ".join(f"{q} {queues[q]}" for q in QUEUE_ORDER),
             f"batches: {len(batches)} of up to {BATCH_SIZE}"]
    group_of = {bid: built["group"].get(rows[0][key_at], "tree") for bid, rows in batches.items()}
    for g in GROWTH_GROUPS:
        ids = [bid for bid in sorted(batches) if group_of[bid] == g]
        lines.append(f"  {g}: {sum(len(batches[b]) for b in ids)} frames in {len(ids)} batches"
                     + (f" ({ids[0]} to {ids[-1]})" if ids else ""))
    for bid in sorted(batches)[:SUMMARY_BATCHES]:
        rows = batches[bid]
        by_q = Counter(r[queue_at] for r in rows if r[pick_at] == "queue")
        rarity = [built["rarity"][r[key_at]] for r in rows]
        lines.append(
            f"  batch {bid} ({group_of[bid]}): {len(rows)} frames, "
            + ", ".join(f"{q} {by_q[q]}" for q in QUEUE_ORDER if by_q[q])
            + f", control {sum(r[pick_at] == 'control' for r in rows)}, "
            f"priority mission {sum(r[key_at] in built['priority'] for r in rows)} "
            f"(of the control {sum(r[key_at] in built['priority'] for r in rows if r[pick_at] == 'control')})"
            + (f", IUCN-listed {sum(bool(c) for _, c, _ in rarity)}, "
               f"census stems <= 10: {sum(bool(n) and int(n) <= 10 for n, _, _ in rarity)}, "
               f"not in census {sum(not n for n, _, _ in rarity)}, "
               f"WCVP regions <= 5: {sum(bool(r) and int(r) <= 5 for _, _, r in rarity)}"
               if any(any(v) for v in built["rarity"].values()) else ""))
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
    ap.add_argument("--pins", type=Path, default=PINS_CSV,
                    help="batches kept as handed out, read first and rewritten from the "
                         "output (default: input/pinned_batches.csv)")
    ap.add_argument("--keep-ahead", type=int, default=KEEP_AHEAD, metavar="N",
                    help="top the pins up to N unsent batches, the ones the collaborator "
                         f"holds (default: {KEEP_AHEAD})")
    ap.add_argument("--hand-out", type=int, default=0, metavar="K",
                    help="pin K more batches on top of --keep-ahead (default: 0)")
    ap.add_argument("--rarity", action="store_true",
                    help="order inside each queue by IUCN, census and WCVP range (off: "
                         "lefolab wants no rarity order before a model trained on BCI labels)")
    add_input_flags(ap)
    add_label_source_flag(ap)
    args = ap.parse_args()
    if args.hand_out < 0 or args.keep_ahead < 0:
        ap.error("--hand-out and --keep-ahead must be 0 or more")
    return args


def main() -> None:
    args = parse_args()
    pool = read_pool(args.pool)
    h = load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                    wcvp_cache=args.wcvp_cache, label_source=args.label_source)
    priority_missions = (load_priority_missions(str(args.priority_missions))
                         if args.priority_missions else load_priority_missions())
    with open(args.gt, encoding="utf-8") as f:
        labels = {r["global_key"]: r["wcvp_canonical_name"] for r in csv.DictReader(f)}
    off = {} if not args.rarity else None  # None reads the input/ tables
    sent_nums = sent_rounds(LEDGER_DIR)
    pins = read_pins(args.pins)
    built = build(pool, scan_cache(str(args.cache)).predictions, h,
                  ledger_keys(LEDGER_DIR), priority_missions, census=off, iucn=off,
                  wcvp_range=off, labels=labels, pins=pins, sent_nums=sent_nums)
    pinned = write_pins(args.pins, built["batch_rows"], pins, sent_nums, args.hand_out,
                        args.keep_ahead)
    write_files(args.out, built, pool, set(pinned))
    print(summary(pool, built))
    print(f"pinned batches {', '.join(map(str, pinned)) or 'none'} in {args.pins}")
    print(f"wrote send_batches.csv, send_first_queue.csv, frames.csv, propagated_labels.csv"
          f" to {args.out}")


if __name__ == "__main__":
    main()
