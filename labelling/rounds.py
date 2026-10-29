"""What makes a batch in Labelbox a labelling round.

A round exists in Labelbox as two things: a batch whose name carries the round
number and the month it was sent (``batch0001_2026-10``), and a ``batch_id``
metadata field carrying that same name on every data row in it. `dispatch_round.py` writes both. `close_round.py` finds
the round again by the batch name.

A batch created by hand in the Labelbox interface is a round only if it carries
the same two things, so the convention lives here instead of in a format string
in each script. `verify_round.py` reads a round back and says whether it does.

Stdlib only, so a test can import it without Labelbox installed.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

# The metadata field, and the kind it holds. The value is the batch name, a
# string such as `batch0001_2026-10`, so a row says which batch it went out in
# without a lookup. `dispatch_round.py` creates the field as a String; a field
# that already exists with another kind cannot be written to.
METADATA_SCHEMA_NAME = "batch_id"

# `batch0001_2026-10`, and nothing else. The counter is four digits, zero
# padded; the month is the UTC month it was sent in, not the day, so every
# sender's clock gives the same name.
BATCH_NAME_RE = re.compile(r"^batch(\d{4})_(\d{4}-\d{2})$")


def batch_name(round_no: int, day: date | None = None) -> str:
    """The name a round's batch carries. One writer, so one shape."""
    day = day or datetime.now(timezone.utc).date()
    return f"batch{round_no:04d}_{day:%Y-%m}"


def batch_name_prefix(round_no: int) -> str:
    """What a round is found by later.

    The prefix, not the whole name: whoever closes a round knows its number and
    not the month it was sent, so the month cannot be part of the match.
    """
    return f"batch{round_no:04d}_"


def round_of(name: str) -> int | None:
    """The round number a batch name carries, or None if the name is not one.

    None is the answer for a name that is close but not the convention:
    `batch1_2026-10`, `Batch0001_2026-10`, `batch0001_2026-10-27`. Each of
    those would be missed by whoever closes the round, so none is a round.
    """
    found = BATCH_NAME_RE.match(name.strip())
    return int(found.group(1)) if found else None
