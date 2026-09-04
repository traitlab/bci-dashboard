"""The species table's own two additions: the accuracy bar and the export link.

Etienne sorted the table by hand and counted rows out loud to answer "how many
species are above 85 or so". The control answers it directly, and the count it
prints has to be the same count the rows carry, or the page tells a reader two
different things about one population.

The bar defaults to `core.RELIABLE_MIN_TOP1` over species carrying
`panels.THIN_MIN_FRAMES` or more labelled frames, which is the definition of
"usually right" in `core.diagnose`. So at the default the control's number and
the count of rows tagged that way are the same number reached two ways, and a
change to either definition that does not change the other fails here.

    .venv/bin/pytest tests/test_species_panel.py
"""

from __future__ import annotations

import re

from conftest import species_rows

BAR_COUNT = re.compile(r'id="accuracy-bar-count">(\d+)</span>')
OPTION = re.compile(r'<option value="([0-9.]+)" data-n="(\d+)"( selected)?>')


def test_the_bar_defaults_to_the_reliable_threshold(panels, core):
    """The one option a test can check against another definition."""
    assert panels.THRESHOLD_DEFAULT == core.RELIABLE_MIN_TOP1
    assert panels.THRESHOLD_DEFAULT in panels.THRESHOLD_BARS


def test_the_count_at_the_default_bar_is_the_usually_right_row_count(external_page):
    """The gate. At 90% with the 10-frame floor the control counts exactly the
    species the table tags "usually right", because the status is defined as
    that pair of conditions."""
    html, _ = external_page
    printed = BAR_COUNT.search(html)
    assert printed, "the species panel prints no bar count"
    tagged = [row for row in species_rows(html) if 'class="tag reliable"' in row]
    assert int(printed.group(1)) == len(tagged) > 0


def test_every_bar_carries_its_own_count(external_page, panels):
    """The counts are rendered, one per option, so the control needs no
    measurement at read time and the page stays one file."""
    html, _ = external_page
    options = OPTION.findall(html)
    assert [float(v) for v, _, _ in options] == list(panels.THRESHOLD_BARS)
    selected = [v for v, _, sel in options if sel]
    assert selected == [f"{panels.THRESHOLD_DEFAULT:.2f}"]
    counts = [int(n) for _, n, _ in options]
    # A higher bar can never admit more species than a lower one.
    assert counts == sorted(counts, reverse=True)


def test_the_sentence_says_which_species_are_left_out(external_page, panels):
    """The exclusion is in the sentence, not a footnote: a species with one
    labelled frame scores 0% or 100% and nothing else."""
    html, _ = external_page
    assert f"{panels.THIN_MIN_FRAMES} or more labelled frames" in html


def test_the_bar_counts_only_species_over_the_frame_floor(panels):
    """Thin species are excluded whatever the bar, including a perfect one."""
    rows = [{"n_labelled_frames": panels.THIN_MIN_FRAMES - 1, "top1_accuracy": 1.0},
            {"n_labelled_frames": panels.THIN_MIN_FRAMES, "top1_accuracy": 1.0},
            {"n_labelled_frames": panels.THIN_MIN_FRAMES, "top1_accuracy": 0.5}]
    assert panels._clearing(rows, 0.9) == 1
    assert panels._clearing(rows, 0.5) == 2


def test_a_rate_that_equals_the_bar_clears_it(panels):
    """Same tolerance as `core.diagnose`: 9/10 is 0.9 in arithmetic and a float
    step below it in binary, and the two counts have to agree."""
    rows = [{"n_labelled_frames": 10, "top1_accuracy": 9 / 10}]
    assert panels._clearing(rows, 0.9) == 1


def test_the_species_table_links_its_own_export(external_page):
    """The table shows some columns of a wider CSV, and the CSV is beside the
    page rather than somewhere a reader has to be told about."""
    html, stdout = external_page
    assert 'href="per_species_health.csv"' in html
    assert "per_species_health.csv" in stdout
