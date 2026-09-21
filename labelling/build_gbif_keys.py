#!/usr/bin/env python3
"""Write down the GBIF key behind every taxon option, so a rename stops hiding a match.

Each option in the Labelbox ``Taxón`` question carries a display label and a
``value``. The value is a GBIF backbone key: ``Abuta panamensis-ABUTPA-ABUP``
is 3830289. Every species on a Pl@ntNet checklist carries ``gbifId`` from the
same backbone. Both ends of the join exist already; only the name was ever
read, and a name join answers "is this species on the list" wrongly every time
the botanists rename an option. ``Pochota quinata`` became ``Pochota
fendleri``, ``Quararibea asterolepis`` became ``Quararibea stenophylla``, and
under the name join all three frames read as absent from a list that carries
them.

Two lookups come out of here:

``by_code`` maps the leading collection code (``VIROSU``) to the key. The
pre-2026 labels in ``input/boxes/crop_bounding_boxes.csv`` predate the current
option names but carry the same codes, so the code is what links an old label
to the option it was drawn from. 808 codes over 2,416 options, none ambiguous.

``by_name`` maps the code-stripped, normalized option label to the key, for
labels that carry no code at all.

``by_legacy`` does the same for the names the ontology no longer carries. The
ground truth stores option labels with their codes already stripped, so a
renamed option reaches the dashboard as a bare old name with nothing to join
on. Reading ``input/boxes/crop_bounding_boxes.csv``, which is tracked and does
keep the codes, turns each old name back into the code it was drawn with and
so into the key the option holds today.

``accepted`` resolves every key on both sides through the GBIF backbone to its
accepted usage key. Without it four species read as absent because the label
and the checklist hold two different keys for one taxon.

One GBIF request per distinct key, so the checklists to resolve are named
rather than globbed: ``core.EVAL_PROJECT``'s own list is the one membership is
read from, and k-world-flora alone would be 84,642 requests for an answer no
page asks for.

    python3 labelling/build_gbif_keys.py
    python3 labelling/build_gbif_keys.py --checklist k-central-america

Needs LABELBOX_API_KEY. Calls GBIF once per distinct key, unauthenticated.
Out: ``data/gbif_keys.json``. The dashboard reads it offline and never fetches.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import labelbox as lb
import requests
from settings import api_key, setting

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "gbif_keys.json"
BOXES = REPO / "input" / "boxes" / "crop_bounding_boxes.csv"
GBIF_SPECIES = "https://api.gbif.org/v1/species/{key}"
WORKERS = 16

def options_of(normalized: dict) -> list[dict]:
    """Every radio option in an ontology, at whatever nesting depth."""
    found: list[dict] = []

    def walk(nodes):
        for node in nodes:
            for opt in node.get("options") or []:
                found.append(opt)
                walk(opt.get("options") or [])
            walk(node.get("classifications") or [])

    walk((normalized.get("tools") or []) + (normalized.get("classifications") or []))
    return found


def index_options(options: list[dict], normalize, split_codes) -> tuple[dict, dict, list]:
    """``(by_code, by_name, collisions)`` over the options that carry a key.

    A code that two options claim is reported rather than resolved: it would
    make an old label ambiguous, and guessing which option it meant is exactly
    the silent wrong answer this file exists to remove.
    """
    by_code: dict[str, int] = {}
    by_name: dict[str, int] = {}
    collisions = []
    for opt in options:
        value = (opt.get("value") or "").strip()
        if not value.isdigit():
            continue
        key = int(value)
        name, codes = split_codes(opt["label"])
        nn = normalize(name)
        if nn:
            by_name.setdefault(nn, key)
        if not codes:
            continue
        code = codes[0]
        if by_code.setdefault(code, key) != key:
            collisions.append((code, by_code[code], key, opt["label"]))
    return by_code, by_name, collisions


def accepted_keys(keys, session=None) -> dict[str, int]:
    """Each key mapped to its GBIF backbone accepted usage key.

    A synonym key resolves to the accepted one; an accepted key maps to itself.
    Both sides of the join are put through this, so ``Celtis schippii`` held as
    4159734 by the label and under another key by the checklist still meets.
    """
    session = session or requests.Session()

    def one(key):
        r = session.get(GBIF_SPECIES.format(key=key), timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"GBIF {r.status_code} for key {key}")
        doc = r.json()
        return str(key), int(doc.get("acceptedKey") or doc.get("key") or key)

    with ThreadPoolExecutor(WORKERS) as pool:
        return dict(pool.map(one, sorted(keys)))


def legacy_names(path, by_code, by_name, normalize, split_codes) -> tuple[dict, list]:
    """Old label names mapped to the key of the option they were drawn from.

    ``Pochota quinata-POCHQU`` in the tracked boxes file is the option now
    labelled ``Pochota fendleri-POCHQU``: the name moved, the code did not.
    Only names the current ontology has dropped are indexed, so a live option
    is never shadowed by an older reading of the same string.

    A name two codes claim with two different keys is reported, not resolved.
    """
    if not path.exists():
        return {}, []
    by_legacy: dict[str, int] = {}
    collisions = []
    with open(path, newline="", encoding="utf-8") as fh:
        labels = {r["lb_label"] for r in csv.DictReader(fh) if r.get("lb_label")}
    for label in sorted(labels):
        name, codes = split_codes(label)
        if not codes:
            continue
        key = by_code.get(codes[0])
        nn = normalize(name)
        if key is None or not nn or nn in by_name:
            continue
        if by_legacy.setdefault(nn, key) != key:
            collisions.append((nn, by_legacy[nn], key, label))
    return by_legacy, collisions


def checklist_keys(paths) -> set[int]:
    """Every ``gbifId`` on every checklist on disk."""
    keys = set()
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for sp in json.load(fh).get("species", []):
                gid = sp.get("gbifId")
                if gid:
                    keys.add(int(gid))
    return keys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None, help="default: config.yaml labelbox.project_id")
    ap.add_argument("--checklist", action="append", default=None, metavar="PROJECT",
                    help="checklist to resolve keys for, repeatable "
                         "(default: core.EVAL_PROJECT)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "dashboard"))
    from core import EVAL_PROJECT, normalize
    from gbif_keys import split_codes

    projects = args.checklist or [EVAL_PROJECT]
    checklists = [REPO / "data" / f"checklist_{p}.json" for p in projects]
    absent = [p for p in checklists if not p.exists()]
    if absent:
        print(f"no checklist on disk: {', '.join(p.name for p in absent)}. "
              f"Run predict/fetch_checklist.py first.", file=sys.stderr)
        return 1

    project_id = args.project or setting("labelbox", "project_id", env="LABELBOX_PROJECT_ID")
    client = lb.Client(api_key=api_key())
    ontology = client.get_project(project_id).ontology()
    options = options_of(ontology.normalized)
    by_code, by_name, collisions = index_options(options, normalize, split_codes)
    by_legacy, legacy_clash = legacy_names(BOXES, by_code, by_name, normalize, split_codes)
    collisions += legacy_clash
    if collisions:
        for code, first, second, label in collisions:
            print(f"code {code} claimed by keys {first} and {second} ({label})", file=sys.stderr)
        print(f"{len(collisions)} ambiguous collection codes: an old label using one "
              f"cannot be resolved. Fix the ontology, do not guess.", file=sys.stderr)
        return 1

    keys = set(by_code.values()) | set(by_name.values()) | checklist_keys(checklists)
    accepted = accepted_keys(keys)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({
            "ontology_id": ontology.uid,
            "ontology_name": ontology.name,
            "project_id": project_id,
            "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_options": len(options),
            "checklists": [p.name for p in checklists],
            "by_code": by_code,
            "by_name": by_name,
            "by_legacy": by_legacy,
            "accepted": accepted,
        }, fh)

    moved = sum(1 for k, v in accepted.items() if int(k) != v)
    print(f"{ontology.name}: {len(options)} options, {len(by_code)} collection codes, "
          f"{len(by_name)} names, {len(by_legacy)} retired names, {len(accepted)} keys "
          f"resolved ({moved} are synonyms) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
