"""The offline publication path includes the catalogue browser, not its raw data."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("already_published", [False, True])
def test_publication_keeps_explorers_discoverable_without_raw_exports(tmp_path, already_published):
    (tmp_path / "bin").mkdir()
    (tmp_path / "dashboard").mkdir()
    build = tmp_path / "build"
    build.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    shutil.copy2(ROOT / "bin/publish_pages.sh", tmp_path / "bin/publish_pages.sh")
    for name in ("build_index.py", "site_navigation.py"):
        shutil.copy2(ROOT / "dashboard" / name, tmp_path / "dashboard" / name)
    operational = ["model_health_dashboard.html", "label_queue_dashboard.html", "label_queue_team.html"]
    explorers = ["explorer.html", "embedding-atlas.html", "crownfirst-atlas.html"]
    expected = {name: "<!doctype html><h1>" + name + "</h1>" for name in operational + explorers}
    for name, content in expected.items():
        destination = docs if already_published and name in explorers else build
        (destination / name).write_text(content)
    (build / "explorer.json").write_text('{"raw":true}')
    (build / "embeddings.npz").write_bytes(b"raw matrix fixture")

    subprocess.run(["bash", str(tmp_path / "bin/publish_pages.sh")], check=True,
                   capture_output=True, text=True)

    for name, content in expected.items():
        assert (docs / name).read_text() == content
    assert not (docs / "explorer.json").exists()
    assert not (docs / "embeddings.npz").exists()
    index = (docs / "index.html").read_text()
    assert index.index('href="explorer.html"') < index.index('href="model_health_dashboard.html"')
    assert 'href="embedding-atlas.html"' in index
    assert 'href="crownfirst-atlas.html#view=models"' in index
