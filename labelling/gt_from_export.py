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
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GT = REPO / "data" / "gt_dominant_taxon.csv"
SPLITS = REPO / "data" / "splits.csv"
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


def export_dominants(ndjson_path: Path) -> dict[str, str]:
    """Basename -> dominant taxon by summed box area, from the export."""
    area = defaultdict(Counter)
    with open(ndjson_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            stem = row["data_row"]["global_key"].rsplit("/", 1)[-1]
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
                        area[stem][sp] += bb.get("width", 0) * bb.get("height", 0)
    return {stem: counts.most_common(1)[0][0]
            for stem, counts in area.items() if counts}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", required=True, help="Labelbox project export NDJSON")
    ap.add_argument("--gt", default=str(GT), help="existing gt_dominant_taxon.csv")
    ap.add_argument("--splits", default=str(SPLITS), help="splits.csv (corpus keys)")
    ap.add_argument("--note", default=None,
                    help="one-line provenance note for the merged GT, e.g. the batch "
                         "name and its review status; written to a sidecar the "
                         "dashboards read, so the page never quotes a stale batch")
    args = ap.parse_args()

    with open(args.splits, newline="", encoding="utf-8") as f:
        corpus = {r["global_key"] for r in csv.DictReader(f)}

    with open(args.gt, newline="", encoding="utf-8") as f:
        base_gt = {r["global_key"]: r["wcvp_canonical_name"] for r in csv.DictReader(f)}

    july = export_dominants(Path(args.export))
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

    note = args.note or (f"Ground truth merged from Labelbox export "
                         f"{Path(args.export).name} on {date.today().isoformat()}.")
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
