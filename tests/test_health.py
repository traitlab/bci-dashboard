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


def test_the_list_length_health_measures_is_the_one_the_pages_state(health, core):
    """`top5_accuracy` is the species table's "Right name in the list" column,
    and `figures.prepare` aborts a build whose cache carries more names than
    the pages are written for. Those were a literal 5 and a constant: raising
    the request setting in one place would have left the column counting five
    while the prose said ten.
    """
    import figures  # already on sys.path via the `health` fixture

    assert figures.N_CANDIDATES == core.N_CANDIDATES
    src = open(health.__file__, encoding="utf-8").read()
    assert '"ranked"][:N_CANDIDATES]' in src
    assert '"ranked"][:5]' not in src, "the list length is a literal again"
