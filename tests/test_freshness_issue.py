"""The stale-feed issue is opened on a stale or missing feed and closed on fresh ones."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "freshness_issue", Path(__file__).resolve().parents[1] / "bin" / "freshness_issue.py")
fi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fi)


def row(what, newest, age, stale):
    return {"what": what, "newest": newest, "age": age, "stale": stale}


def test_stale_feed_opens_with_dates_ages_threshold_and_population():
    action, body = fi.decide([row("photo", "2026-03-01", 20, True), row("label", "2026-03-10", 5, False)],
                             120, 30, "2026-03-21")
    assert action == "open"
    assert "2026-03-01 (age 20 days) **stale**" in body and "2026-03-10 (age 5 days)" in body
    assert "14 days" in body and "120 graded frames and 30 frames in the 2026 catalog pool" in body


def test_fresh_feeds_close():
    assert fi.decide([row("photo", "2026-03-10", 5, False), row("label", "2026-03-08", 7, False)],
                     1, 1, "2026-03-15") == ("close", "")


def test_missing_dates_are_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(fi.hc, "SPLITS_CSV", str(tmp_path / "absent.csv"))
    monkeypatch.setattr(fi.hc, "CATALOG_INPUT_CSV", str(tmp_path / "absent2.csv"))
    monkeypatch.setattr(fi.hc, "GT_LABEL_DATES_CSV", str(tmp_path / "absent3.csv"))
    out = tmp_path / "body.md"
    assert fi.main(["--date", "2026-03-15", "--body-file", str(out)]) == 0
    assert "not found (age unknown)" in out.read_text()


def test_fresh_files_print_close_and_write_no_body(tmp_path, monkeypatch, capsys):
    splits = tmp_path / "splits.csv"
    splits.write_text("global_key,split\nDJI_20260310090000_0001_V_1zoom.JPG,train\n")
    labels = tmp_path / "labels.csv"
    labels.write_text("global_key,labelled_at\nk,2026-03-08T11:00:00Z\n")
    monkeypatch.setattr(fi.hc, "SPLITS_CSV", str(splits))
    monkeypatch.setattr(fi.hc, "CATALOG_INPUT_CSV", str(tmp_path / "none.csv"))
    monkeypatch.setattr(fi.hc, "GT_LABEL_DATES_CSV", str(labels))
    out = tmp_path / "body.md"
    assert fi.main(["--date", "2026-03-15", "--body-file", str(out)]) == 0
    assert capsys.readouterr().out.strip() == "close" and not out.exists()
