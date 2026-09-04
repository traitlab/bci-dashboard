"""What makes a batch in Labelbox a labelling round.

A round exists in Labelbox as two things: a batch whose name carries the round
number, and a ``selection_round`` metadata field carrying that same number on
every data row in it. `dispatch_round.py` writes both. `close_round.py` finds
the round again by the batch name.

A batch created by hand in the Labelbox interface is a round only if it carries
the same two things, so the convention lives here instead of in a format string
in each script. `verify_round.py` reads a round back and says whether it does.

Stdlib only, so a test can import it without Labelbox installed.
"""
from __future__ import annotations

import re
from datetime import date

# The metadata field, and the number kind it holds. A round number is a number
# in Labelbox, not a string, because `dispatch_round.py` upserts it as one and a
# field that already exists with the other kind cannot be written to.
METADATA_SCHEMA_NAME = "selection_round"

# `Round 3 - 2026-09-04`, and nothing else. The date is the day it went out.
BATCH_NAME_RE = re.compile(r"^Round (\d+) - (\d{4}-\d{2}-\d{2})$")


def batch_name(round_no: int, day: date | None = None) -> str:
    """The name a round's batch carries. One writer, so one shape."""
    return f"Round {round_no} - {(day or date.today()).isoformat()}"


def batch_name_prefix(round_no: int) -> str:
    """What a round is found by later.

    The prefix, not the whole name: whoever closes a round knows its number and
    not the day it was sent, so the date cannot be part of the match.
    """
    return f"Round {round_no} - "


def round_of(name: str) -> int | None:
    """The round number a batch name carries, or None if the name is not one.

    None is the answer for a name that is close but not the convention:
    `Round 3`, `round 3 - 2026-09-04`, `Round 3 - Sept 4`. Each of those would
    be missed by whoever closes the round, so none of them is a round.
    """
    found = BATCH_NAME_RE.match(name.strip())
    return int(found.group(1)) if found else None
