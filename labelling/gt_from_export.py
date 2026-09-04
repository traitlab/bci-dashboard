"""Fold a Labelbox project export into the dominant-taxon GT.

The botanists' July 2026 revision was exported from the Labelbox project
``2024_bci`` as NDJSON on 2026-08-06: per-crown ``Planta`` boxes with a nested
Radio ``Taxon``. Those labels are the revised record, so where the export
covers a photo its label wins. Photos it does not cover keep the label an
earlier script (``15a_export_gt_dominant_taxon.py``, no longer in the repo)
derived offline from ``input/boxes/crop_bounding_boxes.csv``, and photos
newly labelled in the export are added.

Dominant taxon per photo is by summed box area, the rule that script used.
Taxon option names carry trailing ALL-CAPS code tokens
(``Mascagnia divaricata-MAS2DI`` / ``-MASCDI``); one or two are stripped so
name variants of one species collapse to the same string.

Rows outside the photo corpus (``splits.csv``) are dropped: the 2026-04-02
mission's tele photos have no cached prediction and would only pad the
no-cache log lines in the dashboard measurement.

Read-only: the NDJSON is parsed, never written back to Labelbox.

``--export`` may be repeated, and the merge is over the union. This matters for
the deep links rather than for the labels: an export names only the project it
came from, so one export can only ever mint ids for one project's rows, and the
single export on disk covers 1,719 of the 3,781 labelled frames. Pass the other
projects' exports alongside it and the id table covers their frames too, each
with its own ``project_id``, so a frame links into the project it belongs to.
Later exports win where two carry the same frame, so the argument order is the
recency order.

Usage:
    python3 labelling/gt_from_export.py \
        --export "/path/to/Export  project - 2024_bci - 8_6_2026.ndjson"
    python3 labelling/gt_from_export.py \
        --export data/exports/export_cmbgnzmhu0bed07027vmxezzd.ndjson \
        --export data/exports/export_cme99tjc606h4075147dfd6j6.ndjson \
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

    Also strips a single trailing code (``-MASCDI``), which that script's two-code
    strip left in place. Genera/families without codes pass through.
    """
    parts = str(name).split("-")
    while len(parts) > 1 and _CODE.match(parts[-1]):
        parts.pop()
    return "-".join(parts) if parts else str(name)


def export_dominants(ndjson_path: Path):
    """Basename -> dominant taxon by summed box area, boxes, row ids, and dates.

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

    The fourth return value is when each frame was labelled, from the export's
    own ``label_details.created_at``, latest label wins. Today that date is not
    a labelling journal. Of the 1,900 dated labels, every one of the 1,719 that
    the corpus knows about carries the same 2026-07-20 bulk migration stamp.
    The 181 that spread across 2026-07-03 to 2026-07-23 are all outside the
    frame list. So nothing is plotted against this. It is recorded because a
    trend across model versions needs dated labels to exist before it can be
    honest, and the material only starts accumulating once something writes it
    down.
    """
    area = defaultdict(Counter)
    boxes: list[dict] = []
    row_ids: dict[str, tuple[str, str]] = {}
    dates: dict[str, str] = {}
    with open(ndjson_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            stem = row["data_row"]["global_key"].rsplit("/", 1)[-1]
            for project_id in row.get("projects", {}):
                row_ids[stem] = (row["data_row"]["id"], project_id)
                break
            for proj in row.get("projects", {}).values():
                for label in proj.get("labels", []):
                    made = (label.get("label_details") or {}).get("created_at")
                    if made and made > dates.get(stem, ""):
                        dates[stem] = made
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
    return dominants, boxes, row_ids, dates


def union_exports(paths):
    """``export_dominants`` over several exports, folded into one result.

    Later files win on both the dominant taxon and the ``(data_row_id,
    project_id)`` pair, so the caller orders its arguments oldest first and gets
    the most recent read of any frame that appears twice. Boxes accumulate
    instead, because a frame that two projects both carry crowns for has both
    sets of crowns and dropping either would be a silent loss.
    """
    dominants: dict[str, str] = {}
    boxes: list[dict] = []
    row_ids: dict[str, tuple[str, str]] = {}
    dates: dict[str, str] = {}
    for path in paths:
        d, b, r, dt = export_dominants(Path(path))
        print(f"export {Path(path).name}: {len(d)} labelled frames, "
              f"{len(b)} boxes, {len(r)} data row ids, {len(dt)} dated")
        dominants.update(d)
        boxes.extend(b)
        row_ids.update(r)
        # Latest wins across exports too, for the same reason it wins inside
        # one: a frame relabelled later was labelled later.
        for stem, made in dt.items():
            if made > dates.get(stem, ""):
                dates[stem] = made
    return dominants, boxes, row_ids, dates


def parse_args():
    """The exports to merge, the three files they merge into, and an optional note.

    The note is written to a sidecar the dashboards read, so a page can say
    which batch its ground truth came from without anyone retyping it there.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", required=True, action="append",
                    help="Labelbox project export NDJSON; repeat to merge the "
                         "union of several projects, oldest first")
    ap.add_argument("--gt", default=str(GT), help="existing gt_dominant_taxon.csv")
    ap.add_argument("--splits", default=str(SPLITS), help="splits.csv (corpus keys)")
    ap.add_argument("--boxes-out", default=str(BOXES),
                    help="where to write the export crown geometry")
    ap.add_argument("--note", default=None,
                    help="one-line provenance note for the merged GT, e.g. the batch "
                         "name and its review status; written to a sidecar the "
                         "dashboards read, so the page never quotes a stale batch")
    return ap.parse_args()


def write_boxes(boxes, path):
    """The crown geometry exactly as the export drew it, never recomputed."""
    fields = ["base_image", "x_min", "y_min", "x_max", "y_max",
              "width", "height", "lb_label"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(boxes)
    print(f"export crown boxes {len(boxes)} on "
          f"{len({b['base_image'] for b in boxes})} frames -> {path}")


def merge_gt(base_gt, july, path):
    """Fold this export's labels into the accumulated ground truth.

    The export wins where the two disagree: it is the more recent read of the
    same photo by the same botanists. Which rows it revised is returned rather
    than swallowed, because a batch that revises hundreds of rows is worth
    someone looking at before it is trusted.
    """
    merged = dict(base_gt)
    revised = {k: (base_gt[k], sp) for k, sp in july.items()
               if k in base_gt and base_gt[k] != sp}
    new = {k: sp for k, sp in july.items() if k not in base_gt}
    merged.update(july)

    out = sorted(merged.items())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "wcvp_canonical_name"])
        w.writerows(out)
    return out, revised, new


def merge_row_ids(row_ids, corpus, n_gt, path):
    """Data row ids accumulate the same way the GT does.

    An export names only the project it came from, so a frame labelled in a
    project nobody has exported has no id here. That is the whole reason the
    coverage is what it is, and the fix is another export rather than a guess,
    so the share is printed and the gap is left visible for the pages to report.

    The per-project tally is printed with it because the table is expected to be
    mixed: a frame links into the project it belongs to, and one line per
    project is how a reader checks that a project they exported actually landed.
    """
    known: dict[str, tuple[str, str]] = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            known = {r["global_key"]: (r["data_row_id"], r["project_id"])
                     for r in csv.DictReader(f)}
    before = len(known)
    known.update({GT_KEY_PREFIX + stem: pair for stem, pair in row_ids.items()
                  if GT_KEY_PREFIX + stem in corpus})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "data_row_id", "project_id"])
        w.writerows([k, *known[k]] for k in sorted(known))
    share = f"{len(known) / n_gt:.1%}" if n_gt else "n/a"
    print(f"data row ids {before} -> {len(known)} ({share} of GT)  -> {path}")
    for project_id, n in sorted(Counter(p for _, p in known.values()).items()):
        print(f"  {n:5d}  in project {project_id}")


def merge_label_dates(dates, corpus, path):
    """When each frame was labelled, accumulated the way the row ids are.

    A sidecar rather than a third column on ``gt_dominant_taxon.csv``: that
    file is two columns everywhere it is read, and widening it is a breaking
    change for a value nothing reads yet.

    The spread is printed because it is the whole reason no page plots this.
    A date range of one day over thousands of frames is a migration stamp and
    not a labelling history, and the print is what makes that visible on the
    run that first produces a real spread.
    """
    known: dict[str, str] = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            known = {r["global_key"]: r["labelled_at"] for r in csv.DictReader(f)}
    before = len(known)
    for stem, made in dates.items():
        key = GT_KEY_PREFIX + stem
        if key in corpus and made > known.get(key, ""):
            known[key] = made
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "labelled_at"])
        w.writerows([k, known[k]] for k in sorted(known))
    print(f"label dates {before} -> {len(known)}  -> {path}")
    if known:
        days = Counter(v[:10] for v in known.values())
        top_day, top_n = days.most_common(1)[0]
        print(f"  {len(days)} distinct days, {min(days)} to {max(days)}; "
              f"{top_n} of {len(known)} share {top_day}")
        if len(days) == 1 or top_n > len(known) // 2:
            print("  NOTE: one day carries most of these, so they date the "
                  "export and not the labelling. No trend can be built on them.")


def report(base_gt, july, out, revised, new, gt_path):
    """What the merge did, in the four counts that have to add up.

    Agreed, revised and newly labelled sum to the export rows that landed in
    the corpus, so a reader can see nothing went missing between the file and
    the GT.
    """
    n_agree = len(july) - len(revised) - len(new)
    print(f"export photos in corpus with a species label : {len(july)}")
    print(f"  agreeing with existing GT                  : {n_agree}")
    print(f"  revising existing GT                       : {len(revised)}")
    print(f"  newly labelled (no prior GT)               : {len(new)}")
    print(f"GT rows {len(base_gt)} -> {len(out)}  -> {gt_path}")
    print(f"  distinct species {len(set(base_gt.values()))} -> "
          f"{len({sp for _, sp in out})}")
    top = Counter(g for g, _ in revised.values()).most_common(8)
    print("  most-revised away from:")
    for name, c in top:
        print(f"    {c:4d}  {name}")


def main() -> None:
    """Merge one Labelbox export into the ground truth, the crown boxes, the
    data row ids and the label dates, then say what changed in each."""
    args = parse_args()

    with open(args.splits, newline="", encoding="utf-8") as f:
        corpus = {r["global_key"] for r in csv.DictReader(f)}

    with open(args.gt, newline="", encoding="utf-8") as f:
        base_gt = {r["global_key"]: r["wcvp_canonical_name"] for r in csv.DictReader(f)}

    july, boxes, row_ids, dates = union_exports(args.export)
    write_boxes(boxes, args.boxes_out)

    # Only frames the corpus knows about. An export can carry photos from
    # another project, and a GT row for a frame no page can score is dead weight.
    july = {GT_KEY_PREFIX + stem: sp for stem, sp in july.items()
            if GT_KEY_PREFIX + stem in corpus}

    out, revised, new = merge_gt(base_gt, july, args.gt)
    merge_row_ids(row_ids, corpus, len(out),
                  Path(args.gt).with_name("data_row_ids.csv"))
    merge_label_dates(dates, corpus, Path(args.gt).with_name("gt_label_dates.csv"))

    names = ", ".join(Path(p).name for p in args.export)
    note = args.note or (f"Ground truth merged from Labelbox export "
                         f"{names} on "
                         f"{datetime.now(timezone.utc).date().isoformat()}.")
    sidecar = Path(args.gt).with_suffix(".provenance.txt")
    sidecar.write_text(note + "\n", encoding="utf-8")
    print(f"provenance note                            -> {sidecar}")

    report(base_gt, july, out, revised, new, args.gt)


if __name__ == "__main__":
    main()
