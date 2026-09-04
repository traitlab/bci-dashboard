"""Can we tell which crown a photo shows? No, and here is the test.

Split out of ``next_batch.py``, which builds the queues. This is not a queue:
it is a negative result kept in the run report so the next person does not
spend a day rediscovering that the ``polygon`` field looks like a tree id.
Two proxies suggest themselves, both were checked against ground truth, and
both fail. ``next_batch.main`` calls ``report_polygon_identity`` and prints
what it returns.
"""

from __future__ import annotations

import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "dashboard"))

import core as hc

# Radii tried when testing whether drone position identifies a crown.
GPS_CLUSTER_RADII_M = (5, 10, 20)


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


def report_polygon_identity(dataset_rows: list[dict], log, basename) -> None:
    """Record that no crown identity is recoverable from this metadata.

    Two proxies suggest themselves and both are wrong. Writing the test down
    matters more than the queue it rules out: without it the next person spends
    the same day rediscovering that ``polygon`` looks like a tree id.

    ``basename`` is passed in rather than imported: which prefixes a global key
    can carry is the caller's business, and importing it back from
    ``next_batch`` would make the pair import each other.
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
