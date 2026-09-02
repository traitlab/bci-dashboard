"""The load-and-join layer's own failures, which every command hits first."""

import pytest


def test_a_missing_input_stops_the_run_with_one_readable_line(health, tmp_path):
    """A first run on a fresh clone hits this, from any of the four commands.

    It used to raise FileNotFoundError, which only measure.py caught, so the
    three builders printed a traceback for the most ordinary failure there is.
    """
    with pytest.raises(SystemExit) as e:
        health.load_health(gt_csv=str(tmp_path / "absent.csv"))
    msg = str(e.value)
    assert "the botanist labels" in msg          # what the file is, not its name
    assert "absent.csv" in msg                   # where it looked
    assert "bin/refresh.sh" in msg               # what to do about it
