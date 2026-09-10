"""The queue's confound audit: the covariates it holds fixed, and what it does
with a photo whose covariate cannot be read.

The helpers live in `labelling/rank_confound.py` and need numpy; the ranker
that calls them needs labelfirst too. Both come from the speciesfirst
virtualenv:

    ../speciesfirst/.venv/bin/python -m pytest tests/test_rank_confound.py
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def rank_confound():
    pytest.importorskip("numpy", reason="numpy is not in this virtualenv")
    from conftest import load
    return load("_rank_confound_under_test", REPO / "labelling" / "rank_confound.py")


def test_a_photo_with_no_covariate_is_left_out_and_counted_not_grouped(rank_confound):
    """Two photos with no readable site are not a thirteenth site called "".
    They leave the audit, and the audit says how many left."""
    import numpy as np
    score = np.array([0.1, 0.2, 0.3, 0.4])
    target = np.array([1.0, 2.0, 3.0, 4.0])
    kept, n_out = rank_confound.without_unreconciled(score, target, ["a", "", "b", ""])
    s, t, cov = kept
    assert n_out == 2
    assert s.tolist() == [0.1, 0.3] and t.tolist() == [1.0, 3.0]
    assert cov == ["a", "b"]


def test_nothing_is_left_out_when_every_photo_has_a_covariate(rank_confound):
    import numpy as np
    kept, n_out = rank_confound.without_unreconciled(
        np.array([1.0, 2.0]), np.array([3.0, 4.0]), ["x", "y"])
    assert n_out == 0 and kept[2] == ["x", "y"]


def test_the_audit_record_carries_how_many_were_left_out(rank_confound):
    """The page prints the count beside each test, so it has to be in the JSON
    under a name the page reads."""
    pytest.importorskip("labelfirst", reason="labelfirst is not in this virtualenv")
    import numpy as np
    rng = np.random.default_rng(0)
    target = rng.normal(size=80)
    score = target + rng.normal(size=80) * 0.5
    cov = [("p", "q")[i % 2] for i in range(80)]
    cov[3] = cov[7] = ""
    rec = rank_confound.one_confound("queued photos", score, target, cov,
                                     score_name="s", target_name="t", covariate_name="site")
    assert rec["n_unreconciled"] == 2 and rec["n"] == 78 and rec["n_groups"] == 2
    assert "" not in rec["within_group"]


def test_the_ranker_holds_the_flight_fixed_as_well_as_the_site_and_the_batch():
    """The plan asked for flight = (date, site). Read as text so the check runs
    on the stdlib interpreter too."""
    src = (REPO / "labelling" / "rank_queue.py").read_text(encoding="utf-8")
    assert re.search(r'\("flight",', src), "run_confound no longer audits the flight"
    assert "load_flights" in src
