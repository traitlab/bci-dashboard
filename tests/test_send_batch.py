"""bin/send_batch.py, the one-file sender the collaborator downloads.

It picks the next batch from what Labelbox already holds, and the names it
writes are the ones the refresh reads back as sends.

    .venv/bin/pytest tests/test_send_batch.py
"""

from __future__ import annotations

import datetime

import pytest
from conftest import REPO, load


@pytest.fixture(scope="session")
def send():
    return load("_send_batch_under_test", REPO / "bin" / "send_batch.py")


def test_the_name_is_the_one_the_refresh_records(send, rounds):
    day = datetime.date(2026, 10, 28)
    assert send.batch_name(7, day) == rounds.batch_name(7, day)
    assert send.NAME_RE.pattern == rounds.BATCH_NAME_RE.pattern


def test_both_take_the_utc_month_whatever_the_local_clock(send, rounds, monkeypatch):
    """31 Oct 23:30 in Panama is 1 Nov in UTC: both senders name it November."""
    panama = datetime.datetime(2026, 10, 31, 23, 30,
                               tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))

    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return panama.astimezone(tz) if tz else panama.replace(tzinfo=None)

    class Today(datetime.date):
        @classmethod
        def today(cls):
            return panama.date()

    monkeypatch.setattr(rounds, "datetime", Clock)
    monkeypatch.setattr(rounds, "date", Today)
    monkeypatch.setattr(send.datetime, "datetime", Clock)
    monkeypatch.setattr(send.datetime, "date", Today)
    assert send.batch_name(7) == rounds.batch_name(7) == "batch0007_2026-11"


def test_the_next_batch_is_the_lowest_not_in_labelbox(send):
    sent = send.sent_numbers(["batch0001_2026-10", "batch0002_2026-11", "trial run",
                              "batch00031_2026-10", "batch0004_old"])
    assert sent == {1: "batch0001_2026-10", 2: "batch0002_2026-11"}
    assert send.pick([1, 1, 2, 3, 4], sent, None) == 3
    assert send.pick([1, 2, 3], {}, None) == 1


def test_a_batch_asked_for_by_number(send):
    assert send.pick([1, 2, 3], {1: "batch0001_2026-10"}, 3) == 3
    with pytest.raises(SystemExit, match="already sent as batch0001_2026-10"):
        send.pick([1, 2, 3], {1: "batch0001_2026-10"}, 1)
    with pytest.raises(SystemExit, match="no batch 9"):
        send.pick([1, 2, 3], {}, 9)


def test_nothing_left_to_send(send):
    with pytest.raises(SystemExit, match="already in Labelbox"):
        send.pick([1, 2], {1: "a", 2: "b"}, None)
