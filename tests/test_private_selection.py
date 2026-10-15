"""Exercise pytest's actual collection and marker expression handling."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import conftest
import pytest

PRIVATE_NODES = (
    "tests/test_assessments.py::test_a_sidecar_on_disk_matches_what_the_reader_expects",
    "tests/test_plain_english.py::test_most_of_each_page_is_in_short_sentences[external_prose]",
    "tests/test_plain_english.py::test_no_public_page_backticks_something_a_reader_cannot_open[external_page]",
    "tests/test_pages.py::test_one_species_row_per_scored_species[external_page]",
)
PUBLIC_NODE = "tests/test_public_pages.py::test_measurement_matches_independent_observation_counts"

COLLECT = """
import json
from pathlib import Path
import sys
import pytest

class CollectionInputs:
    def pytest_configure(self, config):
        # Collection-only probe: substitute only the prerequisite inventory.
        # No private test body runs and no private input is read or fabricated.
        import conftest
        conftest._private_required_inputs = lambda: [Path(p) for p in json.loads(sys.argv[2])]

    def pytest_collection_finish(self, session):
        print('SELECTED_NODEIDS=' + json.dumps([item.nodeid for item in session.items]))

raise SystemExit(pytest.main(json.loads(sys.argv[1]), plugins=[CollectionInputs()]))
"""


def collect(
    *args: str, required: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    env = dict(
        os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1"
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            COLLECT,
            json.dumps(["--collect-only", "-q", *args]),
            json.dumps(required),
        ],
        cwd=conftest.REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "expression", ["not private_data", "not private_data and not unknown"]
)
def test_excluding_private_checks_needs_no_flag(expression):
    proc = collect("-m", expression, PUBLIC_NODE, *PRIVATE_NODES)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELECTED_NODEIDS=" + json.dumps([PUBLIC_NODE]) in proc.stdout


@pytest.mark.parametrize("expression", ["private_data", "private_data or unknown"])
def test_matching_private_checks_requires_explicit_flag(expression):
    proc = collect("-m", expression, *PRIVATE_NODES)
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "requires --private-data" in proc.stderr


def test_explicit_private_selection_retains_dynamic_and_sidecar_checks():
    proc = collect("--private-data", "-m", "private_data", PUBLIC_NODE, *PRIVATE_NODES)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELECTED_NODEIDS=" + json.dumps(list(PRIVATE_NODES)) in proc.stdout


def test_default_public_selection_omits_actual_snapshot_checks():
    proc = collect(PUBLIC_NODE, *PRIVATE_NODES)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELECTED_NODEIDS=" + json.dumps([PUBLIC_NODE]) in proc.stdout


def test_private_prerequisites_include_the_actual_crosswalk():
    assert (
        conftest.REPO / "data" / "wcvp_cache.json"
        in conftest._private_required_inputs()
    )


def test_missing_private_crosswalk_is_an_input_error(tmp_path):
    missing = str(tmp_path / "wcvp_cache.json")
    proc = collect(
        "--private-data", "-m", "private_data", *PRIVATE_NODES, required=(missing,)
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "requires the real local inputs" in proc.stderr
    assert missing in proc.stderr
