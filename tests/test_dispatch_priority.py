"""The batch number a round goes out as, and the Labelbox priority it becomes.

`send_batches.csv` holds fifty batches in queue order and Labelbox has five
priority levels, so the mapping saturates rather than wrapping. Sending every
batch at priority 1, which is what the script did before, throws away the
ordering the whole queue exists to produce.

    .venv/bin/pytest tests/test_dispatch_priority.py
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("batch, expect", [("1", 1), ("2", 2), ("4", 4), ("5", 5)])
def test_the_first_batches_map_one_to_one(dispatch_round, batch, expect):
    assert dispatch_round.priority_for_batch(batch) == expect


@pytest.mark.parametrize("batch", ["6", "12", "50"])
def test_every_later_batch_saturates_at_the_lowest_priority(dispatch_round, batch):
    assert dispatch_round.priority_for_batch(batch) == dispatch_round.MAX_PRIORITY


def test_an_explicit_priority_wins_over_the_batch_number(dispatch_round):
    """A batch re-sent out of order is a human decision, not a bug to correct."""
    assert dispatch_round.priority_for_batch("9", explicit=1) == 1
    assert dispatch_round.priority_for_batch("1", explicit=5) == 5


def test_a_run_with_no_batch_goes_out_at_the_top(dispatch_round):
    """No --batch means no order to preserve, which is the old behaviour."""
    assert dispatch_round.priority_for_batch(None) == 1


@pytest.mark.parametrize("batch", ["", "  ", "batch-3", "1.5"])
def test_a_batch_id_that_is_not_a_number_does_not_crash_a_dispatch(dispatch_round, batch):
    assert dispatch_round.priority_for_batch(batch) == 1


def test_a_zero_or_negative_batch_id_still_lands_inside_the_five_levels(dispatch_round):
    assert dispatch_round.priority_for_batch("0") == 1
    assert dispatch_round.priority_for_batch("-3") == 1


def test_whitespace_around_the_batch_id_is_ignored(dispatch_round):
    """`load_selection_csv` strips, and this has to agree with it."""
    assert dispatch_round.priority_for_batch(" 3 ") == 3


def test_an_integer_batch_id_works_as_well_as_the_csv_string(dispatch_round):
    assert dispatch_round.priority_for_batch(3) == 3
