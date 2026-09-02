#!/usr/bin/env python3
"""Pull the species Pl@ntNet can return for a project, so absence stops being a guess.

The dashboard marks a species "never in the five guesses" when its name appears
in none of the cached prediction lists. That is inference from a sample, not a
membership test: we only ever asked for five candidates, so a species the model
carries but has never ranked looks exactly like one it does not carry. Within
the primary evaluation set, 143 names are visible only because rank 5 was
included, which is how far from saturated that sample is.

GET /v2/projects/{project}/species returns the label set itself. With pageSize
and page left empty the response is the complete list, which is what makes the
distinction exact and permanent instead of proportional to how deep we query.

Writes data/checklist_<project>.json: the raw species array plus the
speciesCount the project listing reports, so a later run can tell a truncated
download from a real change in the model.

    python3 predict/fetch_checklist.py [--project <id>]

Needs PLANTNET_API_KEY in .env. /v2/projects is documented as unlimited; the
species route's quota category is not documented, so this asks once and caches.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from photo import api_and_project

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data"

TIMEOUT = 300  # the unpaginated list is documented as a long response


def project_species_count(api: str, api_key: str, project: str):
    """speciesCount for `project`, or None if the listing does not carry it.

    Read separately from the species array so a short download is detectable:
    the array itself has no envelope and no total, so its own length cannot
    confirm that it is complete.
    """
    r = requests.get(f"{api}/projects", params={"api-key": api_key}, timeout=60)
    r.raise_for_status()
    for p in r.json():
        if p.get("id") == project:
            return p.get("speciesCount")
    return None


def fetch_species(api: str, api_key: str, project: str, lang: str = "en") -> list:
    """The whole label set in one call.

    pageSize and page are sent empty on purpose: the API paginates at 100 by
    default, and an empty value is the documented way to switch that off.
    """
    r = requests.get(
        f"{api}/projects/{project}/species",
        params={"api-key": api_key, "lang": lang, "pageSize": "", "page": ""},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None,
                    help="default: the project config.yaml's identify_url points at")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    try:
        api, configured = api_and_project()
    except ValueError as bad:
        sys.exit(str(bad))
    project = args.project or configured

    load_dotenv(REPO / ".env")
    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        print("PLANTNET_API_KEY is not set (put it in .env)", file=sys.stderr)
        return 2

    declared = project_species_count(api, api_key, project)
    species = fetch_species(api, api_key, project, args.lang)
    if not isinstance(species, list) or not species:
        print(f"no species returned for {project}", file=sys.stderr)
        return 1

    if declared is not None and len(species) != declared:
        print(f"WARNING: got {len(species)} species, project listing declares "
              f"{declared}. Treat the list as incomplete.", file=sys.stderr)

    out = args.out or OUT / f"checklist_{project}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"project": project, "lang": args.lang,
                   "declared_species_count": declared,
                   "n_returned": len(species), "species": species}, fh)

    print(f"{project}: {len(species)} species "
          f"(listing declares {declared}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
