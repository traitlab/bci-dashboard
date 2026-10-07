"""Write a ground truth that uses the reviewed publication labels where they apply.

The workbook ``BCI Raw Data Publication - Final List.xlsx`` (sheet ``master``)
holds one row per published crown, with the reviewed name in ``FINAL_SPECIES``
and the photo it was read from in ``zoom_url_legacy``. A labelled frame whose
own image URL, as the dataset inventory states it, equals a BCI crown's
``zoom_url_legacy`` exactly takes that crown's reviewed name. Every other
labelled frame keeps its Labelbox label from ``gt_dominant_taxon.csv``. Each
row says which it is in ``label_source``, so measure.py reports the two
populations side by side instead of pooling a reviewed label with an
unreviewed one.

Exact URL equality only. A filename or mission/flight suffix match is not used:
it does not establish that two links name the same photo. A URL two crowns
share would make the reviewed label a guess, so such a frame keeps its Labelbox
label and the run says how many there were.

The xlsx is read with ``zipfile`` and the sheet XML; no spreadsheet package is
a dependency. Offline: nothing is fetched and the inputs are never written.

The published headline is scored on this file's reviewed rows, so the
workbook is a required input: bin/refresh.sh runs ``--check`` before it merges
anything and this script right after the Labelbox merge. A missing workbook
stops the run; nothing falls back to the Labelbox labels.

Usage:
    python3 labelling/gt_from_publication.py            # data/publication_final_list.xlsx
    python3 labelling/gt_from_publication.py --check    # the workbook is there and reads
    python3 dashboard/measure.py                        # scores the reviewed rows

Out: ``data/gt_publication_reviewed.csv`` and its ``.provenance.txt`` sidecar.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

# dashboard/ is a script directory, not a package: its core is found on the
# path, the way draw_holdout.py finds it.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "dashboard")
)
core = importlib.import_module("core")

SHEET = "master"
SITE = "bci"
ID_COLUMN = "canopyrs_object_id"
SITE_COLUMN = "site"
REVIEWED_COLUMN = "FINAL_SPECIES"
URL_COLUMN = "zoom_url_legacy"
REQUIRED_COLUMNS = (ID_COLUMN, SITE_COLUMN, REVIEWED_COLUMN, URL_COLUMN)
OUT_COLUMNS = (
    "global_key",
    "wcvp_canonical_name",
    core.LABEL_SOURCE_COLUMN,
    core.LABELBOX_NAME_COLUMN,
    ID_COLUMN,
)

# One spelling pair the WCVP cache does not join. GBIF resolves both names
# EXACT to one accepted taxon (usage key 8153963, Terminalia amazonica; the
# other is its synonym), and the Labelbox labels and Pl@ntNet both write
# "Terminalia amazonia". The reviewed spelling is mapped onto that one so a
# spelling difference is not scored as a wrong answer.
EQUIVALENT_NAMES = {"terminalia amazonica": "Terminalia amazonia"}

_NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_CODE_SUFFIX = re.compile(r"\s*\[[^\]]+\]\s*$")
_COLUMN_LETTERS = re.compile(r"[A-Z]+")


def reviewed_name(value: str) -> str:
    """``Hieronyma alchorneoides [HYERAL]`` -> ``Hieronyma alchorneoides``.

    The bracketed code is the census mnemonic, not part of the name. Whitespace
    is collapsed; case is kept, as the Labelbox names keep it.
    """
    name = " ".join(_CODE_SUFFIX.sub("", value or "").split())
    return EQUIVALENT_NAMES.get(core.normalize(name), name)


def read_sheet(path: str | os.PathLike, sheet: str = SHEET) -> list[dict]:
    """The named sheet as a list of dicts keyed by its first row.

    Raises SystemExit, naming the file, when the sheet is absent, empty or
    lacks a required column, because every one of those is a workbook the
    rest of this script would otherwise turn into a quietly empty match.
    """
    with zipfile.ZipFile(path) as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_id = next(
            (
                s.get(f"{{{_NS['r']}}}id")
                for s in book.findall("s:sheets/s:sheet", _NS)
                if s.get("name") == sheet
            ),
            None,
        )
        if rel_id is None:
            raise SystemExit(f"{path}: no sheet named {sheet!r}")
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(
            r.get("Target")
            for r in rels.findall("p:Relationship", _NS)
            if r.get("Id") == rel_id
        )
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [
                "".join(si.itertext())
                for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(
                    "s:si", _NS
                )
            ]
        root = ET.fromstring(archive.read(target))

    rows = []
    for row in root.findall("s:sheetData/s:row", _NS):
        cells = {}
        for cell in row.findall("s:c", _NS):
            kind = cell.get("t")
            if kind == "inlineStr":
                text = "".join(cell.find("s:is", _NS).itertext())
            else:
                v = cell.find("s:v", _NS)
                text = (v.text or "") if v is not None else ""
                if kind == "s" and text:
                    text = strings[int(text)]
            cells[_COLUMN_LETTERS.match(cell.get("r")).group()] = text
        rows.append(cells)
    if not rows:
        raise SystemExit(f"{path}: sheet {sheet!r} is empty")
    header = {col: name.strip() for col, name in rows[0].items() if name.strip()}
    missing = [c for c in REQUIRED_COLUMNS if c not in header.values()]
    if missing:
        raise SystemExit(
            f"{path}: sheet {sheet!r} has no column "
            + ", ".join(repr(c) for c in missing)
        )
    records = [
        {name: cells.get(col, "").strip() for col, name in header.items()}
        for cells in rows[1:]
    ]
    records = [r for r in records if any(r.values())]
    if not records:
        raise SystemExit(f"{path}: sheet {sheet!r} has a header and no rows")
    return records


def reviewed_by_url(crowns: list[dict], site: str = SITE):
    """legacy zoom URL -> the one crown photographed there, for ``site`` only.

    Returns the map and the set of URLs two or more crowns share, which are left
    out of the map. A crown on the site without a reviewed name fails the run:
    the workbook is the final list, and a blank there is for a person to fix.
    """
    on_site = [c for c in crowns if c[SITE_COLUMN].strip().lower() == site]
    blank = [c[ID_COLUMN] for c in on_site if not reviewed_name(c[REVIEWED_COLUMN])]
    if blank:
        raise SystemExit(
            f"{len(blank)} {site} crown(s) have an empty {REVIEWED_COLUMN}: "
            + ", ".join(blank[:10])
        )
    per_url = Counter(c[URL_COLUMN] for c in on_site if c[URL_COLUMN])
    shared = {u for u, n in per_url.items() if n > 1}
    by_url = {
        c[URL_COLUMN]: c
        for c in on_site
        if c[URL_COLUMN] and c[URL_COLUMN] not in shared
    }
    return by_url, shared


def build_rows(
    gt_rows: list[dict], image_urls: dict[str, str], by_url: dict[str, dict]
) -> list[dict]:
    """One output row per GT row, in GT order. Nothing is dropped."""
    out = []
    for r in gt_rows:
        crown = by_url.get(image_urls.get(r["global_key"], ""))
        out.append(
            {
                "global_key": r["global_key"],
                "wcvp_canonical_name": (
                    reviewed_name(crown[REVIEWED_COLUMN])
                    if crown
                    else r["wcvp_canonical_name"]
                ),
                core.LABEL_SOURCE_COLUMN: (
                    core.LABEL_SOURCE_REVIEWED
                    if crown
                    else core.LABEL_SOURCE_UNREVIEWED
                ),
                core.LABELBOX_NAME_COLUMN: r["wcvp_canonical_name"],
                ID_COLUMN: crown[ID_COLUMN] if crown else "",
            }
        )
    return out


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=core.summarise(__doc__))
    ap.add_argument(
        "--workbook",
        default=core.PUBLICATION_WORKBOOK,
        help="the publication xlsx (default: "
        f"{os.path.relpath(core.PUBLICATION_WORKBOOK, core.REPO)})",
    )
    ap.add_argument("--sheet", default=SHEET, help=f"sheet to read (default: {SHEET})")
    ap.add_argument("--gt", default=core.GT_CSV, help="the Labelbox ground truth")
    ap.add_argument(
        "--inventory",
        action="append",
        default=None,
        help="dataset inventory JSONL giving each frame's image URL; "
        "repeatable (default: the two legacy inventories)",
    )
    ap.add_argument(
        "--out",
        default=core.PUBLICATION_GT_CSV,
        help="where to write the reviewed-label ground truth",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="only confirm the workbook is there and its sheet reads; write nothing",
    )
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if not os.path.exists(args.workbook):
        raise SystemExit(
            f"Cannot find the publication workbook\n  {args.workbook}\nThe published "
            f"headline is scored against its reviewed labels and there is no fallback "
            f"to the Labelbox labels. Put the BCI Raw Data Publication final list "
            f"there, or name it with --workbook."
        )
    if args.check:
        read_sheet(args.workbook, args.sheet)
        print(f"workbook ok: {args.workbook}")
        return
    if not os.path.exists(args.gt):
        raise SystemExit(f"Cannot find {args.gt}")
    gt_rows = core.read_csv_rows(args.gt)
    if (
        not gt_rows
        or "global_key" not in gt_rows[0]
        or "wcvp_canonical_name" not in gt_rows[0]
    ):
        raise SystemExit(f"{args.gt}: needs global_key and wcvp_canonical_name rows")
    crowns = read_sheet(args.workbook, args.sheet)
    by_url, shared = reviewed_by_url(crowns)
    image_urls = core.inventory_image_urls(
        tuple(args.inventory or core.LEGACY_INVENTORIES)
    )
    rows = build_rows(gt_rows, image_urls, by_url)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, OUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    sources = Counter(r[core.LABEL_SOURCE_COLUMN] for r in rows)
    n_rev = sources[core.LABEL_SOURCE_REVIEWED]
    changed = sum(
        1
        for r in rows
        if r[core.LABEL_SOURCE_COLUMN] == core.LABEL_SOURCE_REVIEWED
        and core.normalize(r["wcvp_canonical_name"])
        != core.normalize(r[core.LABELBOX_NAME_COLUMN])
    )
    digest = hashlib.sha256(Path(args.workbook).read_bytes()).hexdigest()[:12]
    note = (
        f"Ground truth: reviewed publication labels ({Path(args.workbook).name}, "
        f"sheet {args.sheet}, sha256 {digest}) on {n_rev} of {len(rows)} labelled "
        f"frames, matched by exact legacy zoom URL; the other "
        f"{sources[core.LABEL_SOURCE_UNREVIEWED]} keep their Labelbox label and are "
        f"marked {core.LABEL_SOURCE_UNREVIEWED}. Labelbox labels: "
        f"{core.gt_provenance(args.gt)}"
    )
    out.with_suffix(".provenance.txt").write_text(note + "\n", encoding="utf-8")

    on_site = sum(1 for c in crowns if c[SITE_COLUMN].strip().lower() == SITE)
    print(
        f"workbook crowns {len(crowns)}, {SITE} {on_site}, "
        f"with a unique legacy zoom URL {len(by_url)}"
    )
    print(f"  legacy zoom URLs shared by two or more crowns (not used): {len(shared)}")
    print(
        f"GT frames {len(rows)}, with an inventory image URL "
        f"{sum(1 for r in gt_rows if r['global_key'] in image_urls)}"
    )
    for source in (core.LABEL_SOURCE_REVIEWED, core.LABEL_SOURCE_UNREVIEWED):
        print(f"  {source:<22}: {sources[source]}")
    print(f"  reviewed name differs from the Labelbox name: {changed}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
