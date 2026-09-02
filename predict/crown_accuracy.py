#!/usr/bin/env python3
"""
Crown-level Pl@ntNet accuracy, split by camera.

Reads the cache written by ``predict/crown.py`` and scores every crown that
carries a botanist label. The split that matters is zoom against tele: the
2024 corpus that the accuracy claims were built on is zoom, and every unsent
photo is tele.

The headline gap is reported raw and then decomposed. Raw stays the headline
because it is what the labelled crowns actually scored. The decomposition splits
it into the part the species mix explains, the part it does not, and the part
carried by species the reference camera has never seen, so a reader can tell how
much of the gap is a property of the corpus rather than of the camera.

The controls exist because the headline gap invites four easy objections, and
each one is checked here rather than argued: different species mix, smaller
crowns, stale box geometry, and a label attached to the wrong box. The last is
the sharpest test. If boxes and labels had drifted apart, a wrong prediction
would tend to name a *different* labelled crown in the same frame.

Confidence is reported per camera on purpose. A score threshold calibrated on
zoom does not carry over, and several downstream cuts (the contradiction queue,
any auto-accept rule) are exactly such a threshold.

Stdlib only. Deterministic. No network calls.

Run:  python3 predict/crown_accuracy.py
      python3 predict/crown_accuracy.py --cache-dir data/crowns/cache
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO / "data" / "crowns" / "cache"
EXPORT_BOXES = REPO / "data" / "export_boxes.csv"
DATASET_ROWS = REPO / "data" / "dataset_rows.jsonl"
SIZE_BINS = ((128, 256), (256, 512), (512, 10_000))
CONF_CUT = 0.5
MIN_SPECIES_N = 8
MIN_BASELINE_N = 3


def camera_of(base_image: str) -> str:
    """Camera from the file name. The two rigs write ``...tele.JPG``/``...zoom.JPG``."""
    return "tele" if "tele" in base_image else "zoom"


def gt_species(lb_label: str) -> str:
    """Botanist species from an ``lb_label`` like ``Luehea seemannii-LUEHSE-LUE1``.

    Returns "" for a label that is not a binomial, which drops genus-only and
    unparsed labels rather than scoring them as a miss.
    """
    name = (lb_label or "").split("-")[0].strip().lower()
    return name if " " in name else ""


def load_crowns(cache_dir: Path) -> list[dict]:
    """One row per cached crown that carries a botanist species name.

    Crowns without one are dropped here rather than counted as misses: nothing
    graded them, so they belong to no accuracy figure.
    """
    rows = []
    for path in sorted(cache_dir.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        gt = gt_species(entry.get("lb_label", ""))
        if not gt:
            continue
        results = entry.get("results") or []
        box = entry.get("box") or {}
        try:
            side = min(float(box["x_max"]) - float(box["x_min"]),
                       float(box["y_max"]) - float(box["y_min"]))
        except (KeyError, TypeError, ValueError):
            side = 0.0
        frac = frame_fraction(box, entry.get("frame_width"),
                              entry.get("frame_height"))
        names = [(r.get("scientific_name") or "").lower() for r in results]
        rows.append({
            "camera": camera_of(entry["base_image"]),
            "frame": entry["base_image"],
            "gt": gt,
            "top1": names[0] if names else "",
            "top5": names[:5],
            "score": float(results[0]["score"]) if results else 0.0,
            "side": side,
            "frac": frac,
            "box": box,
        })
    return rows


def frame_fraction(box: dict, width, height) -> float:
    """Crown box as a linear fraction of its frame, or 0.0 when unmeasurable.

    Linear rather than area, so the two cameras compare as a magnification. The
    frame size comes from the cache entry, never a constant, since a frame that
    broke the constant is what this control has to catch.
    """
    try:
        area = ((float(box["x_max"]) - float(box["x_min"]))
                * (float(box["y_max"]) - float(box["y_min"])))
        return math.sqrt(area / (float(width) * float(height)))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0.0


def load_missions(path: Path) -> dict[str, str]:
    """Frame name to mission identifier, from the dataset row dump.

    Keyed on the basename, which is the only component the three global-key
    namespaces share.
    """
    if not path.exists():
        return {}
    missions = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            mission = (row.get("metadata") or {}).get("mission")
            if mission:
                missions[Path(row["global_key"]).name] = mission
    return missions


def load_export_boxes(path: Path) -> dict[str, set[tuple[int, int]]]:
    if not path.exists():
        return {}
    boxes: dict[str, set[tuple[int, int]]] = collections.defaultdict(set)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            boxes[r["base_image"]].add(
                (int(float(r["x_min"])), int(float(r["y_min"]))))
    return boxes


def accuracy(rows: list[dict]) -> float:
    return sum(r["top1"] == r["gt"] for r in rows) / len(rows) if rows else 0.0


def headline(rows: list[dict], cameras: list[str]) -> None:
    print(f"{'camera':6} {'crowns':>7} {'species':>8} {'top-1':>8} {'top-5':>8} {'genus':>8}")
    for cam in cameras:
        sel = [r for r in rows if r["camera"] == cam]
        n = len(sel)
        top5 = sum(r["gt"] in r["top5"] for r in sel) / n
        genus = sum(r["top1"].split(" ")[0] == r["gt"].split(" ")[0] for r in sel) / n
        print(f"{cam:6} {n:>7} {len({r['gt'] for r in sel}):>8} "
              f"{accuracy(sel):>7.1%} {top5:>7.1%} {genus:>7.1%}")


def decomposition(rows: list[dict], reference: str, target: str) -> None:
    """Split the gap between two cameras into species mix and everything else.

    Direct standardization: hold the target camera's species composition and
    substitute the reference camera's per-species accuracy. The expected figure
    is what the target would score if every species behaved as it does on the
    reference. The distance from the reference's own headline is the part of the
    gap that the species mix alone explains, and the distance from the expected
    figure to what the target actually scores is the part it does not.

    Target crowns whose species has fewer than ``MIN_BASELINE_N`` reference
    crowns are reported on their own line. No reference rate exists for them, so
    standardizing over them would invent one.
    """
    ref = collections.defaultdict(list)
    for r in rows:
        if r["camera"] == reference:
            ref[r["gt"]].append(r["top1"] == r["gt"])
    based, thin = [], []
    for r in rows:
        if r["camera"] != target:
            continue
        (based if len(ref.get(r["gt"], ())) >= MIN_BASELINE_N else thin).append(r)
    if not based:
        return
    expected = sum(
        sum(ref[r["gt"]]) / len(ref[r["gt"]]) for r in based) / len(based)
    all_ref = [r for r in rows if r["camera"] == reference]
    all_tgt = based + thin

    print(f"\ndecomposition - the {reference} to {target} gap, "
          f"{accuracy(all_ref) - accuracy(all_tgt):.1%} in total")
    print(f"  {'step':52} {'n':>6} {'top-1':>8} {'drop':>7}")
    ladder = [
        (f"{reference}, every labelled crown", all_ref, accuracy(all_ref)),
        (f"{target}, if each species scored as it does on {reference}",
         based, expected),
        (f"{target}, observed, species with a {reference} baseline",
         based, accuracy(based)),
        (f"{target}, observed, every labelled crown", all_tgt, accuracy(all_tgt)),
    ]
    prev = None
    for label, sel, rate in ladder:
        drop = "" if prev is None else f"{prev - rate:>6.1%}"
        print(f"  {label:52} {len(sel):>6} {rate:>7.1%} {drop:>7}")
        prev = rate
    if thin:
        species = len({r["gt"] for r in thin})
        print(f"  the last step is {len(thin)} crowns of {species} species with "
              f"fewer than {MIN_BASELINE_N} {reference} crowns, "
              f"scoring {accuracy(thin):.1%}")


def shared_species(rows: list[dict], cameras: list[str]) -> set:
    """The species every camera has labelled frames for.

    Comparing cameras on all species compares two different species mixes as
    much as two cameras. This is the set that lets the rest of the controls
    hold the mix fixed.
    """
    return set.intersection(*({r["gt"] for r in rows if r["camera"] == c}
                              for c in cameras))


def control_same_species(rows, cameras, shared) -> None:
    """Control 1: the same species on every camera, so the mix cannot explain a gap."""
    print(f"\ncontrol 1 - only the {len(shared)} species every camera shows")
    for cam in cameras:
        sel = [r for r in rows if r["camera"] == cam and r["gt"] in shared]
        print(f"  {cam:6} n={len(sel):5}  top-1={accuracy(sel):.1%}")


def control_box_size(rows, cameras) -> None:
    """Control 2: how big the crowns are on each camera.

    A camera that only ever sees small crowns has a harder job, and this is
    where that shows up before it is mistaken for a worse camera.
    """
    print("\ncontrol 2 - crown box size, shortest side in px")
    for cam in cameras:
        sides = sorted(r["side"] for r in rows if r["camera"] == cam)
        print(f"  {cam:6} n={len(sides):5}  median={statistics.median(sides):.0f}  "
              f"p10={sides[len(sides) // 10]:.0f}  p90={sides[9 * len(sides) // 10]:.0f}")


def control_size_matched(rows, cameras, shared) -> None:
    """Control 3: same species and same crown size, the two controls together."""
    print("\ncontrol 3 - same species and same box size")
    for lo, hi in SIZE_BINS:
        parts = []
        for cam in cameras:
            sel = [r for r in rows if r["camera"] == cam and r["gt"] in shared
                   and lo <= r["side"] < hi]
            parts.append(f"{cam}={accuracy(sel):.1%} (n={len(sel)})")
        print(f"  side {lo}-{hi}: " + "  ".join(parts))


def control_export_geometry(rows, cameras, export_boxes) -> None:
    """Control 4: are these the boxes the current export drew?

    A crown scored against geometry from an older export is scored against a
    different crop of the photo, which is a silent way to be wrong.
    """
    print("\ncontrol 4 - do the boxes come from the current export geometry?")
    for cam in cameras:
        sel = [r for r in rows if r["camera"] == cam and r["box"]]
        hit = sum(
            (int(float(r["box"]["x_min"])), int(float(r["box"]["y_min"])))
            in export_boxes.get(r["frame"], ()) for r in sel)
        print(f"  {cam:6} {hit}/{len(sel)} crowns match a box in the export")


def control_wrong_box(rows, cameras) -> None:
    """Control 5: is the label attached to the wrong crown?

    The tell is a wrong call that names another labelled crown in the same
    frame. The model saw a tree that is there, just not the one the box was
    drawn around, so this counts a labelling error rather than a model error.
    """
    print("\ncontrol 5 - is the label on the wrong box?")
    print("  a wrong call that names another labelled crown in the same frame is the tell")
    by_frame = collections.defaultdict(list)
    for r in rows:
        by_frame[(r["camera"], r["frame"])].append(r)
    for cam in cameras:
        wrong = other = 0
        for (c, _), crowns in by_frame.items():
            if c != cam or len(crowns) < 2:
                continue
            for r in crowns:
                if not r["top1"] or r["top1"] == r["gt"]:
                    continue
                wrong += 1
                other += r["top1"] in {o["gt"] for o in crowns if o is not r}
        if wrong:
            print(f"  {cam:6} {other}/{wrong} wrong calls name a different "
                  f"labelled crown ({other / wrong:.1%})")


def controls(rows: list[dict], cameras: list[str], export_boxes: dict) -> None:
    """Five ways a camera gap could be something other than the camera, checked
    in the order they are worth ruling out."""
    shared = shared_species(rows, cameras)
    control_same_species(rows, cameras, shared)
    control_box_size(rows, cameras)
    control_size_matched(rows, cameras, shared)
    if export_boxes:
        control_export_geometry(rows, cameras, export_boxes)
    control_wrong_box(rows, cameras)


def magnification(rows: list[dict], cameras: list[str]) -> None:
    print("\ncontrol 6 - apparent magnification, crown box against its own frame")
    medians = {}
    for cam in cameras:
        fracs = sorted(r["frac"] for r in rows if r["camera"] == cam and r["frac"])
        if not fracs:
            continue
        medians[cam] = statistics.median(fracs)
        print(f"  {cam:6} n={len(fracs):5}  median linear={medians[cam]:.3f}  "
              f"area={medians[cam] ** 2:.1%}")
    if len(medians) == 2:
        (lo, a), (hi, b) = sorted(medians.items(), key=lambda kv: kv[1])
        print(f"  a crown is {b / a:.2f}x larger linearly on {hi} than on {lo}, "
              f"so {hi} is not the smaller-crown camera")


def campaigns(rows: list[dict], cameras: list[str],
              missions: dict[str, str]) -> None:
    """Whether the cameras share a mission, a calendar day, or a site.

    The decomposition's middle step is about the camera only if nothing else
    varies with it, so the sharing is reported rather than assumed.
    """
    print("\ncontrol 7 - do the cameras share a mission, a day or a site?")
    seen: dict[str, dict[str, set]] = {}
    for cam in cameras:
        frames = {r["frame"] for r in rows if r["camera"] == cam}
        named = {missions[f] for f in frames if f in missions}
        if not named:
            print(f"  {cam:6} no mission recorded for any of its {len(frames)} frames")
            continue
        parts = [m.split("_") for m in named]
        seen[cam] = {
            "mission": named,
            "day": {p[0] for p in parts},
            "site": {p[1] for p in parts if len(p) > 1},
            "aircraft": {p[-1] for p in parts},
        }
        days = sorted(seen[cam]["day"])
        print(f"  {cam:6} {sum(r['camera'] == cam for r in rows):5} crowns  "
              f"{len(frames):5} frames  {len(named):3} mission(s)  "
              f"{days[0]}..{days[-1]}  "
              f"aircraft {','.join(sorted(seen[cam]['aircraft']))}  "
              f"{len(seen[cam]['site'])} site(s)")
    if len(seen) != 2:
        return
    left, right = (seen[c] for c in sorted(seen))
    for kind in ("mission", "day", "site"):
        both = left[kind] & right[kind]
        total = len(left[kind] | right[kind])
        print(f"  {kind + 's carrying both cameras:':38} {len(both):3} of {total}")
    if not left["mission"] & right["mission"]:
        print("  the cameras share no mission, so a gap measured across cameras "
              "is measured across missions too")


def confidence(rows: list[dict], cameras: list[str]) -> None:
    print("\nconfidence - a threshold set on one camera does not carry to the other")
    for cam in cameras:
        sel = [r for r in rows if r["camera"] == cam]
        conf = [r for r in sel if r["score"] >= CONF_CUT]
        med = statistics.median([r["score"] for r in sel])
        print(f"  {cam:6} median top-1 score={med:.3f}   "
              f"top-1 correct when score>={CONF_CUT}: {accuracy(conf):.1%} (n={len(conf)})")


def per_species(rows: list[dict], camera: str) -> None:
    print(f"\nper species on {camera}, where at least {MIN_SPECIES_N} crowns are labelled")
    hits = collections.defaultdict(list)
    for r in rows:
        if r["camera"] == camera:
            hits[r["gt"]].append(r["top1"] == r["gt"])
    for sp, v in sorted(hits.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
        if len(v) >= MIN_SPECIES_N:
            print(f"  {sp:34} n={len(v):3}  {sum(v) / len(v):6.1%}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    p.add_argument("--export-boxes", type=Path, default=EXPORT_BOXES)
    p.add_argument("--dataset-rows", type=Path, default=DATASET_ROWS)
    p.add_argument("--per-species-camera", default="tele")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    rows = load_crowns(args.cache_dir)
    if not rows:
        raise SystemExit(f"no labelled crowns in {args.cache_dir}")
    cameras = sorted({r["camera"] for r in rows})
    print(f"{len(rows)} labelled crowns from {args.cache_dir}\n")
    headline(rows, cameras)
    if len(cameras) > 1:
        by_size = sorted(cameras, key=lambda c: sum(r["camera"] == c for r in rows))
        decomposition(rows, reference=by_size[-1], target=by_size[0])
        controls(rows, cameras, load_export_boxes(args.export_boxes))
        magnification(rows, cameras)
        campaigns(rows, cameras, load_missions(args.dataset_rows))
    confidence(rows, cameras)
    if args.per_species_camera in cameras:
        per_species(rows, args.per_species_camera)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
