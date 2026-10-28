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
PUBLICATION_GT_CSV = REPO / "data" / "gt_publication_reviewed.csv"


def pytest_addoption(parser):
    parser.addoption("--private-data", action="store_true",
                     help="also check the real local snapshot; missing inputs are an error")


def _private_required_inputs():
    """The real inputs used by the separately selected corpus assertions."""
    required = [GT_CSV, PUBLICATION_GT_CSV, SPLITS_CSV, CACHE_DIR,
                REPO / "data" / "wcvp_cache.json",
                QUEUE_NOVELTY_CSV, SNAPSHOT_DIR / "per_species_health.csv",
                SNAPSHOT_DIR / "send_first_queue.csv",
                SNAPSHOT_DIR / "label_review_queue.csv",
                SNAPSHOT_DIR / "confidence_calibration.csv",
                REPO / "data" / "dataset_rows_combined.jsonl",
                REPO / "data" / "checklist_bcnm.json",
                REPO / "data" / "checklist_k-central-america.json",
                REPO / "data" / "gbif_keys.json",
                REPO / "data" / "predictions_bcnm" / "cache",
                REPO / "snapshots" / "model-health-2026-08-24" / "per_species_health.csv",
                REPO.parent / "bci-dashboard-docs" / "metrics.md",
                REPO.parent / "bci-dashboard-docs" / "hypothesis.md"]
    required.extend(REPO / "data" / "model_health" / name for name in
                    ("transductive.json", "disagreement.json", "reject_sweep.json", "status.json"))
    return required


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config, items):
    # Real-corpus assertions keep their independent expectations. Public page
    # contracts use public_snapshot instead, never the developer's data/.
    private_fixtures = {"page", "external_page", "internal_page", "corpus", "gt_csv",
                        "page_prose", "public_page"}
    private_tests = {
        "test_a_sidecar_on_disk_matches_what_the_reader_expects",
        "test_the_checklist_note_counts_the_names_rank_five_alone_brings_in",
        "test_the_low_confidence_note_states_what_the_calibration_table_measured",
        "test_the_split_is_not_blocked_by_site_so_the_caveat_still_applies",
        "test_every_held_out_frame_sits_at_a_site_the_rule_also_learned_from",
        "test_the_headline_rates_metrics_md_quotes_are_the_ones_the_snapshot_holds",
        "test_membership_needs_the_crosswalk_not_normalize_alone",
        "test_the_measured_absent_species_are_absent_by_name_and_by_key",
        "test_a_renamed_option_is_found_by_its_key_not_its_name",
        "test_species_the_corpus_never_returned_are_not_all_out_of_scope",
    }
    for item in items:
        if private_fixtures.intersection(item.fixturenames) or item.name in private_tests:
            item.add_marker(pytest.mark.private_data)
    # Let pytest apply the actual -m and -k expressions before deciding
    # whether a private item was requested. Negation and mixed expressions
    # retain pytest's own semantics rather than a second expression parser.
    yield
    private = [item for item in items if item.get_closest_marker("private_data")]
    if config.getoption("--private-data"):
        missing = [str(path) for path in _private_required_inputs() if not path.exists()]
        if private and missing:
            raise pytest.UsageError("--private-data requires the real local inputs, missing: "
                                    + ", ".join(missing))
        return
    if private and config.option.markexpr:
        raise pytest.UsageError("selecting private_data checks requires --private-data and the real local inputs")
    items[:] = [item for item in items if not item.get_closest_marker("private_data")]
    config.hook.pytest_deselected(items=private)


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
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
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
def assessments():
    """The stdlib reader for what `labelling/assess_species.py` wrote. On the
    path because it reads its floor from core as a sibling."""
    with _on_path(REPO / "dashboard"):
        import assessments
        yield assessments


@pytest.fixture(scope="session")
def assess_panels():
    """The fragments the model-health page renders off the assessments."""
    with _on_path(REPO / "dashboard"):
        import assess_panels
        yield assess_panels


@pytest.fixture(scope="session")
def history():
    with _on_path(REPO / "dashboard"):
        import history
        yield history


@pytest.fixture(scope="session")
def dashboard_gbif_keys():
    """`dashboard/gbif_keys.py`, stdlib only: the offline read of the GBIF key
    behind a Labelbox option label."""
    with _on_path(REPO / "dashboard"):
        import gbif_keys
        yield gbif_keys


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
def selection_panels():
    """The queue page's measured selection evidence: two JSON sidecars from
    labelling/rank_queue.py, read here with the standard library."""
    with _on_path(REPO / "dashboard"):
        import selection_panels
        yield selection_panels


@pytest.fixture(scope="session")
def queue_panels():
    """The internal queue page\'s own panels, split out of `panels` so the two
    audiences do not share a 1,100-line module. Same path dance as `panels`."""
    with _on_path(REPO / "dashboard"):
        import queue_panels
        yield queue_panels


@pytest.fixture(scope="session")
def queue_filters():
    """The queue page's filter-and-download block."""
    with _on_path(REPO / "dashboard"):
        import queue_filters
        yield queue_filters


@pytest.fixture(scope="session")
def queue_why_panels():
    """The queue page's second part, the closed panels that argue for the
    order, split out of `queue_panels` when the page put them last."""
    with _on_path(REPO / "dashboard"):
        import queue_why_panels
        yield queue_why_panels


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
def record_sends():
    """`labelling/record_sends.py`: reads an export file and writes a ledger, no client."""
    _require("labelbox", "yaml", "dotenv", who="labelling")
    with _on_path(REPO / "labelling"):
        return load("_record_sends_under_test", REPO / "labelling" / "record_sends.py")


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
# A species row is a row carrying a status tag.
_ANY_ROW = re.compile(r"<tr\b[^>]*>.*?</tr>", re.DOTALL)


def species_rows(html: str) -> list[str]:
    """Every row of the species table, tags and all."""
    return [row for row in _ANY_ROW.findall(html) if '<span class="tag ' in row]


# fixture name -> (builder, filename, panels it verifies, extra builder flags).
# One queue page: the labelling team's commands are a closed block on it, and
# the retired team address is a redirect the builder writes beside it, not a page.
PAGES = {
    "external_page": ("build_external.py", "model_health_dashboard.html",
                      {"species", "species_status", "species_thin",
                       "floor", "snapshot"}, ()),
    "internal_page": ("build_internal.py", "label_queue_dashboard.html",
                      {"queue_counts", "queue_keys", "snapshot"}, ()),
}


def require_buildable():
    """Skip on a fresh clone: the builders need measurement inputs and the
    tables to verify against, neither of which is tracked in git. Run
    `dashboard/measure.py` to make the tables."""
    for path, label in ((GT_CSV, "data/gt_dominant_taxon.csv"),
                        (PUBLICATION_GT_CSV, "data/gt_publication_reviewed.csv"),
                        (SPLITS_CSV, "data/splits.csv"),
                        (CACHE_DIR, "data/predictions/cache"),
                        (QUEUE_NOVELTY_CSV,
                         "data/next_batch/queue_novelty.csv")):
        if not path.exists():
            pytest.skip(f"{label} not present (fresh clone)")
    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"{SNAPSHOT_DIR} not present (fresh clone)")


def build_page(tmp_path_factory, script: str, out_name: str,
               flags: tuple[str, ...] = ()) -> tuple[str, str]:
    """Run a builder as a real subprocess, the way `bin/refresh.sh` does.

    Returns (page_html, stdout). Raises via `assert` on a non-zero exit so
    the failure message carries the process's own stderr (a `VERIFY FAIL:
    ...` line from `history.verify_snapshot`, or a traceback).
    """
    out = tmp_path_factory.mktemp("page") / out_name
    args = [sys.executable, str(DASHBOARD / script), "--out", str(out),
            "--generated", GENERATED,
            "--verify-against", str(SNAPSHOT_DIR), *flags]
    proc = subprocess.run(args, capture_output=True, text=True, cwd=REPO, check=False)
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
    name, out, _panels, flags = PAGES["external_page"]
    return build_page(tmp_path_factory, name, out, flags)


@pytest.fixture(scope="session")
def internal_page(tmp_path_factory):
    require_buildable()
    name, out, _panels, flags = PAGES["internal_page"]
    return build_page(tmp_path_factory, name, out, flags)


@pytest.fixture(params=sorted(PAGES))
def page(request):
    """Every shared page assertion against both pages, written once.

    Yields ``(html, stdout, panels-this-page-carries)``. Here rather than in
    one test file because `test_pages.py` and `test_page_navigation.py` both
    run against both, and a second copy of the parametrisation is how one
    file quietly stops covering a page.
    """
    html, stdout = request.getfixturevalue(request.param)
    return html, stdout, PAGES[request.param][2]


@pytest.fixture(scope="session")
def catalog_batches():
    """`labelling/catalog_batches.py`, loaded for `build` and `summary`. It puts
    `dashboard/` on the path itself and reads no Labelbox, key or network."""
    return load("_catalog_batches_under_test", REPO / "labelling" / "catalog_batches.py")
