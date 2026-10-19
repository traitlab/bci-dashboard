"""Card and strip images load the small WebP and fall back to the original once; large frames keep the original."""

import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest
from test_atlas_mission_view import photo, run_atlas
from test_explorer_browser import run_browser

ROOT = Path(__file__).resolve().parents[1]
KEY = "comb_a/b c#1 !'()*é.JPG"


def thumb_fn(page):
    html = runpy.run_path(ROOT / "dashboard" / page)["HTML"]
    return re.search(r"function thumbSrc\(p\)\{[^\n]*\}", html).group()


def test_explorer_cards_use_thumbnail_lazily_and_fall_back_once():
    run_browser(r"""
const grid=$('gallery').children[0].children[0].children[1],url='https://example.org/a & ä /?.JPG.jpg';
assert.equal(grid.src,'thumbs/480/'+encodeURIComponent('a & ä /?.JPG')+'.webp');
assert.equal(grid.loading,'lazy');assert.equal(grid.decoding,'async');assert.equal(grid.width,480);assert.equal(grid.height,360);
grid.onerror();assert.equal(grid.src,url);assert.equal(grid.hidden,false);
grid.onerror();assert.equal(grid.hidden,true);assert.equal(grid.src,url);
setState({frame:'b'});assert.equal($('selectedImage').src,'https://example.org/b.jpg');

""")


def test_explorer_table_thumbnail_uses_thumbnail_and_falls_back_once():
    run_browser(r"""
const t=$('evidenceRows').children[0].children[0].children[0].children[1];
assert.equal(t.src,'thumbs/480/'+encodeURIComponent('a & ä /?.JPG')+'.webp');assert.equal(t.loading,'lazy');assert.equal(t.height,360);
t.onerror();assert.match(t.src,/^https:/);t.onerror();assert.equal(t.hidden,true);
""", initial_hash='#layout=table')


def test_explorer_enlarged_frames_keep_the_original():
    html = runpy.run_path(ROOT / "dashboard/explorer_assets.py")["HTML"]
    assert html.count("src=thumbSrc(p)") == 2
    assert "image.src=p.image}" in html and "image.src=p.image;$('detailViewport')" in html


def test_atlas_cards_strip_and_shared_use_thumbnail_and_fall_back_once():
    run_atlas([photo("query", "flight-a", [[1, .9]]), photo("one", "flight-b")], r"""
const p=P[1],url=p.image;
const card=browsePhotoButton(p,false,false,()=>{}).children[0].children[0];
assert.equal(card.src,'thumbs/480/one.webp');assert.equal(card.loading,'lazy');assert.equal(card.decoding,'async');assert.equal(card.width,400);
card.onerror();assert.equal(card.src,url);assert.equal(card.hidden,undefined);card.onerror();assert.equal(card.hidden,true);
const strip=similarPhotoButton(p,.9,()=>{}).children[0];
assert.equal(strip.getAttribute('data-src'),'thumbs/480/one.webp');assert.equal(strip.loading,'lazy');assert.equal(strip.width,64);
strip.onerror();assert.equal(strip.src,url);strip.onerror();assert.equal(strip.hidden,true);
""")


def test_atlas_other_card_sites_and_large_frames():
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    assert html.count("src=thumbSrc(") == 3 and html.count("thumbSrc(photo));") == 1
    # preview and shared cards fall back once to the original; the large frame loads it directly.
    assert "image.fb=1;image.src=meta.image" in html and "image.fb=1;image.src=photo.image" in html
    assert "image.src=p.image;" in html and "naturalWidth" in html


@pytest.mark.parametrize("page", ["explorer_assets.py", "embedding_atlas_assets.py"])
def test_thumb_src_matches_the_script_file_name(page):
    if not shutil.which("node"):
        pytest.skip("Node is needed to run thumbSrc")
    import importlib.util
    spec = importlib.util.spec_from_file_location("fpt", ROOT / "labelling/fetch_photo_thumbs.py")
    fpt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fpt)
    out = subprocess.run(["node", "-e", thumb_fn(page) + "\nprocess.stdout.write(thumbSrc({key:process.argv[1]}))", KEY],
                         capture_output=True, text=True, check=True).stdout
    assert out == "thumbs/480/" + fpt.thumb_name(KEY)
