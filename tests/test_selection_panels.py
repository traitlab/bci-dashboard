"""The queue page's measured evidence for its ordering: two JSON files from
`labelling/rank_queue.py --audit` and `--confound`, read here with the standard
library and refused when they describe a different pool from the ordering.

    .venv/bin/pytest tests/test_selection_panels.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace


def _audit(tmp_path, **over):
    d = {"audit": {"h1_sustainability": {"pct_gain": 162.4, "ci_low": 138.9,
                                         "ci_high": 193.3, "wilcoxon_p": 0.0039},
                   "alpha": 0.05, "n_seeds": 8, "rounds": 20,
                   "library_version": "0.9.0", "embedding_sha256": "anchor-sha"},
         "efficiency": {"labels_saved_pct": 70.0, "challenger_rounds_to_match": 6.0,
                        "baseline_rounds": 20},
         "preflight": {"separability_pct": 81.8, "gain_on_ladder": False},
         "population": {"n_frames": 1719, "n_species": 155, "n_rare_species": 107,
                        "rare_threshold": 5},
         "params": {"k_per_round": 20, "seed_pool_size": 200},
         "run": {"extra": {"written": "2026-09-10"}}}
    for k, v in over.items():
        d["audit"]["h1_sustainability"][k] = v
    p = tmp_path / "audit.json"
    p.write_text(json.dumps(d))
    return str(p)


def _confound(tmp_path, verdict="robust"):
    d = {"audits": [{"population": "queued photos", "covariate": "export batch",
                     "verdict": verdict, "raw_corr": 0.445, "partial_corr": 0.452,
                     "partial_p": 0.0002, "covariate_eta2": 0.004, "n": 3873,
                     "n_groups": 2}],
         "run": {"embedding_sha256": "pool-sha",
                 "extra": {"anchor_sha256": "anchor-sha", "written": "2026-09-10"}}}
    p = tmp_path / "confound.json"
    p.write_text(json.dumps(d))
    return str(p)


def test_an_absent_file_is_none_and_a_broken_one_is_named(selection_panels, tmp_path):
    sp = selection_panels
    assert sp.selection_audit(str(tmp_path / "none.json")) is None
    assert sp.selection_confound(str(tmp_path / "none.json")) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    try:
        sp.selection_audit(str(bad))
    except SystemExit as e:
        assert "bad.json" in str(e)
    else:
        raise AssertionError("a file that is there and unreadable must stop the build")


def test_the_audit_is_flattened_and_the_pass_rule_is_read_off_the_numbers(
        selection_panels, tmp_path):
    a = selection_panels.selection_audit(_audit(tmp_path))
    assert a["gain"] == 162.4 and a["n_frames"] == 1719 and a["n_rare"] == 107
    assert a["labels_saved_pct"] == 70.0 and a["sha"] == "anchor-sha"
    assert a["passed"] is True
    # Range crossing zero: no claim, whatever the p-value says.
    assert selection_panels.selection_audit(_audit(tmp_path, ci_low=-2.0))["passed"] is False
    # p at the alpha, not under half of it: no claim.
    assert selection_panels.selection_audit(_audit(tmp_path, wilcoxon_p=0.04))["passed"] is False
    # A number that is not there is None, never zero.
    p = tmp_path / "thin.json"
    p.write_text(json.dumps({"audit": {}}))
    thin = selection_panels.selection_audit(str(p))
    assert thin["gain"] is None and thin["passed"] is False


def test_the_notes_say_unmeasured_without_the_files(selection_panels):
    c = SimpleNamespace(selection_audit=None, selection_confound=None, head_n=0)
    assert "Not yet measured" in selection_panels.audit_note(c)
    assert "Not yet tested" in selection_panels.confound_note(c)
    assert "162" not in selection_panels.audit_note(c)


def test_the_notes_carry_the_number_its_population_and_its_range(selection_panels,
                                                                  tmp_path):
    sp = selection_panels
    c = SimpleNamespace(selection_audit=sp.selection_audit(_audit(tmp_path)),
                        selection_confound=sp.selection_confound(_confound(tmp_path)),
                        head_n=389, head_tele_share=0.1877, queue_tele_share=0.1154)
    note = sp.audit_note(c)
    assert "162% more rare species" in note
    assert "1,719 photos" in note and "107 of them rare" in note
    assert "range 139% to 193%" in note and "8 such starts" in note
    assert "70% fewer labels" in note
    assert "paper" in note, "the page says where the number does not come from"
    cf = sp.confound_note(c)
    assert "holds once the export batch is held fixed" in cf
    assert "3,873" in cf and "+0.45 before, +0.45 after" in cf
    assert "19% carry the newer file naming" in cf


def test_a_failed_audit_claims_nothing(selection_panels, tmp_path):
    c = SimpleNamespace(selection_audit=selection_panels.selection_audit(
        _audit(tmp_path, ci_low=-2.0)))
    note = selection_panels.audit_note(c)
    assert "claims nothing" in note and "more rare species over the run" not in note


def test_a_confounded_verdict_is_said_plainly(selection_panels, tmp_path):
    c = SimpleNamespace(selection_confound=selection_panels.selection_confound(
        _confound(tmp_path, "confounded")), head_n=0)
    assert "is mostly the export batch" in selection_panels.confound_note(c)


def test_evidence_run_against_other_photos_is_a_complaint_naming_the_file(
        selection_panels, tmp_path):
    sp = selection_panels
    audit = sp.selection_audit(_audit(tmp_path))
    conf = sp.selection_confound(_confound(tmp_path))
    fresh = {"sha": "pool-sha", "anchor_sha": "anchor-sha"}
    assert sp.selection_complaint(audit, conf, fresh) == ""
    # The audit ran on other labelled photos than the ordering was anchored on.
    got = sp.selection_complaint(audit, conf, {"sha": "pool-sha", "anchor_sha": "other"})
    assert "selection_audit.json" in got and "--audit" in got
    # The confound ran on another pool.
    got = sp.selection_complaint(audit, conf, {"sha": "other", "anchor_sha": "anchor-sha"})
    assert "selection_confound.json" in got and "--confound" in got
    # The older text sidecar carries no hash, so nothing can be checked.
    assert sp.selection_complaint(audit, conf, {"sha": None, "anchor_sha": None}) == ""
    # Absent evidence is not stale evidence.
    assert sp.selection_complaint(None, None, fresh) == ""
