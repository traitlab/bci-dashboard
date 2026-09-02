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


def test_no_command_measures_a_list_of_five_by_a_literal(core):
    """The same drift, in the two other places that slice a candidate list.

    `measure.py` computes every top-5 rate in run_log.txt, and both pages quote
    numbers from that file, so a literal here would disagree with the CSV
    column the test above pins.
    """
    import os

    import glob

    # Every module, not a hand-written list of two. A list of which files to
    # check is itself a second copy of a fact, which is the defect this test
    # exists to catch; `explain.py` and `score_confirmatory.py` were both
    # outside the old list and both still held a literal.
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    paths = sorted(glob.glob(os.path.join(root, "dashboard", "*.py")))
    assert len(paths) > 10, "the module glob found almost nothing; check the path"
    for path in paths:
        name = os.path.basename(path)
        src = open(path, encoding="utf-8").read()
        assert "[:5]" not in src, f"{name} slices a candidate list by a literal"
        assert ", 5)" not in src, f"{name} passes a list length as a literal"
        assert "nb-results=5" not in src, f"{name} prints the list length as a literal"


def test_the_run_log_text_lives_in_run_log_py(core):
    """run_log.py says it holds "every line measure.py writes into run_log.txt".

    It did not: measure.main carried about 150 lines of report printing mixed
    into the computation, which is what put measure.py over the 500-line limit.
    The claim is now true, and this keeps it true: a section header printed
    from measure.py means the report has started leaking back.
    """
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    src = open(os.path.join(root, "dashboard", "measure.py"), encoding="utf-8").read()
    assert 'log("---' not in src and 'log(f"---' not in src
