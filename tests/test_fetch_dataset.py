"""The checks `labelling/fetch_dataset.py` runs before it pages anything.

Two inventories now live in `data/`, one per Labelbox dataset, and
`dashboard/core.py` reads both by name. The file name is therefore the only
record of which dataset a dump holds, which makes the default `--out` a place a
second dataset must never land: it would replace one inventory with another,
every deep link only the first one knows would quietly change project, and no
gate downstream would see it. So the wrong pairing is a stop here.

Nothing in this file makes a network call or reads a credential.
"""

from __future__ import annotations

import pytest

CONFIGURED = "cmon3zoss00wu0705ertl0vd7"       # config.yaml labelbox.dataset_id
OTHER = "cmn5chixy005u07846jctibv1"            # the combined dispatch dataset


def test_the_default_out_is_refused_for_another_dataset(fetch_dataset):
    with pytest.raises(SystemExit) as stop:
        fetch_dataset.main(["--dataset-id", OTHER])
    said = str(stop.value)
    assert fetch_dataset.OUT_PATH in said
    # Both ids, or the reader cannot tell which of the two the file holds.
    assert CONFIGURED in said and OTHER in said
    assert "--out" in said


def test_the_configured_dataset_may_still_use_the_default_out(fetch_dataset):
    """The guard is about the pairing, not about naming the id at all. Passing
    the configured id explicitly is the same run as passing nothing."""
    args = fetch_dataset.parse_args(["--dataset-id", CONFIGURED])
    assert args.out == fetch_dataset.OUT_PATH


def test_the_configured_id_is_the_one_the_guard_compares_against(settings):
    """This file hard-codes the id so the test needs no network. If config
    moves, the hard-coded value is stale and the guard is being tested against
    a dataset nothing reads."""
    assert settings.load_config()["labelbox"]["dataset_id"] == CONFIGURED
