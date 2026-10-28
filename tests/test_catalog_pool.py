"""The catalog pool rebuilt from the dataset (`labelling/catalog_pool.py`).

A fake client stands in for Labelbox and a stub for Pl@ntNet: nothing here reaches the
network or reads a credential.

    .venv/bin/pytest tests/test_catalog_pool.py
"""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

BUNDLED = "global_key,image_url\nold.JPG,https://old/old.JPG\n"

ROWS = [("f1/sent.JPG", "https://new/f1/sent.JPG"),   # in a project: out
        ("f2/new.JPG", "https://new/f2/new.JPG"),     # new dataset row: in, keyed by file name
        ("f3/new.JPG", "https://new/f3/new.JPG"),     # same file name again: first one kept
        ("f2/blank.JPG", "")]                         # no photo to show: out


@pytest.fixture(scope="module")
def catalog_pool():
    from conftest import REPO, _on_path, load
    with _on_path(REPO / "labelling"):
        return load("_catalog_pool_under_test", REPO / "labelling" / "catalog_pool.py")


def fake_client(rows, name="2024_bci"):
    rows = [SimpleNamespace(global_key=k, row_data=u) for k, u in rows]
    dataset = SimpleNamespace(name=name, data_rows=lambda: iter(rows))
    return lambda key: SimpleNamespace(get_datasets=lambda: iter([dataset]))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "k")
    export = tmp_path / "01_x.ndjson"
    export.write_text(json.dumps({"data_row": {"id": "r1", "global_key": "f1/sent.JPG"}}) + "\n\n")
    pool_dir = tmp_path / "pool"
    pool_dir.mkdir()
    (pool_dir / "input.csv").write_text(BUNDLED)
    return pool_dir, [export]


def read(pool_dir):
    with open(pool_dir / "input.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_pool_is_dataset_rows_in_no_project(catalog_pool, setup):
    pool_dir, exports = setup
    asked = []
    assert catalog_pool.run(pool_dir, exports, fake_client(ROWS), fetch=asked.append)
    assert read(pool_dir) == [{"global_key": "new.JPG", "image_url": "https://new/f2/new.JPG"}]
    assert asked == [pool_dir]


@pytest.mark.parametrize("why", ["no key", "no export", "empty listing", "api error", "wrong dataset"])
def test_failure_keeps_the_bundled_pool(catalog_pool, setup, monkeypatch, capsys, why):
    pool_dir, exports = setup
    client = fake_client(ROWS)
    if why == "no key":
        monkeypatch.delenv("LABELBOX_API_KEY")
    elif why == "no export":
        exports = []
    elif why == "empty listing":
        client = fake_client([])
    elif why == "wrong dataset":
        client = fake_client(ROWS, name="other")
    else:
        def client(key):
            raise ConnectionError("https://signed.example/?sig=secret")
    assert not catalog_pool.run(pool_dir, exports, client, fetch=lambda d: pytest.fail("fetched"))
    out = capsys.readouterr().out
    assert "kept the bundled snapshot" in out and "secret" not in out
    assert (pool_dir / "input.csv").read_text() == BUNDLED


def test_cached_photos_are_not_asked_again(tmp_path):
    """photo.py's own skip, on the file the pool writes: only the uncached name is outstanding."""
    from conftest import REPO, _on_path, load
    with _on_path(REPO / "predict"):
        photo = load("_photo_under_test", REPO / "predict" / "photo.py")
    (tmp_path / "input.csv").write_text("global_key,image_url\na.JPG,u\nb.JPG,v\n")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "a.JPG.json").write_text("{}")
    cached, todo = photo.outstanding(photo.load_image_list(tmp_path / "input.csv"),
                                     tmp_path / "cache", 10)
    assert [r["global_key"] for r in todo] == ["b.JPG"] and len(cached) == 1


def test_logged_photo_errors_name_no_url_or_key():
    """The pool's Pl@ntNet run logs in public CI: an error keeps its type and status only."""
    import requests
    from conftest import REPO, _on_path, load
    with _on_path(REPO / "predict"):
        photo = load("_photo_under_test", REPO / "predict" / "photo.py")
    gone = requests.ConnectionError("HTTPSConnectionPool(host='h', port=443): Max retries "
                                    "exceeded with url: /v2/identify/all?api-key=SECRET")
    answer = requests.Response()
    answer.status_code = 404
    missing = requests.HTTPError("404 for url: https://h/bucket/f.JPG", response=answer)
    assert (photo.log_reason(gone), photo.log_reason(missing)) == ("ConnectionError", "HTTPError 404")
