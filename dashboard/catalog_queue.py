"""The queue page's figures when the build tables hold the catalog batches.

``labelling/catalog_batches.py`` writes send_batches.csv, send_first_queue.csv
and frames.csv into the tables the page verifies against. frames.csv is the
signal, since measure.py never writes it. With it, the page reads its queue off
those files instead of recomputing the main pool's, and checks send_batches.csv
against the packing catalog_batches.py runs, by calling it. Without it nothing
here applies and the page is the main pool's.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

import core as hc
import queues
from history import fail

FRAMES_FILE = "frames.csv"
LABELLING = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "labelling")
# send_first_queue.csv columns catalog_batches.py fills only under --rarity.
RARITY_COLUMNS = ("census_stems", "iucn_category", "wcvp_regions")


def _read(verify_dir, name):
    return hc.read_csv_rows(os.path.join(verify_dir, name))


def load(verify_dir) -> dict | None:
    """The queue figures the page reads, off the catalog files, or None when the
    tables hold no frames.csv. The keys the main pool's figures share are
    overridden; ``catalog`` carries what only this page words."""
    if not verify_dir or not os.path.exists(os.path.join(verify_dir, FRAMES_FILE)):
        return None
    frames = _read(verify_dir, FRAMES_FILE)
    qrows = _read(verify_dir, "send_first_queue.csv")
    brows = _read(verify_dir, "send_batches.csv")
    priority = {r["global_key"] for r in frames if r["priority_mission"] == "True"}
    batches = defaultdict(list)
    for r in brows:
        batches[int(r["batch_id"])].append(r)
    counts = Counter(r["queue"] for r in qrows)
    status = Counter(r["status"] for r in frames)
    return {
        "queue_counts": counts, "n_unlab": len(qrows),
        "n_batches": max(batches, default=0),
        "n_batch1": len(batches[min(batches)]) if batches else 0,
        "n_no_answer": status["no_answer"],
        # Nothing of the main pool's ordering applies: no split is held out of
        # this pool, no photo is ranked by look, no thumbnail is fetched.
        "queue_held_out": {}, "thumbs": {}, "selection_audit": None,
        "selection_confound": None,
        "catalog": {
            "n_pool": len(frames), "status": status, "batches": dict(sorted(batches.items())),
            "queue_of": {r["global_key"]: r for r in qrows},
            # Priority-mission frames per batch, where it holds any.
            "priority_batches": {b: n for b, rows in sorted(batches.items())
                                 if (n := sum(r["global_key"] in priority for r in rows))},
            # The growth group of each batch: one per batch, the first row's.
            "growth_group": {b: rows[0].get("growth_group") or "tree"
                             for b, rows in batches.items()},
            "rarity": any(r.get(c) for r in qrows for c in RARITY_COLUMNS),
            "n_s3": sum(1 for r in brows if r["s3_uri"])}}


def packer():
    """``labelling/catalog_batches.py``: the packing and caps the files were
    written with, called rather than copied. Stdlib, like this directory."""
    if LABELLING not in sys.path:
        sys.path.append(LABELLING)
    import catalog_batches
    return catalog_batches


def check(verify_dir) -> str:
    """send_batches.csv is the packing catalog_batches.py makes from
    send_first_queue.csv and frames.csv, with the pins and sent rounds in
    packing_inputs.json, row for row, or the build stops."""
    frames = _read(verify_dir, FRAMES_FILE)
    qrows = _read(verify_dir, "send_first_queue.csv")
    brows = _read(verify_dir, "send_batches.csv")
    priority = {r["global_key"] for r in frames if r["priority_mission"] == "True"}
    mission = {r["global_key"]: r["mission"] for r in frames}
    cb = packer()
    path = os.path.join(verify_dir, cb.PACKING_INPUTS)
    used = {"pins": [], "sent": [], "sent_nums": []}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            used = json.load(f)
    threshold = used.get("liana_share", cb.LIANA_SHARE)
    group = {r["global_key"]: cb.growth_group(float(r["liana_share"]), threshold)
             for r in frames if r.get("liana_share")}
    want, _ = cb.pack_pinned(
        [[r[c] for c in queues.SEND_FIRST_COLUMNS] for r in qrows],
        [tuple(p) for p in used["pins"]], set(used["sent"]), set(used["sent_nums"]),
        priority, mission, group)
    got = [[r[c] for c in queues.SEND_BATCH_COLUMNS] for r in brows]
    if [[str(v) for v in row] for row in want] != got:
        fail("send_batches.csv is not the packing labelling/catalog_batches.py makes from "
             "send_first_queue.csv and frames.csv beside it. Re-run catalog_batches.py.")
    n_batched = sum(1 for r in frames if r["status"] == "batched")
    if n_batched != len(brows):
        fail(f"frames.csv marks {n_batched} frames batched, send_batches.csv has {len(brows)}")
    return (f"send_batches.csv: {len(brows):,} catalog rows in "
            f"{len({r['batch_id'] for r in brows})} batches, the packing "
            f"catalog_batches.py makes from send_first_queue.csv and frames.csv")


def batch_rule(cat) -> str:
    """How the catalog batches are made up, in a few sentences."""
    groups = cat["growth_group"]
    piles = []
    for g in packer().GROWTH_GROUPS:
        ids = [b for b in sorted(groups) if groups[b] == g]
        if ids:
            n = sum(len(cat["batches"][b]) for b in ids)
            piles.append(f"{g} batches {ids[0]} to {ids[-1]} ({n:,} photos)" if len(ids) > 1
                         else f"{g} batch {ids[0]} ({n:,} photos)")
    head = ("Trees and lianas go in separate batches: " + ", then ".join(piles) + ". A photo "
            f"is liana when lianas hold at least {packer().LIANA_SHARE:.0%} of the score of "
            "its top 5 Pl@ntNet answers, a model guess, not a label; every other photo, "
            "shrubs and unknowns too, is tree. ") if piles else ""
    prio = cat["priority_batches"]
    if prio:
        head += (f"The {sum(prio.values()):,} queued frames of the priority missions, the "
                 f"ones with ground data on their crowns, come first in their growth form "
                 f"(batch{'es' if len(prio) > 1 else ''} "
                 f"{', '.join(map(str, prio))}). ")
    per = queues.control_size()
    control = (f"{per} random control photos, drawn once from its growth form up front "
               f"(the last batch carries what is left of that draw), " if per else "")
    return (head + f"Each batch of at most {queues.BATCH_SIZE} carries "
            f"{control}up to {queues.QUEUE2_SHARE} photos from the low-confidence queue, "
            f"one per confidence band in turn, and fills the rest in queue order.")
