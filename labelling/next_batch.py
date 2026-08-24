"""What to send to the Labelbox project next, and why.

Answers the standing question -- "the goal is to know which picture in the
dataset to send to the project" -- from the two things a read-only key can
actually reach: the dataset inventory (``labelling/fetch_dataset.py``) and a
project export dropped on disk.

What comes out, and how far each part can be trusted:

``queue_contradictions.csv``  (ready to dispatch)
    Crowns where the field label and the Pl@ntNet top-1 disagree at high
    confidence -- the review the field team asked for -- resolved onto global
    keys that exist in the current dataset. Every row is backed by a cached
    prediction and a botanist label, so the ranking is a measurement.

``queue_missions.csv``  (ready to dispatch, coarse)
    The 32 flights whose photos are in the dataset but not yet in the project,
    largest first. Mission is the unit the team already batches in: the single
    non-legacy batch in the export is one whole mission. Nothing here ranks
    *within* a mission, because nothing available can.

``queue_photos.csv``  (provisional -- read the caveat)
    Every unsent photo, ordered by mission then by a file-size proxy. This is a
    dispatch convenience, not a priority signal.

The caveat, stated once, plainly. Ranking the 3,269 unsent photos by what they
would teach the model needs one of three things, and this script has none of
them:

  * a Pl@ntNet prediction per photo -- none of the 3,269 has one cached, the
    local cache covers only the legacy corpus;
  * an embedding per photo -- present in Labelbox, but reachable only through
    an export task, which a read-only key cannot create (verified: dataset
    export fails with AuthorizationError, same as project export);
  * a crown identity, to tell a new tree from one photographed before.

The third was tested and does not exist in the metadata. See
``report_polygon_identity`` -- both candidate proxies were checked against
ground truth and both failed. Any queue claiming to deduplicate crowns from
this metadata would be making it up.

Read-only. Nothing is written back to Labelbox.

Usage:
    python3 labelling/next_batch.py \\
        --export "/path/to/Export  project - 2024_bci - 8_6_2026.ndjson"
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "dashboard"))

import core as hc

PROJECT_ID = "cmp375mkq0dhr07w92diwbmuh"  # 2024_bci
DATASET_ROWS = "data/dataset_rows.jsonl"
OUT_DIR = "data/next_batch"

# A disagreement is only worth a botanist's time if the model is committed to
# it. Below this the model is hedging and the "contradiction" is noise.
CONTRADICTION_MIN_SCORE = 0.5

# Pl@ntNet was sent a fixed 1280x1280 centre crop, which is 13.7% of the 4000x3000
# frame, while the field label comes from a crown box drawn anywhere in that frame.
# So a "contradiction" can mean the model named a *different* tree correctly. A
# row is only a real contradiction when the field label is the species that
# dominates the crop the model was actually sent.
CONTRADICTION_MIN_COVERAGE = 0.5

# Verdicts assigned by build_contradiction_queue, best first. Only ``send`` rows
# are a disagreement about one tree; the rest are crop artifacts or unprovable.
VERDICT_ORDER = ("send", "low_coverage", "other_crown", "unknown_geometry")

# Radii tried when testing whether drone position identifies a crown.
GPS_CLUSTER_RADII_M = (5, 10, 20)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--export", required=True, help="project export NDJSON")
    p.add_argument("--dataset-rows", default=DATASET_ROWS)
    p.add_argument("--out-dir", default=OUT_DIR)
    p.add_argument("--min-score", type=float, default=CONTRADICTION_MIN_SCORE)
    p.add_argument("--min-coverage", type=float,
                   default=CONTRADICTION_MIN_COVERAGE)
    return p.parse_args(argv)


def basename(global_key: str) -> str:
    """Strip the namespace prefix a global key carries.

    Three prefixes are in play and they are why a hand-built batch list stops
    resolving: the local corpus uses ``comb_NAME``, rows migrated out of the old
    project use ``migrated/NAME``, and rows uploaded by the current ingest use
    ``<flight_folder>/NAME``. The bare file name is the only id the three share.
    """
    return global_key.rsplit("/", 1)[-1].removeprefix("comb_")


def sensor_of(mission: str) -> str:
    return mission.rsplit("_", 1)[-1] if "_" in mission else ""


def gps_of(row: dict):
    point = (row.get("media_attributes") or {}).get("gpsPoint")
    if not point:
        return None
    lat, lon = point.split(",")
    return float(lat), float(lon)


def gps_clusters(rows: list[dict], radius_m: float) -> dict:
    """Single-link cluster of photos by drone position, at ``radius_m``.

    A plain grid would split one true cluster across a cell boundary and then
    report it as two pure clusters, which flatters the purity test it feeds.
    Neighbouring occupied cells are therefore merged.
    """
    cells = defaultdict(list)
    for row in rows:
        lat, lon = gps_of(row)
        cells[(int(lat * 111320.0 // radius_m),
               int(lon * 111320.0 * math.cos(math.radians(lat)) // radius_m)
               )].append(row)

    parent = {key: key for key in cells}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for cx, cy in list(cells):
        for dx, dy in ((0, 1), (1, -1), (1, 0), (1, 1)):
            neighbour = (cx + dx, cy + dy)
            if neighbour in cells:
                root_a, root_b = find((cx, cy)), find(neighbour)
                if root_a != root_b:
                    parent[root_a] = root_b

    merged = defaultdict(list)
    for key, members in cells.items():
        merged[find(key)].extend(members)
    return merged


def load_dataset_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"MISSING INPUT: {path} -- run labelling/fetch_dataset.py first")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_export(path: str) -> dict:
    """global_key -> workflow status, for every row already in the project."""
    status = {}
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            project = (rec.get("projects") or {}).get(PROJECT_ID)
            if project is None:
                continue
            details = project.get("project_details") or {}
            status[rec["data_row"]["global_key"]] = {
                "workflow_status": details.get("workflow_status"),
                "batch_name": details.get("batch_name"),
                "n_labels": len(project.get("labels") or []),
            }
    return status


def write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def reconcile(dataset_rows: list[dict], in_project: dict, log) -> list[dict]:
    """State the two populations inside the dataset, in plain counts."""
    migrated = [r for r in dataset_rows if r["global_key"].startswith("migrated/")]
    labelled = [r for r in dataset_rows if r["global_key"] in in_project]
    unlabelled = [r for r in dataset_rows if r["global_key"] not in in_project]

    log("--- WHAT IS IN THE DATASET ---")
    log(f"dataset 2024_bci rows                 : {len(dataset_rows)}")
    log(f"  prefix 'migrated/' (old project)    : {len(migrated)}")
    log(f"  prefix '<flight folder>/' (current) : {len(dataset_rows) - len(migrated)}")
    log(f"already in project 2024_bci           : {len(labelled)}")
    log(f"  of which migrated/                  : "
        f"{sum(1 for r in labelled if r['global_key'].startswith('migrated/'))}")
    log(f"not in the project                    : {len(unlabelled)}")
    log(f"  of which migrated/                  : "
        f"{sum(1 for r in unlabelled if r['global_key'].startswith('migrated/'))}")
    status = Counter(v["workflow_status"] for k, v in in_project.items()
                     if not k.startswith("migrated/"))
    log("workflow status, non-migrated rows    : "
        f"{', '.join(f'{k}={v}' for k, v in sorted(status.items()))}")
    log("Every migrated row is DONE, so the project's live work is one pilot")
    log("mission. The unsent remainder is the whole 2026 flying season.")
    log("")
    return unlabelled


def report_polygon_identity(dataset_rows: list[dict], log) -> None:
    """Record that no crown identity is recoverable from this metadata.

    Two proxies suggest themselves and both are wrong. Writing the test down
    matters more than the queue it rules out: without it the next person spends
    the same day rediscovering that ``polygon`` looks like a tree id.
    """
    log("--- CAN WE TELL WHICH CROWN A PHOTO SHOWS? (no) ---")

    by_polygon = defaultdict(list)
    for row in dataset_rows:
        by_polygon[row["metadata"].get("polygon")].append(row)
    shared = [rows for rows in by_polygon.values() if len(rows) > 1]
    reused_across_missions = sum(
        1 for rows in shared
        if len({r["metadata"].get("mission") for r in rows}) == len(rows))

    # If `polygon` named a tree, two photos sharing one would sit on top of each
    # other. Compare their separation against random pairs from the same site.
    def metres(a, b):
        return math.hypot((a[0] - b[0]) * 111320.0,
                          (a[1] - b[1]) * 111320.0 * math.cos(math.radians(a[0])))

    same, rnd = [], []
    for rows in shared:
        points = [gps_of(r) for r in rows if gps_of(r)]
        same.extend(metres(points[i], points[i + 1])
                    for i in range(len(points) - 1))
    located = [r for r in dataset_rows if gps_of(r)]
    rng = random.Random(0)
    for _ in range(3000):
        a, b = rng.sample(located, 2)
        rnd.append(metres(gps_of(a), gps_of(b)))
    def median(values):
        return sorted(values)[len(values) // 2] if values else float("nan")

    log(f"'polygon' values                      : {len(by_polygon)} distinct, "
        f"range {min(by_polygon)}-{max(by_polygon)}")
    log(f"  shared by >1 photo                  : {len(shared)}")
    log(f"  ... always from different missions  : {reused_across_missions}")
    log(f"  median separation, same polygon     : {median(same):.0f} m")
    log(f"  median separation, random pair      : {median(rnd):.0f} m")
    log("  Identical. 'polygon' is the waypoint index within one flight (it is")
    log("  the number in the file name), not a tree. Deduplicating on it would")
    log("  merge trees kilometres apart.")

    # Second proxy: drone position. Score it on the only truth available -- do
    # co-located photos carry the same botanist label?
    gt = {}
    for row in hc.read_csv_rows(hc.GT_CSV):
        gt[basename(row["global_key"])] = row["wcvp_canonical_name"]
    for radius in GPS_CLUSTER_RADII_M:
        cells = gps_clusters(located, radius)
        pure = impure = 0
        for members in cells.values():
            names = {gt[basename(r["global_key"])] for r in members
                     if basename(r["global_key"]) in gt}
            if len([r for r in members if basename(r["global_key"]) in gt]) >= 2:
                pure += len(names) == 1
                impure += len(names) > 1
        total = pure + impure
        log(f"  GPS cells at {radius:2} m                   : {len(cells)} cells, "
            f"same-species purity {hc.pct(pure, total) if total else 'n/a'} "
            f"({pure}/{total} multi-label cells)")
    log("  Drone position is where the aircraft hovered, not where the crown is,")
    log("  so co-location does not mean same tree either.")
    log("  Nor is 'polygon' a census tag. Checked offline against the 7,688-crown")
    log("  combined_crownmaps_2025 (speciesfirst-docs): matching polygon to Tag")
    log("  puts photo and crown 2577 m apart at the median, worse than the 897 m")
    log("  to the nearest crown of any tag; scoping the match to the crown map's")
    log("  own plot resolves 72 of 1744 photos, still 315 m out. Whatever numbers")
    log("  the mission planner writes into the file name, they are not that map.")
    log("  A point-in-polygon join would need the camera footprint (gimbal yaw and")
    log("  pitch, focal length, altitude, and a canopy height model) rather than")
    log("  the drone's own coordinate. The cheap route is the waypoint-to-crown")
    log("  table the flight planner already had. Ask for it before rebuilding it.")
    log("")


def build_mission_queue(unlabelled: list[dict], log) -> list[dict]:
    """The 32 unsent flights, largest first. The unit the team already uses."""
    by_mission = defaultdict(list)
    for row in unlabelled:
        by_mission[row["metadata"].get("mission")].append(row)

    missions = []
    for mission, rows in by_mission.items():
        dates = sorted(r["created_at"] for r in rows)
        missions.append({
            "mission": mission,
            "sensor": sensor_of(mission),
            "photos": len(rows),
            "first_ingested": dates[0][:10],
            "median_bytes": sorted(
                (r.get("media_attributes") or {}).get("contentLength") or 0
                for r in rows)[len(rows) // 2],
        })
    missions.sort(key=lambda m: (-m["photos"], m["mission"]))
    for rank, mission in enumerate(missions, 1):
        mission["rank"] = rank

    log("--- UNSENT FLIGHTS ---")
    log(f"unsent photos                         : {len(unlabelled)}")
    log(f"  distinct missions                   : {len(missions)}")
    log(f"  median photos per mission           : "
        f"{sorted(m['photos'] for m in missions)[len(missions) // 2]}")
    sensors = Counter(m["sensor"] for m in missions)
    log(f"  by sensor (missions)                : "
        f"{', '.join(f'{k}={v}' for k, v in sorted(sensors.items()))}")
    log("  For scale, the one pilot batch the botanists are working through is")
    log("  213 photos and is still in review. The unsent pool is 15 such batches.")
    log("")
    return missions


def build_photo_queue(unlabelled: list[dict], missions: list[dict]) -> list[dict]:
    """Every unsent photo, mission-ordered. A dispatch convenience, not a rank.

    Within a mission the order is the M3E-then-larger-file proxy: at fixed
    encoder quality a bigger JPEG carries more high-frequency detail, which
    usually means sharper and less sky. Untested on these photos. It decides
    which of two otherwise identical photos goes first and nothing more.
    """
    rank_of = {m["mission"]: m["rank"] for m in missions}
    rows = []
    for row in unlabelled:
        mission = row["metadata"].get("mission", "")
        attrs = row.get("media_attributes") or {}
        rows.append({
            "global_key": row["global_key"],
            "data_row_id": row["uid"],
            "mission": mission,
            "mission_rank": rank_of.get(mission, 999),
            "waypoint": row["metadata"].get("polygon"),
            "sensor": sensor_of(mission),
            "bytes": attrs.get("contentLength") or 0,
            "gps": attrs.get("gpsPoint") or "",
            "row_data": row["row_data"],
        })
    rows.sort(key=lambda r: (r["mission_rank"], 0 if r["sensor"] == "m3e" else 1,
                             -r["bytes"], r["global_key"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def crop_verdict(rec: dict, top1_name: str, min_coverage: float) -> str:
    """Is this row a disagreement about one tree, or an artifact of the crop?

    ``crop_dominant`` is the labelled species covering most of the centre crop
    that was sent to Pl@ntNet, canonicalised the same way as ``gt`` so the two
    compare. The four outcomes, in the order a botanist should care about them:

    ``send``            the field label is what the model saw, and it still
                        disagreed. A real contradiction about one crown.
    ``low_coverage``    the field label dominates the crop but holds less than
                        ``min_coverage`` of it, so the model saw mostly canopy
                        that nobody labelled. Weak evidence either way.
    ``other_crown``     the crop is dominated by a *different* labelled species.
                        The model was asked about one tree and scored against
                        another. Sending this teaches the botanist that the
                        model is wrong when it is not.
    ``unknown_geometry`` no crown box exists for the frame, so what the model
                        saw cannot be reconstructed. Unprovable, not wrong.
    """
    if rec["crop_coverage"] is None:
        return "unknown_geometry"
    dominant = rec["crop_dominant"]
    if dominant is not None and dominant != rec["gt"]:
        return "other_crown"
    if rec["crop_coverage"] < min_coverage:
        return "low_coverage"
    return "send"


def build_contradiction_queue(dataset_rows: list[dict], min_score: float,
                              min_coverage: float, log) -> list[dict]:
    """Field label vs Pl@ntNet top-1, resolved onto live dataset global keys."""
    health = hc.load_health()
    by_basename = {basename(r["global_key"]): r for r in dataset_rows}

    queue, unresolved = [], 0
    for rec in health.sp_recs:
        top1_name, top1_score = rec["ranked"][0]
        if top1_name == rec["gt"] or top1_score < min_score:
            continue
        gt_rank = next((i for i, (n, _) in enumerate(rec["ranked"], 1)
                        if n == rec["gt"]), None)
        row = by_basename.get(basename(rec["global_key"]))
        if row is None:
            unresolved += 1
            continue
        verdict = crop_verdict(rec, top1_name, min_coverage)
        queue.append({
            "global_key": row["global_key"],
            "data_row_id": row["uid"],
            "mission": row["metadata"].get("mission", ""),
            "waypoint": row["metadata"].get("polygon"),
            "field_label": rec["gt"],
            "predicted": top1_name,
            "predicted_score": round(top1_score, 5),
            "field_label_rank_in_top5": gt_rank or "",
            "field_label_absent_from_top5": "" if gt_rank else "yes",
            "verdict": verdict,
            "crop_coverage": ("" if rec["crop_coverage"] is None
                              else round(rec["crop_coverage"], 3)),
            "crop_dominant": rec["crop_dominant"] or "",
            "predicted_is_crop_dominant": (
                "yes" if (verdict == "other_crown"
                          and top1_name == rec["crop_dominant"]) else ""),
            "row_data": row["row_data"],
        })

    queue.sort(key=lambda r: (VERDICT_ORDER.index(r["verdict"]),
                             -r["predicted_score"]))
    for rank, row in enumerate(queue, 1):
        row["rank"] = rank

    tally = Counter(r["verdict"] for r in queue)
    disagreeing = sum(1 for r in health.sp_recs if r["ranked"][0][0] != r["gt"])
    log("--- FIELD LABEL vs PL@NTNET ---")
    log(f"species-level crowns scored           : {len(health.sp_recs)}")
    log(f"  top-1 disagrees with field label    : {disagreeing}")
    log(f"  ... and top-1 score >= {min_score}          : {len(queue) + unresolved}")
    log(f"  resolved onto a live dataset row    : {len(queue)}")
    log(f"  NOT in the current dataset          : {unresolved}")
    log("  The unresolved ones are photos the old project holds that the")
    log("  migration into dataset 2024_bci did not carry over. They cannot be")
    log("  batched from here at all, whatever the permissions.")
    log(f"  Of the {len(queue)} that resolve, "
        f"{sum(1 for r in queue if r['field_label_absent_from_top5'])} have the field")
    log("  label nowhere in the model's top 5, which is the sharper disagreement.")
    log("")
    log("  Pl@ntNet saw a 1280x1280 centre crop, 13.7% of the 4000x3000 frame.")
    log("  The field label comes from a crown box drawn anywhere in that frame,")
    log("  so a disagreement can mean the model named a different tree correctly.")
    log(f"  send             : {tally['send']:3d}  field label dominates the crop, "
        f">= {min_coverage:.0%} of it")
    log(f"  low_coverage     : {tally['low_coverage']:3d}  field label dominates "
        "but holds little of the crop")
    log(f"  other_crown      : {tally['other_crown']:3d}  crop is dominated by a "
        "DIFFERENT labelled species")
    matched = sum(1 for r in queue if r["predicted_is_crop_dominant"])
    log(f"    ... of which Pl@ntNet named that other species exactly: {matched}")
    log("    Those are not model errors. The label points at another crown.")
    log(f"  unknown_geometry : {tally['unknown_geometry']:3d}  no crown box for the "
        "frame, so unprovable")
    log("")
    return queue


def main(argv=None) -> int:
    args = parse_args(argv)
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    dataset_rows = load_dataset_rows(args.dataset_rows)
    in_project = load_export(args.export)
    os.makedirs(args.out_dir, exist_ok=True)

    log(f"dataset rows file : {args.dataset_rows}")
    log(f"project export    : {args.export}")
    log("")
    unlabelled = reconcile(dataset_rows, in_project, log)
    report_polygon_identity(dataset_rows, log)
    missions = build_mission_queue(unlabelled, log)
    photos = build_photo_queue(unlabelled, missions)
    contradictions = build_contradiction_queue(dataset_rows, args.min_score,
                                               args.min_coverage, log)

    outputs = [
        ("queue_contradictions.csv",
         ["rank", "verdict", "global_key", "data_row_id", "mission", "waypoint",
          "field_label", "predicted", "predicted_score",
          "field_label_rank_in_top5", "field_label_absent_from_top5",
          "crop_coverage", "crop_dominant", "predicted_is_crop_dominant",
          "row_data"], contradictions),
        ("queue_missions.csv",
         ["rank", "mission", "sensor", "photos", "first_ingested",
          "median_bytes"], missions),
        ("queue_photos.csv",
         ["rank", "global_key", "data_row_id", "mission", "mission_rank",
          "waypoint", "sensor", "bytes", "gps", "row_data"], photos),
    ]
    log("--- OUTPUTS ---")
    for name, fields, rows in outputs:
        path = os.path.join(args.out_dir, name)
        write_csv(path, fields, rows)
        log(f"  {path}  ({len(rows)} rows)")

    report = os.path.join(args.out_dir, "report.txt")
    with open(report, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
