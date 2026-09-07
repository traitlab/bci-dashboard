"""Creating the `selection_round` field the first time a round goes out.

`DataRowMetadataOntology.get_by_name` raises `KeyError` for a field that does
not exist yet. `get_or_create_round_schema` read it as a falsy return, so on a
project that had never dispatched a round the create half never ran and the
dispatch died before writing anything. Nothing covered it, which is how it
shipped.

    .venv/bin/pytest tests/test_round_schema.py
"""

from __future__ import annotations

import pytest


class _Schema:
    def __init__(self, uid):
        self.uid = uid


class _Absent:
    """What the SDK does on a project with no such field: it raises."""

    def __init__(self):
        self.created = []

    def get_by_name(self, name):
        raise KeyError(f"There is no metadata with name '{name}'")

    def create_schema(self, name, kind):
        self.created.append((name, kind))
        return _Schema("new-uid")


class _Present:
    def __init__(self, uid="existing-uid"):
        self.uid = uid

    def get_by_name(self, name):
        return _Schema(self.uid)

    def create_schema(self, name, kind):
        raise AssertionError("must not create a field that already exists")


def test_a_project_that_has_never_dispatched_gets_the_field_made(dispatch_round):
    mdo = _Absent()
    assert dispatch_round.get_or_create_round_schema(mdo) == "new-uid"
    assert [n for n, _ in mdo.created] == [dispatch_round.METADATA_SCHEMA_NAME]


def test_the_field_is_made_as_a_number_because_the_round_is_upserted_as_one(
        dispatch_round):
    """`rounds.py` says a round number is a number in Labelbox. A field created
    with the other kind cannot be written to afterwards."""
    from labelbox.schema.data_row_metadata import DataRowMetadataKind

    mdo = _Absent()
    dispatch_round.get_or_create_round_schema(mdo)
    assert [k for _, k in mdo.created] == [DataRowMetadataKind.number]


def test_a_project_that_already_has_the_field_reuses_it(dispatch_round):
    assert dispatch_round.get_or_create_round_schema(_Present()) == "existing-uid"


def test_any_other_lookup_failure_still_stops_the_dispatch(dispatch_round):
    """Only "no such field" means create one. A refused key or a network fault
    must not be turned into a new field on someone's project."""
    class _Refused:
        def get_by_name(self, name):
            raise PermissionError("Insufficient permissions")

        def create_schema(self, name, kind):
            raise AssertionError("must not create a field after an unclear failure")

    with pytest.raises(PermissionError):
        dispatch_round.get_or_create_round_schema(_Refused())
