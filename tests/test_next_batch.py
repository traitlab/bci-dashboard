"""Which rows `labelling/next_batch.py` counts as unsent.

An inventory that carries `projects` (fetched with a key that may export) is
the authority: a row in any project is sent. Without it the one project export
on disk is all there is, and a row only it misses is counted unsent.
"""

from __future__ import annotations

import pytest
from conftest import REPO, _on_path, _require, load


@pytest.fixture(scope="module")
def next_batch():
    _require("yaml", "dotenv", who="labelling")
    with _on_path(REPO / "labelling"):
        return load("_next_batch_under_test", REPO / "labelling" / "next_batch.py")


def row(key, **extra):
    return {"global_key": key, **extra}


def test_catalog_membership_beats_the_project_export(next_batch):
    rows = [row("a.JPG", projects=[]), row("b.JPG", projects=["sibling"]),
            row("c.JPG", projects=["this"])]
    in_project = {"c.JPG": {"workflow_status": "DONE"}}
    got = next_batch.reconcile(rows, in_project, lambda *_: None)
    assert [r["global_key"] for r in got] == ["a.JPG"]


def test_without_membership_the_export_decides(next_batch):
    rows = [row("a.JPG"), row("b.JPG"), row("c.JPG")]
    in_project = {"c.JPG": {"workflow_status": "DONE"}}
    got = next_batch.reconcile(rows, in_project, lambda *_: None)
    assert [r["global_key"] for r in got] == ["a.JPG", "b.JPG"]
