#!/usr/bin/env python3
"""Pull the species Pl@ntNet can return for a project, so absence stops being a guess.

The dashboard marks a species "never in the five guesses" when its name appears
in none of the cached prediction lists. That is inference from a sample, not a
membership test: we only ever asked for five candidates, so a species the model
carries but has never ranked looks exactly like one it does not carry. Within
the primary evaluation set, 143 names are visible only because rank 5 was
included, which is how far from saturated that sample is.

GET /v2/projects/{project}/species returns the label set itself. It is read in
pages and the pages are concatenated, which is what makes the distinction exact
and permanent instead of proportional to how deep we query. Leaving pageSize
empty asks for the whole list in one response and the server answers 503 on a
project the size of k-world-flora, so paging is the only route that works for
every project.

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

TIMEOUT = 300  # a page of thousands of species is a long response
# Species per request. The route defaults to 100 and accepts far more; 5,000
# reads k-world-flora in 17 requests instead of 847. Not the whole list in one
# request: that is what 503s.
PAGE_SIZE = 5000


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


def fetch_species(api: str, api_key: str, project: str, lang: str = "en",
                  page_size: int = PAGE_SIZE) -> list:
    """The whole label set, read a page at a time and concatenated.

    A short page ends the loop, so the last request is the one that proves the
    list is finished. `main` then checks the total against the count the project
    listing declares, which is what tells a dropped page from a real change in
    the model.
    """
    out, page = [], 1
    while True:
        r = requests.get(
            f"{api}/projects/{project}/species",
            params={"api-key": api_key, "lang": lang,
                    "pageSize": page_size, "page": page},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        got = r.json()
        if not isinstance(got, list):
            raise ValueError(f"expected a species array, got {type(got).__name__}")
        out += got
        if len(got) < page_size:
            return out
        page += 1


def main() -> int:
    """Fetch the species checklist for one Pl@ntNet project and write it down.

    The checklist is what separates a species the model could never name from
    one it names badly, so the pages need it committed rather than fetched.
    """
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
