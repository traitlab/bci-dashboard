"""The stale-photo check (`labelling/check_photo_links.py`) and the queue page line it feeds.

A fake client stands in for Labelbox: nothing here reaches the network or reads a credential.

    .venv/bin/pytest tests/test_photo_links.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

OLD = "https://object-arbutus.cloud.computecanada.ca/lefolab_drone_missions_wpt/m/a.JPG"
NEW = "https://object-arbutus.alliancecan.ca/swift/v1/lefolab/m/a.JPG"


@pytest.fixture(scope="session")
def check_photo_links():
    from conftest import REPO, _on_path, load
    with _on_path(REPO / "labelling"):
        return load("_check_photo_links_under_test", REPO / "labelling" / "check_photo_links.py")


@pytest.fixture(scope="session")
def queue_panels():
    from conftest import REPO, _on_path
    with _on_path(REPO / "dashboard"):
        import queue_panels
        yield queue_panels


def fake_client(urls, name="2024_bci"):
    rows = [SimpleNamespace(row_data=u, global_key=f"k{i}") for i, u in enumerate(urls)]
    dataset = SimpleNamespace(name=name, data_rows=lambda: iter(rows))
    other = SimpleNamespace(name="other", data_rows=lambda: iter([]))
    return SimpleNamespace(get_datasets=lambda: iter([other, dataset]))


def ok(url):
    return "200"


def test_counts_old_host_rows_among_mixed_hosts(check_photo_links, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")
    out = tmp_path / "photo_links.json"
    urls = [OLD, NEW, OLD, "", None, OLD]
    got = check_photo_links.run(str(out), lambda key: fake_client(urls), ok)
    assert (got["status"], got["total_rows"], got["old_host_rows"]) == ("checked", 6, 3)
    assert got["examples"] == ["k0", "k2", "k5"]
    # An empty row_data is a blank frame too, whatever the probe says.
    assert got["broken_rows"] == 2 and got["status_codes"] == {"200": 4, "no row_data": 2}
    assert json.loads(out.read_text()) == got


def test_zero_old_host_rows(check_photo_links, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")
    got = check_photo_links.run(str(tmp_path / "p.json"), lambda key: fake_client([NEW, NEW]), ok)
    assert got["old_host_rows"] == 0 and got["examples"] == []
    assert got["broken_rows"] == 0


def test_a_404_row_is_broken_though_on_the_new_host(check_photo_links, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")
    renamed = NEW.replace("/m/", "/20260420_renamed/")
    got = check_photo_links.run(str(tmp_path / "p.json"),
                                lambda key: fake_client([NEW, renamed, NEW]),
                                lambda url: "404" if "20260420" in url else "200")
    assert got["old_host_rows"] == 0 and got["broken_rows"] == 1
    assert got["broken_examples"] == ["k1"] and got["status_codes"] == {"200": 2, "404": 1}


def test_a_timeout_counts_as_broken(check_photo_links, monkeypatch):
    import socket
    import urllib.request

    def slow(*args, **kwargs):
        raise socket.timeout("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", slow)
    assert check_photo_links.head(NEW) == "error"


def test_head_reports_the_http_status(check_photo_links, monkeypatch):
    import urllib.error
    import urllib.request

    def refuse(*args, **kwargs):
        raise urllib.error.HTTPError(NEW, 404, "Not Found", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert check_photo_links.head(NEW) == "404"


def test_no_key_is_not_checked_and_exits_zero(check_photo_links, tmp_path, monkeypatch):
    monkeypatch.delenv("LABELBOX_API_KEY", raising=False)
    out = tmp_path / "p.json"
    assert check_photo_links.main(["--out", str(out)]) == 0
    got = json.loads(out.read_text())
    assert got["status"] == "not checked" and "LABELBOX_API_KEY" in got["reason"]


def test_api_error_is_not_checked_and_exits_zero(check_photo_links, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")

    def boom(key):
        raise ConnectionError("https://signed.example/?token=secret")
    got = check_photo_links.run(str(tmp_path / "p.json"), boom)
    assert got["status"] == "not checked"
    assert "secret" not in json.dumps(got)


def test_missing_dataset_is_not_checked(check_photo_links, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")
    got = check_photo_links.run(str(tmp_path / "p.json"),
                                lambda key: fake_client([OLD], name="renamed"), ok)
    assert got["status"] == "not checked"


def write(tmp_path, record):
    (tmp_path / "photo_links.json").write_text(json.dumps(record), encoding="utf-8")
    return str(tmp_path)


def test_page_warns_when_rows_are_on_the_old_host(queue_panels, tmp_path):
    html = queue_panels.photo_links_note(write(tmp_path, {
        "status": "checked", "total_rows": 5201, "old_host_rows": 3482, "checked": "2026-10-28",
        "old_host": "object-arbutus.cloud.computecanada.ca", "examples": [],
        "broken_rows": 3482, "status_codes": {"403": 3482}}))
    assert "3,482 of 5,201" in html and "blank" in html and "row_data" in html


def test_page_warns_for_broken_rows_on_the_new_host(queue_panels, tmp_path):
    html = queue_panels.photo_links_note(write(tmp_path, {
        "status": "checked", "total_rows": 5201, "old_host_rows": 0, "checked": "2026-10-28",
        "old_host": "h", "examples": [], "broken_rows": 96, "status_codes": {"200": 5105, "404": 96}}))
    assert "96 of 5,201" in html and "404: 96" in html and "suspended" not in html


def test_page_says_nothing_for_zero_or_no_file(queue_panels, tmp_path):
    assert queue_panels.photo_links_note(str(tmp_path)) == ""
    assert queue_panels.photo_links_note("") == ""
    assert queue_panels.photo_links_note(write(tmp_path, {
        "status": "checked", "total_rows": 5201, "old_host_rows": 0, "checked": "2026-10-28",
        "old_host": "h", "examples": [], "broken_rows": 0, "status_codes": {"200": 5201}})) == ""


def test_page_has_a_muted_line_when_not_checked(queue_panels, tmp_path):
    html = queue_panels.photo_links_note(write(tmp_path, {
        "status": "not checked", "reason": "LABELBOX_API_KEY is not set", "checked": "2026-10-28"}))
    assert "not checked" in html and "LABELBOX_API_KEY" in html and "warn" not in html
