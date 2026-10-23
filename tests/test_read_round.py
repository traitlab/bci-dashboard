"""`labelling/read_round.py` on a synthetic round with known arm outcomes.

    .venv/bin/pytest tests/test_read_round.py
"""

from __future__ import annotations

import csv

import pytest
from conftest import REPO, load

WELL = 10  # core.WELL_SAMPLED_MIN_N


@pytest.fixture(scope="module")
def rr():
    return load("_read_round_under_test", REPO / "labelling" / "read_round.py")


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def files(tmp_path):
    """Ledgers in rounds/. Round 1: prioritised p1-p4, control c1-c2. Round 2
    (unlabelled): p9 only. Ledger batch_id is not the round: round 1 was batch 7.

    Before round 1 the GT holds `common` x10 (well sampled) and `rare` x2.
    Labels: p1 common (guess common), p2 rare (guess common), p3 fresh (guess
    common), p4 unlabelled; c1 common (guess common), c2 common (guess rare).
    """
    guesses = {"p1": "common", "p2": "common", "p3": "common", "c1": "common", "c2": "rare"}
    head = ["round", "batch_id", "global_key", "picked_by", "predicted_species"]
    (tmp_path / "rounds").mkdir()
    r1 = [("1", "7", f"p{i}", "queue", guesses.get(f"p{i}", "")) for i in (1, 2, 3, 4)]
    r1 += [("1", "7", f"c{i}", "control", guesses[f"c{i}"]) for i in (1, 2)]
    write(tmp_path / "rounds" / "round_1.csv", head, r1)
    write(tmp_path / "rounds" / "round_2.csv", head, [("2", "1", "p9", "queue", "")])
    gt = [(f"old{i}", "common") for i in range(WELL)] + [("old_r1", "rare"), ("old_r2", "rare")]
    gt += [("p1", "Common"), ("p2", "rare"), ("p3", "fresh"), ("c1", "common"), ("c2", "common")]
    write(tmp_path / "gt.csv", ["global_key", "wcvp_canonical_name"], gt)
    return tmp_path


def load_inputs(rr, d):
    sent = [r for p in sorted((d / "rounds").glob("round_*.csv")) for r in rr.read_rows(p)]
    gt = {r["global_key"]: r["wcvp_canonical_name"] for r in rr.read_rows(d / "gt.csv")}
    guess = {r["global_key"]: r["predicted_species"] for r in sent}
    return sent, gt, guess


def test_known_arm_outcomes(rr, files):
    res = rr.read_round(*load_inputs(rr, files), 1)
    assert res["status"] == "closed"
    p, c = res["arms"]["prioritised"], res["arms"]["control"]
    assert (p["n_sent"], p["n_labelled"], p["n_with_guess"]) == (4, 3, 3)
    assert p["corrections"] == 2 and p["new_rows"] == 1 and p["new_species"] == {"fresh"}
    assert p["long_tail_rows"] == 2  # rare (2 < 10) and fresh (0)
    assert (c["n_labelled"], c["corrections"], c["new_rows"], c["long_tail_rows"]) == (2, 1, 0, 0)


def test_unclosed_round_is_pending(rr, files):
    assert rr.read_round(*load_inputs(rr, files), 2)["status"] == "pending"


def test_empty_arm_has_no_interval(rr, files):
    sent, gt, guess = load_inputs(rr, files)
    res = rr.read_round(sent, {**gt, "p9": "common"}, guess, 2)
    row = rr.out_row("2", "control", res["arms"]["control"])
    assert res["status"] == "closed" and row["n_labelled"] == 0
    assert row["corrections_lo"] == row["new_lo"] == row["long_tail_hi"] == ""
    assert "-" in rr.render("t", [row])


def test_interval_is_wilson(rr, files):
    res = rr.read_round(*load_inputs(rr, files), 1)
    row = rr.out_row("1", "control", res["arms"]["control"])
    lo, hi = rr.wilson(1, 2)
    assert (row["corrections_lo"], row["corrections_hi"]) == (round(lo, 4), round(hi, 4))


def test_pool_sums_closed_rounds(rr, files):
    sent, gt, guess = load_inputs(rr, files)
    r1 = rr.read_round(sent, gt, guess, 1)
    r2 = rr.read_round(sent, {**gt, "p9": "fresh2"}, guess, 2)
    pooled = rr.pool([r1, r2])
    assert pooled["prioritised"]["n_labelled"] == 4 and pooled["control"]["n_labelled"] == 2
    # fresh is new at round 1, fresh2 at round 2: one new species each
    assert pooled["prioritised"]["new_species"] == 1 + 1


def test_cli_pending_exits_zero_and_writes_csv(rr, files, monkeypatch, capsys):
    out = files / "out.csv"
    monkeypatch.setattr("sys.argv", ["read_round", "--round", "2", "--ledger-dir", str(files / "rounds"),
                                     "--gt", str(files / "gt.csv"),
                                     "--out", str(out)])
    rr.main()
    assert "pending" in capsys.readouterr().out
    rows = rr.read_rows(out)
    assert rows == [{**dict.fromkeys(rr.OUT_COLUMNS, ""), "scope": "2", "status": "pending"}]


def test_cli_all_with_no_gt_file_is_pending(rr, files, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["read_round", "--all", "--ledger-dir", str(files / "rounds"),
                                     "--gt", str(files / "missing.csv"), "--out", str(files / "o.csv")])
    rr.main()
    assert "pooled: pending" in capsys.readouterr().out


def test_queue_page_reads_the_csv_read_round_writes(rr, files, monkeypatch, queue_panels):
    from types import SimpleNamespace
    out = files / "round_readout.csv"
    monkeypatch.setattr("sys.argv", ["read_round", "--round", "1", "--ledger-dir", str(files / "rounds"),
                                     "--gt", str(files / "gt.csv"),
                                     "--out", str(out)])
    rr.main()
    html = queue_panels.readout_block(SimpleNamespace(verify_dir=str(files)))
    assert "pending" not in html
    assert ">prioritised<" in html and ">random control<" in html


def test_later_keys_come_from_the_ledgers_round_not_batch_id(rr, files):
    # round 1 was batch 7: read by batch_id it would count as "later" than round 2
    sent, gt, guess = load_inputs(rr, files)
    res = rr.read_round(sent, {**gt, "p9": "fresh"}, guess, 2)  # p3 made fresh known in round 1
    assert res["arms"]["prioritised"]["new_rows"] == 0
