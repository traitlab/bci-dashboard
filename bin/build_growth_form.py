#!/usr/bin/env python3
"""Regenerate input/growth_form.csv, the growth form of each species in the build.

Reads the WCVP names file (wcvp_names.csv from the Kew bulk download, '|'
separated) and the species of the last build (labelled, plus every species the send queue predicts), and writes one row per species:
tree, liana, palm, shrub or unknown. Palms come from the family Arecaceae;
climbers (liana, climbing, scrambling, vine) are lianas. A lifeform that is
missing, mixed ("shrub or tree") or not listed below is unknown, never guessed.
Lianas and unknowns also go to input/growth_form_review.csv for a botanist.

WCVP: Govaerts R (ed.). World Checklist of Vascular Plants, Royal Botanic
Gardens, Kew, https://doi.org/10.34885/egs6-cp24, CC BY 3.0 per its README.
The bulk file is not committed.

    python bin/build_growth_form.py path/to/wcvp_names.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPECIES_CSV = REPO / "build" / "tables" / "per_species_health.csv"
QUEUE_CSV = REPO / "build" / "tables" / "send_first_queue.csv"
OUT = REPO / "input" / "growth_form.csv"
REVIEW = REPO / "input" / "growth_form_review.csv"
FIELDS = ("species", "growth_form", "source")

CLIMBER = re.compile(r"\b(liana|climber|climbing|vine|scrambling)\b")
EXACT = {"tree": "tree", "shrub": "shrub"}


def growth_form(family: str, lifeform: str) -> str:
    """Palm by family, then climbers, then the exact tree/shrub terms, else unknown."""
    if family == "Arecaceae":
        return "palm"
    lifeform = lifeform.strip().lower()
    if CLIMBER.search(lifeform):
        return "liana"
    return EXACT.get(lifeform, "unknown")


def source(family: str, lifeform: str) -> str:
    wcvp = f"WCVP:{lifeform or '(none)'}"
    return f"family:Arecaceae;{wcvp}" if family == "Arecaceae" else wcvp


def read_wcvp(path: Path, wanted: set[str]) -> dict[str, dict[str, str]]:
    """Accepted species rows for the wanted lowercase binomials, by that binomial."""
    found: dict[str, dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE):
            name = row["taxon_name"].lower()
            if (
                name in wanted
                and row["taxon_status"] == "Accepted"
                and row["taxon_rank"] == "Species"
            ):
                found[name] = row
    return found


def rows_for(
    species: list[str], wcvp: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    out = []
    for name in species:
        rec = wcvp.get(name)
        if rec is None:
            out.append(
                {"species": name, "growth_form": "unknown", "source": "no WCVP match"}
            )
            continue
        family, lifeform = rec["family"], rec["lifeform_description"]
        out.append(
            {
                "species": name,
                "growth_form": growth_form(family, lifeform),
                "source": source(family, lifeform),
            }
        )
    return out


def seed(health: Path, queue: Path | None) -> list[str]:
    """Labelled species first, then queue-predicted ones not already there."""
    names = []
    for path, col in ((health, "species"), (queue, "predicted_species")):
        if path is None:
            continue
        with open(path, newline="", encoding="utf-8") as f:
            names += [r[col] for r in csv.DictReader(f) if r[col]]
    return list(dict.fromkeys(names))


def write(path: Path, rows: list[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("wcvp_names", type=Path)
    ap.add_argument("--species", type=Path, default=SPECIES_CSV)
    ap.add_argument("--queue", type=Path, default=QUEUE_CSV, help="send queue whose predicted species are seeded too")
    ap.add_argument("--no-queue", action="store_true", help="seed from labelled species only")
    args = ap.parse_args(argv)
    species = seed(args.species, None if args.no_queue else args.queue)
    if not species:
        sys.exit(f"no species in {args.species}")
    rows = rows_for(species, read_wcvp(args.wcvp_names, set(species)))
    write(OUT, rows)
    write(REVIEW, [r for r in rows if r["growth_form"] in ("liana", "unknown")])
    for r in rows:
        if r["source"] == "no WCVP match":
            print(f"no WCVP match: {r['species']}", file=sys.stderr)
    counts = {
        g: sum(r["growth_form"] == g for r in rows)
        for g in sorted({r["growth_form"] for r in rows})
    }
    print(f"{len(rows)} species: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
