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
