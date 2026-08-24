"""Shared loading for the tests that import a module by file path.

`dashboard/`, `predict/` and `labelling/` are script directories rather than
importable packages, so a test loads its subject from the path. `core.py` also
carries a `@dataclass`, which needs the module registered in `sys.modules`
before the decorator runs.

Each subject is a fixture rather than a module-level import. A subject that
needs a package from `requirements.txt` skips only the tests that ask for it,
and the skip is reported by name because `addopts` carries `-ra`.

    .venv/bin/pytest
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
BOX_CSV = REPO / "input" / "boxes" / "crop_bounding_boxes.csv"
GT_CSV = REPO / "data" / "gt_dominant_taxon.csv"


def load(name: str, path: pathlib.Path):
    """Import a module from its path under a name that cannot collide."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def core():
    return load("_core_under_test", REPO / "dashboard" / "core.py")


def _require(*packages):
    """Skip rather than fail when a requirements.txt package is absent.

    Named one by one so the skip line says which package is missing, instead of
    reporting the module under test as broken.
    """
    for name in packages:
        pytest.importorskip(name, reason=f"predict needs {name}")


@pytest.fixture(scope="session")
def ingest():
    _require("PIL", "requests", "yaml", "dotenv")
    return load("_ingest_under_test", REPO / "predict" / "ingest_photos.py")


@pytest.fixture(scope="session")
def crown():
    _require("PIL", "yaml", "dotenv")
    return load("_crown_under_test", REPO / "predict" / "crown.py")


@pytest.fixture(scope="session")
def crop_overlap():
    """`dashboard/` on the path for the duration, and off it afterwards."""
    path = str(REPO / "dashboard")
    sys.path.insert(0, path)
    try:
        import crop_overlap
        yield crop_overlap
    finally:
        sys.path.remove(path)


@pytest.fixture(scope="session")
def box_csv():
    if not BOX_CSV.exists():
        pytest.skip("input/boxes/crop_bounding_boxes.csv not present")
    return BOX_CSV


@pytest.fixture(scope="session")
def gt_csv():
    if not GT_CSV.exists():
        pytest.skip("data/gt_dominant_taxon.csv not present")
    return GT_CSV
