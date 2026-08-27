"""Phase 3a refresh — fold a Labelbox project export into the dominant-taxon GT.

``15a_export_gt_dominant_taxon.py`` derived the ground truth offline from
``input/boxes/crop_bounding_boxes.csv``. On 2026-08-06 the botanists' July 2026
revision pass was exported from the Labelbox project ``2024_bci`` as NDJSON:
per-crown ``Planta`` boxes with a nested Radio ``Taxon``. Those labels are the
revised record, so where the export covers a photo its label wins; photos the
export does not cover keep the offline label, and photos newly labelled in the
export are added.

Dominant taxon per photo is by summed box area, the same rule 15a used on the
crop CSV. Taxon option names carry trailing ALL-CAPS code tokens
(``Mascagnia divaricata-MAS2DI`` / ``-MASCDI``); one or two trailing codes are
stripped so name variants of one species collapse to the same string.

Rows outside the photo corpus (``splits.csv``) are dropped: the 2026-04-02
mission's tele photos have no cached prediction and would only pad the
no-cache log lines in the dashboard measurement.

Read-only — the NDJSON is parsed, never written back to Labelbox.

Usage:
    python3 labelling/gt_from_export.py \
        --export "/path/to/Export  project - 2024_bci - 8_6_2026.ndjson"

Out: ``data/gt_dominant_taxon.csv`` (rewritten in place)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GT = REPO / "data" / "gt_dominant_taxon.csv"
SPLITS = REPO / "data" / "splits.csv"
BOXES = REPO / "data" / "export_boxes.csv"
GT_KEY_PREFIX = "comb_"

_CODE = re.compile(r"^[A-Z0-9]{2,}$")


def strip_codes(name: str) -> str:
    """``Anacardium excelsum-ANACEX-ANAE`` -> ``Anacardium excelsum``.

    Also strips a single trailing code (``-MASCDI``), which 15a's two-code
    strip left in place. Genera/families without codes pass through.
    """
    parts = str(name).split("-")
    while len(parts) > 1 and _CODE.match(parts[-1]):
        parts.pop()
    return "-".join(parts) if parts else str(name)


def export_dominants(ndjson_path: Path) -> tuple[dict[str, str], list[dict], dict[str, tuple[str, str]]]:
    """Basename -> dominant taxon by summed box area, boxes, and data row ids.

    The third return value maps a basename to the ``(data_row_id, project_id)``
    the export recorded for it. That pair is the only way to build the Labelbox
    URL a reviewer clicks, and the export is the one place it can be read
    without a credential: a data row opens only inside a project it belongs to,
    and the export states both halves for every frame it carries.

    The boxes are returned as well as the dominants because they are the current
    crown geometry. ``input/boxes/crop_bounding_boxes.csv`` predates the July
    2026 revision and disagrees with the export badly: on the frames both cover
    it holds twice as many boxes per frame, only 35% of them are the same crown
    at IoU 0.5, and a fifth of even those carry a superseded species. Anything
    that needs to know where a crown is should read the export, not that file.

    Emitted in the column shape of crop_bounding_boxes.csv so that the coverage
    code can read either source without a second parser.
    """
    area = defaultdict(Counter)
    boxes: list[dict] = []
    row_ids: dict[str, tuple[str, str]] = {}
    with open(ndjson_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            stem = row["data_row"]["global_key"].rsplit("/", 1)[-1]
            for project_id in row.get("projects", {}):
                row_ids[stem] = (row["data_row"]["id"], project_id)
                break
            for proj in row.get("projects", {}).values():
                for label in proj.get("labels", []):
                    for obj in label.get("annotations", {}).get("objects", []):
                        sp = next(
                            (strip_codes(c["radio_answer"]["name"])
                             for c in obj.get("classifications", [])
                             if "radio_answer" in c),
                            None,
                        )
                        if sp is None:
                            continue
                        bb = obj.get("bounding_box") or {}
                        w, h = bb.get("width", 0), bb.get("height", 0)
                        area[stem][sp] += w * h
                        if not (w and h):
                            continue
                        x0, y0 = int(bb["left"]), int(bb["top"])
                        boxes.append({
                            "base_image": stem,
                            "x_min": x0, "y_min": y0,
                            "x_max": x0 + int(w), "y_max": y0 + int(h),
                            "width": int(w), "height": int(h),
                            "lb_label": sp,
                        })
    dominants = {stem: counts.most_common(1)[0][0]
                 for stem, counts in area.items() if counts}
    return dominants, boxes, row_ids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", required=True, help="Labelbox project export NDJSON")
    ap.add_argument("--gt", default=str(GT), help="existing gt_dominant_taxon.csv")
    ap.add_argument("--splits", default=str(SPLITS), help="splits.csv (corpus keys)")
    ap.add_argument("--boxes-out", default=str(BOXES),
                    help="where to write the export crown geometry")
    ap.add_argument("--note", default=None,
                    help="one-line provenance note for the merged GT, e.g. the batch "
                         "name and its review status; written to a sidecar the "
                         "dashboards read, so the page never quotes a stale batch")
    args = ap.parse_args()

    with open(args.splits, newline="", encoding="utf-8") as f:
        corpus = {r["global_key"] for r in csv.DictReader(f)}

    with open(args.gt, newline="", encoding="utf-8") as f:
        base_gt = {r["global_key"]: r["wcvp_canonical_name"] for r in csv.DictReader(f)}

    july, boxes, row_ids = export_dominants(Path(args.export))

    fields = ["base_image", "x_min", "y_min", "x_max", "y_max",
              "width", "height", "lb_label"]
    with open(args.boxes_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(boxes)
    print(f"export crown boxes {len(boxes)} on "
          f"{len({b['base_image'] for b in boxes})} frames -> {args.boxes_out}")

    july = {GT_KEY_PREFIX + stem: sp for stem, sp in july.items()
            if GT_KEY_PREFIX + stem in corpus}

    merged = dict(base_gt)
    revised = {k: (base_gt[k], sp) for k, sp in july.items()
               if k in base_gt and base_gt[k] != sp}
    new = {k: sp for k, sp in july.items() if k not in base_gt}
    merged.update(july)

    out = sorted(merged.items())
    with open(args.gt, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "wcvp_canonical_name"])
        w.writerows(out)

    # Data row ids accumulate the same way the GT does. An export names only
    # the project it came from, so a frame labelled in a legacy project has no
    # id here until that project's rows are migrated and exported again. The
    # pages report the coverage rather than guessing a link.
    ids_path = Path(args.gt).with_name("data_row_ids.csv")
    known: dict[str, tuple[str, str]] = {}
    if ids_path.exists():
        with open(ids_path, newline="", encoding="utf-8") as f:
            known = {r["global_key"]: (r["data_row_id"], r["project_id"])
                     for r in csv.DictReader(f)}
    before = len(known)
    known.update({GT_KEY_PREFIX + stem: pair for stem, pair in row_ids.items()
                  if GT_KEY_PREFIX + stem in corpus})
    with open(ids_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "data_row_id", "project_id"])
        w.writerows([k, *known[k]] for k in sorted(known))
    share = f"{len(known) / len(merged):.1%}" if merged else "n/a"
    print(f"data row ids {before} -> {len(known)} ({share} of GT)  -> {ids_path}")

    note = args.note or (f"Ground truth merged from Labelbox export "
                         f"{Path(args.export).name} on {datetime.now(timezone.utc).date().isoformat()}.")
    sidecar = Path(args.gt).with_suffix(".provenance.txt")
    sidecar.write_text(note + "\n", encoding="utf-8")
    print(f"provenance note                            -> {sidecar}")

    n_agree = len(july) - len(revised) - len(new)
    print(f"export photos in corpus with a species label : {len(july)}")
    print(f"  agreeing with existing GT                  : {n_agree}")
    print(f"  revising existing GT                       : {len(revised)}")
    print(f"  newly labelled (no prior GT)               : {len(new)}")
    print(f"GT rows {len(base_gt)} -> {len(out)}  -> {args.gt}")
    print(f"  distinct species {len(set(base_gt.values()))} -> "
          f"{len({sp for _, sp in out})}")
    top = Counter(g for g, _ in revised.values()).most_common(8)
    print("  most-revised away from:")
    for name, c in top:
        print(f"    {c:4d}  {name}")


if __name__ == "__main__":
    main()
