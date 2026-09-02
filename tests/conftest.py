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

import contextlib
import importlib.util
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard"
BOX_CSV = REPO / "input" / "boxes" / "crop_bounding_boxes.csv"
GT_CSV = REPO / "data" / "gt_dominant_taxon.csv"


@contextlib.contextmanager
def _on_path(directory: pathlib.Path):
    """`directory` on `sys.path` for the duration, and off it afterwards.

    The script directories are not packages, so a module there is only
    importable while its own folder is on the path. Leaving it on would let a
    later test import a neighbour by accident.
    """
    entry = str(directory)
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        sys.path.remove(entry)


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


def _require(*packages, who="predict"):
    """Skip rather than fail when a requirements.txt package is absent.

    Named one by one so the skip line says which package is missing, instead of
    reporting the module under test as broken.
    """
    for name in packages:
        pytest.importorskip(name, reason=f"{who} needs {name}")


@pytest.fixture(scope="session")
def ingest():
    _require("PIL", "requests", "yaml", "dotenv")
    return load("_ingest_under_test", REPO / "predict" / "ingest_photos.py")


@pytest.fixture(scope="session")
def crown():
    _require("PIL", "yaml", "dotenv")
    return load("_crown_under_test", REPO / "predict" / "crown.py")


@pytest.fixture(scope="session")
def crown_accuracy():
    """Stdlib only, so no `_require` guard and no fixture-scoped path juggling."""
    return load("_crown_accuracy_under_test", REPO / "predict" / "crown_accuracy.py")


@pytest.fixture(scope="session")
def crop_overlap():
    """`dashboard/` on the path for the duration, and off it afterwards."""
    with _on_path(REPO / "dashboard"):
        import crop_overlap
        yield crop_overlap


@pytest.fixture(scope="session")
def history():
    with _on_path(REPO / "dashboard"):
        import history
        yield history


@pytest.fixture(scope="session")
def assets():
    """The rendering primitives, called directly rather than regexed out of a
    built page. They are pure functions of their arguments, so they need none
    of the measurement inputs `tests/test_pages.py` skips itself without."""
    with _on_path(REPO / "dashboard"):
        import assets
        yield assets


@pytest.fixture(scope="session")
def panels():
    """`dashboard/` on the path, because panels imports core and assets as
    siblings. Only the registry and the section machinery are reachable
    without a snapshot; `prepare` needs the measurement inputs."""
    with _on_path(REPO / "dashboard"):
        import panels
        yield panels


@pytest.fixture(scope="session")
def queue_panels():
    """The internal queue page\'s own panels, split out of `panels` so the two
    audiences do not share a 1,100-line module. Same path dance as `panels`."""
    with _on_path(REPO / "dashboard"):
        import queue_panels
        yield queue_panels


@pytest.fixture(scope="session")
def explain():
    """`dashboard/` on the path, because explain imports `core` and `assets` as
    siblings. `_near_miss`, the band dicts and constants, and the three panel
    functions are all reachable without measurement inputs: every one of them
    is a pure function of its arguments."""
    with _on_path(REPO / "dashboard"):
        import explain
        yield explain


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


@pytest.fixture
def settings(monkeypatch):
    """`labelling/settings.py`, with `.env` disconnected.

    The resolver reads `.env` on every call, so a test that says "the
    environment is silent" has to mean it. Left connected, adding a key to a
    developer's own `.env` would quietly change what the suite asserts.
    """
    _require("yaml", "dotenv", who="labelling")
    module = load("_settings_under_test", REPO / "labelling" / "settings.py")
    monkeypatch.setattr(module, "load_dotenv", lambda *a, **k: None)
    return module


@pytest.fixture(scope="session")
def draw_confirmatory():
    _require("PIL", "yaml", "dotenv")
    return load("_draw_confirmatory_under_test", REPO / "predict" / "draw_confirmatory.py")


@pytest.fixture(scope="session")
def score_confirmatory():
    """`dashboard/` on the path, because the scorer imports `core` as a sibling."""
    with _on_path(REPO / "dashboard"):
        import score_confirmatory
        yield score_confirmatory


# ---------------------------------------------------------------------------
# The built pages. Shared, because more than one file asks what a reader
# meets on a page: `test_pages.py` checks what is on it, and
# `test_plain_english.py` checks that it can be read. Building is a real
# subprocess and session-scoped, so it happens once per run either way.
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = REPO / "snapshots" / "model-health-2026-08-24"
SPLITS_CSV = REPO / "data" / "splits.csv"
CACHE_DIR = REPO / "data" / "predictions" / "cache"

# A fixed generation string, like the worktree byte-diff checks use: real
# dates would make two builds of the same code differ for no reason a test
# should care about.
GENERATED = "2026-08-25-test"

# What each page is expected to carry, so a test states its expectation once
# and every page is checked against the same list. `species` is the sortable,
# filterable species table with its status legend, which is also what the
# inline JS binds to. The send queue splits in two: `queue_counts` is the
# how-many-per-queue breakdown and `queue_keys` is the frame-by-frame
# send-first list with the camera note beside it. `snapshot` marks a page that
# reconciles against `snapshots/model-health-2026-08-24` at build time and so
# must print a `verified` line for every check it ran; the export page has no
# such snapshot -- it is scoped to one Labelbox export -- so it carries none.
#
# `species_status` is narrower than `species`: it is the per-row
# `data-species`/`data-status` attributes plus the status legend that
# `panels.p_species` renders. All three pages carry it. `build_export_only.py`
# used to build its own species table straight off `assets.filterable_table`
# with no `row_attrs`, so a row said 40% and nothing said whether that was a
# species the model gets wrong or one with too few labels to judge; it now
# renders the same status column and legend as the other two.
#
# `species_thin` is narrower again: the show-all checkbox that `p_species`
# renders over rows with fewer than `panels.THIN_MIN_FRAMES` labelled frames.
# Only the model-health page hides rows that way; the export page shows every
# species it labelled, however few frames each has.
#
# Each flag now names exactly one page, so a flag no longer distinguishes
# between pages the way it did while a third page carried `species` and
# `queue_counts` together. The flags stay because they say what a page is
# expected to carry, which is the claim the assertions need.
PAGES = {
    "external_page": ("build_external.py", "model_health_dashboard.html",
                      {"species", "species_status", "species_thin",
                       "confirmatory", "snapshot"}),
    "internal_page": ("build_internal.py", "label_queue_dashboard.html",
                      {"queue_counts", "queue_keys", "snapshot"}),
    "export_only_page": ("build_export_only.py", "export_only_dashboard.html",
                         {"species", "species_status"}),
}


def require_buildable():
    """Skip on a fresh clone: the builders need measurement inputs and a
    snapshot to verify against, neither of which is tracked in git."""
    for path, label in ((GT_CSV, "data/gt_dominant_taxon.csv"),
                        (SPLITS_CSV, "data/splits.csv"),
                        (CACHE_DIR, "data/predictions/cache")):
        if not path.exists():
            pytest.skip(f"{label} not present (fresh clone)")
    if not SNAPSHOT_DIR.exists():
        pytest.skip("snapshots/model-health-2026-08-24 not present (fresh clone)")


def build_page(tmp_path_factory, script: str, out_name: str, *,
               export: str | None = None) -> tuple[str, str]:
    """Run a builder as a real subprocess, the way `bin/refresh.sh` does.

    Returns (page_html, stdout). Raises via `assert` on a non-zero exit so
    the failure message carries the process's own stderr (a `VERIFY FAIL:
    ...` line from `history.verify_snapshot`, or a traceback).

    `build_export_only.py` takes `--export` and no `--verify-against` -- it
    has no snapshot to reconcile against -- so `export` switches which flags
    get built rather than duplicating the subprocess call for one page.
    """
    out = tmp_path_factory.mktemp("page") / out_name
    args = [sys.executable, str(DASHBOARD / script), "--out", str(out),
            "--generated", GENERATED]
    args += ["--export", export] if export is not None else (
        ["--verify-against", str(SNAPSHOT_DIR)])
    proc = subprocess.run(args, capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, (
        f"{script} exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return out.read_text(encoding="utf-8"), proc.stdout


# Same convention as core.GT_KEY_PREFIX / gt_from_export.GT_KEY_PREFIX: a GT or
# splits global_key is "comb_<stem>.JPG", a cache file is "<stem>.JPG.json".
GT_KEY_PREFIX = "comb_"

def corpus_keys_with_species_gt():
    """Every corpus global_key that also carries a species label in
    gt_dominant_taxon.csv, split by whether the cache holds a prediction for
    it, plus the GT map itself. All three come straight off disk."""
    import csv
    with open(GT_CSV, newline="", encoding="utf-8") as f:
        gt = {r["global_key"]: r["wcvp_canonical_name"] for r in csv.DictReader(f)}
    with open(SPLITS_CSV, newline="", encoding="utf-8") as f:
        corpus = {r["global_key"] for r in csv.DictReader(f)}
    cached = {p.stem for p in CACHE_DIR.glob("*.json")}
    labelled = sorted(gk for gk in corpus if gk in gt)
    with_cache = [gk for gk in labelled if gk[len(GT_KEY_PREFIX):] in cached]
    without_cache = [gk for gk in labelled if gk[len(GT_KEY_PREFIX):] not in cached]
    return with_cache, without_cache, gt


def write_export_ndjson(path, keys, gt) -> None:
    """Emit NDJSON in the shape `gt_from_export.export_dominants` parses: one
    data row per key, one project with one label carrying a single
    full-frame Planta box whose Taxon radio answer is that key's own GT
    species.

    This fabricates no data and asserts nothing about Labelbox: every key and
    species comes from the repo's own tracked data/gt_dominant_taxon.csv and
    data/splits.csv, and the file exists only for the duration of the test.
    """
    import json
    with open(path, "w", encoding="utf-8") as f:
        for i, gk in enumerate(keys):
            stem = gk[len(GT_KEY_PREFIX):]
            row = {
                "data_row": {"id": f"dr_{i}", "global_key": stem},
                "projects": {"proj1": {"labels": [{"annotations": {"objects": [{
                    "bounding_box": {"top": 0, "left": 0, "width": 100, "height": 100},
                    "classifications": [{"radio_answer": {"name": gt[gk]}}],
                }]}}]}},
            }
            f.write(json.dumps(row) + "\n")


@pytest.fixture(scope="session")
def export_fixture(tmp_path_factory):
    """A deterministic slice of 48 real, cache-backed keys and the NDJSON
    file built from them, shared by every test below that needs a scored
    export page."""
    require_buildable()
    with_cache, _, gt = corpus_keys_with_species_gt()
    keys = with_cache[:48]
    path = tmp_path_factory.mktemp("export") / "export.ndjson"
    write_export_ndjson(path, keys, gt)
    return path, keys, gt


@pytest.fixture(scope="session")
def export_only_page(tmp_path_factory, export_fixture):
    require_buildable()
    path, _, _ = export_fixture
    return build_page(tmp_path_factory, *PAGES["export_only_page"][:2], export=str(path))


@pytest.fixture(scope="session")
def external_page(tmp_path_factory):
    require_buildable()
    return build_page(tmp_path_factory, *PAGES["external_page"][:2])


@pytest.fixture(scope="session")
def internal_page(tmp_path_factory):
    require_buildable()
    return build_page(tmp_path_factory, *PAGES["internal_page"][:2])
