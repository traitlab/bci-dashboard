"""Which snapshot a page is checked against.

Every builder aborts when the page disagrees with a snapshot folder. The full page
named a fixed date, so a hand-run checked today's numbers against a three-week-old
measurement and appended today's trend points to that old folder's history. The
failure is not silent, but it accuses the wrong file: it reports the live numbers
as stale.

    .venv/bin/pytest tests/test_snapshot_gate.py
"""

import pytest


@pytest.fixture
def store(history, monkeypatch, tmp_path):
    """An empty snapshot store that `latest_snapshot_dir` will look in."""
    monkeypatch.setattr(history.hc, "SNAPSHOT_DIR", str(tmp_path))
    return tmp_path


def test_the_newest_dated_folder_wins(history, store):
    for date in ("2026-08-03", "2026-08-24", "2026-08-07"):
        (store / f"model-health-{date}").mkdir()
    assert history.latest_snapshot_dir().endswith("model-health-2026-08-24")


def test_a_folder_without_a_date_is_not_a_snapshot(history, store):
    (store / "model-health-2026-08-03").mkdir()
    # A working folder beside the snapshots sorts after every date and would
    # otherwise become the gate.
    (store / "model-health-zzz-scratch").mkdir()
    assert history.latest_snapshot_dir().endswith("model-health-2026-08-03")


def test_an_empty_store_fails_loudly(history, store):
    with pytest.raises(SystemExit) as exc:
        history.latest_snapshot_dir()
    assert str(store) in str(exc.value)
