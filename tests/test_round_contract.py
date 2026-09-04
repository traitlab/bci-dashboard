"""A round is a batch named one way and tagged one way, however it was made.

`dispatch_round.py` gets both right by construction. A batch built by hand in
the Labelbox interface is the case these tests exist for: the two things it
usually misses are a name `close_round.py` can match and a `selection_round`
tag, and neither shows up as an error until someone tries to close the round.

    .venv/bin/pytest tests/test_round_contract.py
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace


def fake_project(*names):
    """A stand-in for a Labelbox project: batch names, and nothing else."""
    batches = [SimpleNamespace(name=n, uid=f"uid-{i}") for i, n in enumerate(names)]
    return SimpleNamespace(batches=lambda: list(batches))


def exported(global_key, tag=None, schema="selection_round"):
    """One row as the project export returns it, tagged or not."""
    fields = [] if tag is None else [{"schema_name": schema, "value": tag}]
    return {"data_row": {"global_key": global_key}, "metadata_fields": fields}


# ---------------------------------------------------------------------------
# The name
# ---------------------------------------------------------------------------

def test_the_name_a_round_goes_out_with_is_a_name_it_is_found_by(rounds, close_round):
    """The gate: one module writes the name and the same module supplies the
    prefix the closer matches, so the two cannot drift apart."""
    name = rounds.batch_name(3, date(2026, 9, 4))
    assert name == "Round 3 - 2026-09-04"
    assert close_round.find_batch(fake_project(name), 3).name == name


def test_a_name_that_is_only_close_is_not_a_round(rounds):
    """Each of these would be missed by whoever closes the round, so none of
    them counts as one. Read as the list of ways a hand-made batch goes wrong."""
    for near in ("Round 3", "round 3 - 2026-09-04", "Round 3 - Sept 4",
                 "Round 3 -2026-09-04", "Batch 3 - 2026-09-04"):
        assert rounds.round_of(near) is None, near


def test_a_round_number_is_not_matched_by_a_longer_one(rounds, close_round):
    """Round 3 and round 30 are different rounds, and the prefix has to say so."""
    project = fake_project("Round 30 - 2026-09-04")
    assert close_round.find_batch(project, 3) is None
    assert close_round.find_batch(project, 30) is not None


def test_a_batch_named_close_to_the_round_is_named_in_the_error(close_round):
    """The fix for a near miss is a rename, so the name has to reach the person
    who has to do it. A batch with no bearing on this round stays out of it."""
    project = fake_project("Round 3", "Round 7 - 2026-09-04", "unrelated")
    assert close_round.near_misses(project, 3) == ["Round 3"]


# ---------------------------------------------------------------------------
# The tag
# ---------------------------------------------------------------------------

def test_an_untagged_row_is_reported_with_its_key(verify_round, rounds):
    """A row with no `selection_round` is the other half of the contract, and
    the report names the field to upsert and the value to give it."""
    rows = [exported("a", 3.0), exported("b")]
    problems = verify_round.check_tags(rows, 3)
    assert len(problems) == 1
    assert "1 of 2 rows carry no 'selection_round'" in problems[0]
    assert "'b'" in problems[0] and "= 3" in problems[0]


def test_a_row_tagged_with_another_round_is_not_silently_accepted(verify_round):
    """Re-sending a frame in a later round without re-tagging it is how a round
    ends up holding two rounds' rows."""
    problems = verify_round.check_tags([exported("a", 2.0)], 3)
    assert problems and "another round's number" in problems[0]


def test_a_fully_tagged_round_raises_nothing(verify_round):
    assert verify_round.check_tags([exported("a", 3.0), exported("b", 3)], 3) == []


def test_the_tag_is_read_by_name_not_by_position(verify_round):
    """The export lists every metadata field on the row. Another field sitting
    in front of this one is not this one missing."""
    row = {"data_row": {"global_key": "a"},
           "metadata_fields": [{"schema_name": "tag", "value": "x"},
                               {"schema_name": "selection_round", "value": 3.0}]}
    assert verify_round.round_tag(row) == 3.0
    assert verify_round.check_tags([row], 3) == []


# ---------------------------------------------------------------------------
# The membership
# ---------------------------------------------------------------------------

def test_a_batch_of_the_right_size_with_a_frame_swapped_fails(verify_round, tmp_path):
    """Set equality, not a count. A swapped frame is the failure a count misses,
    and it is the one that makes a drawn sample no longer the sample drawn."""
    csv_path = tmp_path / "drawn.csv"
    csv_path.write_text("global_key\na\nb\nc\n", encoding="utf-8")
    problems = verify_round.check_membership(
        [exported("a", 1.0), exported("b", 1.0), exported("z", 1.0)], csv_path)
    assert len(problems) == 2
    assert "1 drawn frames are not in the batch" in problems[0]
    assert "not drawn" in problems[1]


def test_a_partial_send_is_named_as_a_partial_send(verify_round, tmp_path):
    csv_path = tmp_path / "drawn.csv"
    csv_path.write_text("global_key\na\nb\nc\n", encoding="utf-8")
    problems = verify_round.check_membership([exported("a", 1.0)], csv_path)
    assert problems and "A partial round" in problems[0]


def test_the_drawn_sample_sent_whole_raises_nothing(verify_round, tmp_path):
    csv_path = tmp_path / "drawn.csv"
    csv_path.write_text("global_key\na\nb\n", encoding="utf-8")
    rows = [exported("b", 1.0), exported("a", 1.0)]
    assert verify_round.check_membership(rows, csv_path) == []


# ---------------------------------------------------------------------------
# One convention, one owner
# ---------------------------------------------------------------------------

def test_the_dispatcher_and_the_verifier_name_the_same_metadata_field(
        rounds, dispatch_round, verify_round):
    """Three scripts, one field name. A rename in `rounds` has to move all of
    them or none, which is the point of the module."""
    assert dispatch_round.METADATA_SCHEMA_NAME == rounds.METADATA_SCHEMA_NAME
    assert verify_round.rounds.METADATA_SCHEMA_NAME == rounds.METADATA_SCHEMA_NAME
