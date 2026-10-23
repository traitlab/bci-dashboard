"""The WCVP lifeform to growth-form mapping: explicit, and unknown when unsure."""

import csv

import pytest
from conftest import REPO, load

gf = load("_growth_form_under_test", REPO / "bin" / "build_growth_form.py")


@pytest.mark.parametrize(
    "family, lifeform, expected",
    [
        ("Fabaceae", "tree", "tree"),
        ("Fabaceae", "shrub", "shrub"),
        ("Fabaceae", "liana", "liana"),
        ("Fabaceae", "climbing shrub", "liana"),
        ("Fabaceae", "climbing shrub or liana", "liana"),
        ("Rubiaceae", "scrambling shrub or tree", "liana"),
        ("Vitaceae", "vine", "liana"),
        ("Fabaceae", "shrub or tree", "unknown"),
        ("Orchidaceae", "epiphyte", "unknown"),
        ("Fabaceae", "", "unknown"),
        ("Arecaceae", "", "palm"),
        ("Arecaceae", "climbing palm", "palm"),
    ],
)
def test_growth_form(family, lifeform, expected):
    assert gf.growth_form(family, lifeform) == expected


def test_source_keeps_raw_lifeform():
    assert gf.source("Fabaceae", "tree") == "WCVP:tree"
    assert gf.source("Fabaceae", "") == "WCVP:(none)"
    assert gf.source("Arecaceae", "tree") == "family:Arecaceae;WCVP:tree"


def test_unmatched_species_is_unknown():
    rows = gf.rows_for(["a b"], {})
    assert rows == [
        {"species": "a b", "growth_form": "unknown", "source": "no WCVP match"}
    ]


def test_committed_csv_covers_each_species_once():
    path = REPO / "input" / "growth_form.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert tuple(rows[0]) == gf.FIELDS
    names = [r["species"] for r in rows]
    assert len(names) == len(set(names))
    assert {r["growth_form"] for r in rows} <= {
        "tree",
        "liana",
        "palm",
        "shrub",
        "unknown",
    }


def test_seed_adds_queue_predicted_species_once(tmp_path):
    health = tmp_path / "h.csv"
    health.write_text("species\na b\nc d\n")
    queue = tmp_path / "q.csv"
    queue.write_text("predicted_species\nc d\ne f\ne f\n\n")
    assert gf.seed(health, queue) == ["a b", "c d", "e f"]
    assert gf.seed(health, None) == ["a b", "c d"]
