"""labelling/fetch_photo_thumbs.py: file names, URL check, inventory rows, resize, resume."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib

import pytest

pytest.importorskip("PIL")
from PIL import Image

PATH = pathlib.Path(__file__).resolve().parents[1] / "labelling" / "fetch_photo_thumbs.py"
spec = importlib.util.spec_from_file_location("fetch_photo_thumbs", PATH)
fpt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fpt)

GOOD = f"https://{fpt.HOST}/a/b.JPG"


def jpeg(w=4000, h=3000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 120, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def test_thumb_name_matches_encode_uri_component():
    assert fpt.thumb_name("comb_a/b c#1.JPG") == "comb_a%2Fb%20c%231.JPG.webp"
    assert "/" not in fpt.thumb_name("x/y")


@pytest.mark.parametrize("url,ok", [
    (GOOD, True),
    (GOOD.replace("https", "http"), False),
    ("https://evil.example/a.jpg", False),
    (f"https://{fpt.HOST}.evil.example/a.jpg", False),
    (None, False),
    ("", False),
])
def test_valid_url(url, ok):
    assert fpt.valid_url(url) is ok


def test_make_thumb_480x360_webp():
    out = Image.open(io.BytesIO(fpt.make_thumb(jpeg(), 480, 75)))
    assert out.format == "WEBP" and out.size == (480, 360)


def test_read_photos_dedupes_and_counts_bad(tmp_path):
    rows = [{"global_key": "k1", "row_data": GOOD}, {"global_key": "k1", "row_data": GOOD},
            {"global_key": "k2", "row_data": "http://x/y"}, {"global_key": "", "row_data": GOOD}]
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    assert fpt.read_photos(path) == ({"k1": GOOD}, 1)


def test_second_run_skips(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fpt, "download", lambda url: calls.append(url) or jpeg())
    assert fpt.fetch_one("k/1", GOOD, tmp_path, 480, 75) > 0
    assert (tmp_path / "k%2F1.webp").exists() and not list(tmp_path.glob("*.tmp"))
    assert fpt.fetch_one("k/1", GOOD, tmp_path, 480, 75) == 0
    assert len(calls) == 1


PAGE = '<script id="{id}" type="application/json">{data}</script>'


def write_pages(docs, explorer_keys, atlas_keys=()):
    docs.mkdir(exist_ok=True)
    (docs / "explorer.html").write_text(PAGE.format(
        id="explorer-data", data=json.dumps({"photos": [{"key": k} for k in explorer_keys]})))
    (docs / "embedding-atlas.html").write_text(PAGE.format(
        id="atlas-data", data=json.dumps({"points": [{"key": k} for k in atlas_keys]})))


def rows_file(tmp_path, keys):
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps({"global_key": k, "row_data": GOOD}) for k in keys))
    return path


def test_page_keys_reads_every_page_present(tmp_path):
    write_pages(tmp_path / "docs", ["a", "b"], ["b", "c"])
    assert fpt.page_keys(tmp_path / "docs") == {"a", "b", "c"}
    assert fpt.page_keys(tmp_path / "nothing") == set()


def test_pages_run_fills_only_the_gaps_and_passes_when_none_remain(tmp_path, monkeypatch):
    write_pages(tmp_path / "docs", ["have", "gap"])
    out = tmp_path / "docs" / "thumbs"
    out.mkdir(parents=True)
    (out / "have.webp").write_bytes(b"x")
    calls = []
    monkeypatch.setattr(fpt, "download", lambda url: calls.append(url) or jpeg(40, 30))
    args = ["--rows", str(rows_file(tmp_path, ["have", "gap", "unshown"])), "--out", str(out),
            "--pages", str(tmp_path / "docs"), "--failures", str(tmp_path / "f.txt"), "--workers", "1"]
    assert fpt.main(args) == 0
    assert len(calls) == 1 and (out / "gap.webp").exists() and not (out / "unshown.webp").exists()


def test_pages_run_fails_while_a_page_photo_has_no_thumbnail(tmp_path, monkeypatch):
    write_pages(tmp_path / "docs", ["gap", "not-in-rows"])
    out = tmp_path / "thumbs"
    monkeypatch.setattr(fpt, "download", lambda url: jpeg(40, 30))
    args = ["--rows", str(rows_file(tmp_path, ["gap"])), "--out", str(out),
            "--pages", str(tmp_path / "docs"), "--failures", str(tmp_path / "f.txt"), "--workers", "1"]
    assert fpt.main(args) == 1
    assert (out / "gap.webp").exists() and not (out / "not-in-rows.webp").exists()
