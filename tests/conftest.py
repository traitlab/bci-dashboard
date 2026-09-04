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
import io
import pathlib
import re
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


@pytest.fixture(scope="session")
def queues():
    """The send-first queue policy. Imported with `dashboard/` on the path,
    since it reads its thresholds from core as a sibling."""
    with _on_path(REPO / "dashboard"):
        import queues
        yield queues


@pytest.fixture(scope="session")
def health():
    """`health`, the load-and-join layer. On the path rather than loaded by
    path like `core`, because it imports core as a sibling."""
    with _on_path(REPO / "dashboard"):
        import health
        yield health


def _require(*packages, who="predict"):
    """Skip rather than fail when a requirements.txt package is absent.

    Named one by one so the skip line says which package is missing, instead of
    reporting the module under test as broken.
    """
    for name in packages:
        pytest.importorskip(name, reason=f"{who} needs {name}")


@pytest.fixture
def jpeg():
    """A solid JPEG of a given size, as bytes. Two files ask a fetch path what
    it did with a frame, and they have to hand it the same kind of frame."""
    Image = pytest.importorskip("PIL.Image", reason="predict needs PIL")

    def make(w, h):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (11, 99, 33)).save(buf, format="JPEG")
        return buf.getvalue()

    return make


@pytest.fixture(scope="session")
def ingest():
    """Imported with `predict/` on the path: it takes the crop, the quota
    error and config loading from photo.py as a sibling, the way the script
    does when it is run."""
    _require("PIL", "requests", "yaml", "dotenv")
    with _on_path(REPO / "predict"):
        yield load("_ingest_under_test", REPO / "predict" / "ingest_photos.py")


@pytest.fixture(scope="session")
def embed():
    """Imported the way the script runs it, with photo.py as a sibling: the
    post, the retry and the crop all come from there."""
    _require("numpy", "requests", "yaml", "dotenv", "PIL")
    with _on_path(REPO / "predict"):
        yield load("_embed_under_test", REPO / "predict" / "embed.py")


@pytest.fixture(scope="session")
def checklist():
    """Imported with photo.py as a sibling: the project id comes from config."""
    _require("requests", "yaml", "dotenv", "PIL")
    with _on_path(REPO / "predict"):
        yield load("_checklist_under_test", REPO / "predict" / "fetch_checklist.py")


@pytest.fixture(scope="session")
def photo():
    _require("PIL", "requests", "yaml", "dotenv")
    return load("_photo_under_test", REPO / "predict" / "photo.py")


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
def dashboard_checklist():
    """`dashboard/checklist.py`, stdlib only. Named apart from the `checklist`
    fixture above, which loads `predict/fetch_checklist.py`, the fetch script
    this module reads the output of rather than the module itself."""
    with _on_path(REPO / "dashboard"):
        import checklist
        yield checklist


@pytest.fixture(scope="session")
def assets():
    """The rendering primitives, called directly rather than regexed out of a
    built page. They are pure functions of their arguments, so they need none
    of the measurement inputs `tests/test_pages.py` skips itself without."""
    with _on_path(REPO / "dashboard"):
        import assets
        yield assets


@pytest.fixture(scope="session")
def style():
    """The stylesheet, the script and the element ids they share with
    `assets.filterable_table`. Separate from `assets` because they are literal
    text a test greps, not functions it calls."""
    with _on_path(REPO / "dashboard"):
        import style
        yield style


@pytest.fixture(scope="session")
def confirmatory_panels():
    """The frozen experiment's two panels, and the two amendments they quote
    verbatim. Its own fixture because the quotes are what several tests need,
    and they are literals a test can read without a snapshot."""
    with _on_path(REPO / "dashboard"):
        import confirmatory_panels
        yield confirmatory_panels


@pytest.fixture(scope="session")
def measure():
    """The measurement pass, for its module constants. Imported with
    `dashboard/` on the path, since it imports core and health as siblings."""
    with _on_path(REPO / "dashboard"):
        import measure
        yield measure


@pytest.fixture(scope="session")
def run_log():
    """The prose `measure.py` writes to run_log.txt. Pure formatting over the
    numbers it is handed, so it needs no measurement inputs of its own."""
    with _on_path(REPO / "dashboard"):
        import run_log
        yield run_log


@pytest.fixture(scope="session")
def figures():
    """The prepared context both pages render from. Its private helpers are
    pure functions of the records passed in, so they are reachable without a
    snapshot even though `prepare` is not."""
    with _on_path(REPO / "dashboard"):
        import figures
        yield figures


@pytest.fixture(scope="session")
def status_words():
    """The status vocabulary all three pages share. Module constants only, so
    no snapshot is needed to read it."""
    with _on_path(REPO / "dashboard"):
        import status_words
        yield status_words


@pytest.fixture(scope="session")
def panels():
    """The model-health page's panel functions. `dashboard/` on the path,
    because panels imports core and assets as siblings. Every function here
    needs a figure namespace, so a test without a snapshot can only read the
    module constants."""
    with _on_path(REPO / "dashboard"):
        import panels
        yield panels


@pytest.fixture(scope="session")
def pagemod():
    """`page`, which holds the panel registry, the section layout and the
    builder plumbing. Named `pagemod` because `page` is already the built HTML
    in `test_pages.py`. Reachable without a snapshot, unlike the panels it
    registers."""
    with _on_path(REPO / "dashboard"):
        import page
        yield page


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
def dispatch_round():
    """`labelling/dispatch_round.py`, loaded for its pure helpers.

    Nothing here calls Labelbox: the fixture exists so the batch-to-priority
    mapping is testable without a client, a key, or a project.
    """
    _require("labelbox", "yaml", "dotenv", who="labelling")
    with _on_path(REPO / "labelling"):
        return load("_dispatch_round_under_test", REPO / "labelling" / "dispatch_round.py")


@pytest.fixture(scope="session")
def fetch_dataset():
    """`labelling/fetch_dataset.py`, loaded for the checks that run before it
    reaches Labelbox. Nothing here builds a client or needs a key."""
    _require("labelbox", "yaml", "dotenv", who="labelling")
    with _on_path(REPO / "labelling"):
        return load("_fetch_dataset_under_test", REPO / "labelling" / "fetch_dataset.py")


@pytest.fixture(scope="session")
def rounds():
    """`labelling/rounds.py`, the batch-name and metadata convention. Stdlib
    only, so it loads with no Labelbox and no key."""
    return load("_rounds_under_test", REPO / "labelling" / "rounds.py")


@pytest.fixture(scope="session")
def close_round():
    """`labelling/close_round.py`, loaded for the helpers that find a round.

    Nothing here reaches Labelbox: `find_batch` and `near_misses` are given a
    stand-in project that only has to list batch names.
    """
    _require("labelbox", "yaml", "dotenv", who="labelling")
    with _on_path(REPO / "labelling"):
        return load("_close_round_under_test", REPO / "labelling" / "close_round.py")


@pytest.fixture(scope="session")
def verify_round():
    """`labelling/verify_round.py`, loaded for its three checks.

    Each check reads exported rows as plain dicts, so the whole verifier is
    testable without a project, a batch, or a key.
    """
    _require("labelbox", "yaml", "dotenv", who="labelling")
    with _on_path(REPO / "labelling"):
        return load("_verify_round_under_test", REPO / "labelling" / "verify_round.py")


@pytest.fixture(scope="session")
def draw_confirmatory():
    _require("PIL", "yaml", "dotenv")
    return load("_draw_confirmatory_under_test", REPO / "predict" / "draw_confirmatory.py")


@pytest.fixture(scope="session")
def draw_field_sample():
    """`labelling/draw_field_sample.py`. Stdlib only, and it reaches nothing live.

    It imports the confirmatory draw for the shared allocation, which is stdlib
    at import time even though that script's own fixture needs Pillow for the
    pool it derives.
    """
    return load("_draw_field_sample_under_test",
                REPO / "labelling" / "draw_field_sample.py")


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

# The gate is `core.TABLES_DIR`, what the builders themselves default to, so
# the suite asks for it rather than naming a path. Naming one silently ages:
# this once pinned a snapshot date and sat on 2026-08-24 while the builders
# had moved on to 2026-08-27, so three snapshots' worth of numbers were never
# checked by a test. A dated snapshot is the wrong gate for a different
# reason: it is a record of one day, so it goes stale the moment the code
# that writes a table changes, and the suite would be checking today's page
# against what the code did then.
# A fresh clone has never run measure.py, so this directory can be missing;
# `require_buildable` is what turns that into a skip, so this only has to
# name a path it can print.
with _on_path(REPO / "dashboard"):
    import core as _core
    SNAPSHOT_DIR = pathlib.Path(_core.TABLES_DIR)
SPLITS_CSV = REPO / "data" / "splits.csv"
CACHE_DIR = REPO / "data" / "predictions" / "cache"
# labelling/rank_queue.py writes this one, outside bin/refresh.sh and in its
# own virtualenv, so a checkout can have every other input and still not have
# it. build_internal.py refuses to build without it rather than describe an
# ordering it is not using, which is a skip here and not a failure.
QUEUE_NOVELTY_CSV = pathlib.Path(_core.QUEUE_NOVELTY_CSV)

# A fixed generation string, like the worktree byte-diff checks use: real
# dates would make two builds of the same code differ for no reason a test
# should care about.
GENERATED = "2026-08-25-test"

# What each page is expected to carry, so a test states its expectation once
# and every page is checked against the same list. `species` is the sortable,
# filterable species table with its status legend, which is also what the
# inline JS binds to. `species_status` is the per-row status tag and legend
# `panels.p_species` renders; `species_thin` is its show-all checkbox over
# species with fewer than `panels.THIN_MIN_FRAMES` labelled frames. The send
# queue splits in two: `queue_counts` is the how-many-per-queue breakdown and
# `queue_keys` the frame-by-frame send-first list. `snapshot` marks a page
# that reconciles against `build/tables` at build time and so must print a
# `verified` line for every check it ran.
#
# Each flag names exactly one page. They stay because they say what a page is
# expected to carry, which is the claim the assertions need.
# A species row is a row carrying a status tag. The rows used to be found by a
# `data-status` attribute that repeated on every row what the tag already says;
# the page dropped it, so the tests look for the tag itself.
_ANY_ROW = re.compile(r"<tr\b[^>]*>.*?</tr>", re.S)


def species_rows(html: str) -> list[str]:
    """Every row of the species table, tags and all."""
    return [row for row in _ANY_ROW.findall(html) if '<span class="tag ' in row]


PAGES = {
    "external_page": ("build_external.py", "model_health_dashboard.html",
                      {"species", "species_status", "species_thin",
                       "floor", "snapshot"}),
    "internal_page": ("build_internal.py", "label_queue_dashboard.html",
                      {"queue_counts", "queue_keys", "snapshot"}),
}


def require_buildable():
    """Skip on a fresh clone: the builders need measurement inputs and the
    tables to verify against, neither of which is tracked in git. Run
    `dashboard/measure.py` to make the tables."""
    for path, label in ((GT_CSV, "data/gt_dominant_taxon.csv"),
                        (SPLITS_CSV, "data/splits.csv"),
                        (CACHE_DIR, "data/predictions/cache"),
                        (QUEUE_NOVELTY_CSV,
                         "data/next_batch/queue_novelty.csv")):
        if not path.exists():
            pytest.skip(f"{label} not present (fresh clone)")
    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"{SNAPSHOT_DIR} not present (fresh clone)")


def build_page(tmp_path_factory, script: str, out_name: str) -> tuple[str, str]:
    """Run a builder as a real subprocess, the way `bin/refresh.sh` does.

    Returns (page_html, stdout). Raises via `assert` on a non-zero exit so
    the failure message carries the process's own stderr (a `VERIFY FAIL:
    ...` line from `history.verify_snapshot`, or a traceback).
    """
    out = tmp_path_factory.mktemp("page") / out_name
    args = [sys.executable, str(DASHBOARD / script), "--out", str(out),
            "--generated", GENERATED,
            "--verify-against", str(SNAPSHOT_DIR)]
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


@pytest.fixture(scope="session")
def external_page(tmp_path_factory):
    require_buildable()
    return build_page(tmp_path_factory, *PAGES["external_page"][:2])


@pytest.fixture(scope="session")
def internal_page(tmp_path_factory):
    require_buildable()
    return build_page(tmp_path_factory, *PAGES["internal_page"][:2])


@pytest.fixture(params=sorted(PAGES))
def page(request):
    """Every shared page assertion against all three pages, written once.

    Yields ``(html, stdout, panels-this-page-carries)``. Here rather than in
    one test file because `test_pages.py` and `test_page_navigation.py` both
    run against all three, and a second copy of the parametrisation is how one
    file quietly stops covering a page.
    """
    html, stdout = request.getfixturevalue(request.param)
    return html, stdout, PAGES[request.param][2]
