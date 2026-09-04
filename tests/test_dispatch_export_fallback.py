"""What a dispatch does when the key may read the dataset but not export it.

Our key is exactly that key: every `export` on every project and on the
combined dataset answers a permission refusal, while `data_rows()` pages fine.
`fetch_data_row_ids` exported and nothing else, so the refusal ended the
dispatch before a single row was tagged. It now falls through to paging, which
is slower and works.

Nothing here reaches Labelbox: the dataset is a stub that raises the refusal the
real one raises.

    .venv/bin/pytest tests/test_dispatch_export_fallback.py
"""

from __future__ import annotations

import pytest
from lbox.exceptions import AuthorizationError, MalformedQueryException


class Row:
    def __init__(self, global_key, uid):
        self.global_key, self.uid = global_key, uid


class Dataset:
    """A dataset that refuses to export and pages happily."""

    name = "BCI Workshop - Drone Photos"

    def __init__(self, refusal, rows):
        self._refusal, self._rows = refusal, rows

    def export(self, params=None):
        raise self._refusal

    def data_rows(self):
        return iter(self._rows)


class Client:
    def __init__(self, dataset):
        self._dataset = dataset

    def get_datasets(self):
        return [self._dataset]


ROWS = [Row("comb_DJI_0001.JPG", "row-1"), Row("comb_DJI_0002.JPG", "row-2")]


@pytest.mark.parametrize("refusal", [
    AuthorizationError("Insufficient permissions to perform this action"),
    MalformedQueryException(
        [{"error": "You do not have permission to export data from some projects"}]),
])
def test_a_refused_export_pages_the_dataset_instead(dispatch_round, refusal, capsys):
    dataset = Dataset(refusal, ROWS)
    got = dispatch_round.fetch_data_row_ids(Client(dataset), dataset.name)
    assert got == {"comb_DJI_0001.JPG": "row-1", "comb_DJI_0002.JPG": "row-2"}
    # Said out loud, because the slow route taking twenty times as long is
    # otherwise indistinguishable from a hung export.
    assert "paging" in capsys.readouterr().out


def test_a_row_with_no_global_key_is_left_out_rather_than_keyed_on_none(dispatch_round):
    """The queue names frames by global key, so a row without one is unaddressable."""
    dataset = Dataset(AuthorizationError("nope"), [*ROWS, Row(None, "row-3")])
    assert None not in dispatch_round.page_data_row_ids(dataset)


def test_an_export_the_key_may_run_is_still_the_route_taken(dispatch_round):
    """The fallback is for a refusal, not a replacement for the bulk path."""
    class Exporting(Dataset):
        def export(self, params=None):
            raise AssertionError("should not have been reached")

        def data_rows(self):
            raise AssertionError("paged without a refusal")

    with pytest.raises(AssertionError, match="should not have been reached"):
        dispatch_round.fetch_data_row_ids(
            Client(Exporting(None, [])), Exporting.name)
