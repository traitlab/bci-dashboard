"""The scheduled refresh must reject unsafe inputs and retain the last public site on failure."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "refresh_snapshot.py"
spec = importlib.util.spec_from_file_location("refresh_snapshot", SCRIPT)
refresh = importlib.util.module_from_spec(spec)
# bin/ also contains shell scripts; keep an import cache out of that command folder.
previous_bytecode_setting = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    spec.loader.exec_module(refresh)
finally:
    sys.dont_write_bytecode = previous_bytecode_setting


def bundle(path, name, *, kind=None, size=None, files=None):
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        payload = b"real input fixture\n"
        info.size = len(payload) if size is None else size
        if kind is not None:
            info.type = kind
            info.linkname = "/tmp/escape"
            info.size = 0
        archive.addfile(info, io.BytesIO(payload) if info.isfile() else None)
        manifest = {
            "schema_version": 1,
            "prepared_on": "2026-10-16",
            "label_source": "Labelbox fixture on 2026-08-27",
            "files": {name: hashlib.sha256(payload).hexdigest()}
            if files is None
            else files,
        }
        data = json.dumps(manifest).encode()
        header = tarfile.TarInfo("input-manifest.json")
        header.size = len(data)
        archive.addfile(header, io.BytesIO(data))


@pytest.mark.parametrize(
    "name",
    ["../escape", "/data/escape", "docs/index.html", "data/../escape", r"data\escape"],
)
def test_bundle_rejects_paths_outside_private_data_before_writing(tmp_path, name):
    archive, destination = tmp_path / "input.tar.gz", tmp_path / "unpacked"
    bundle(archive, name)
    with pytest.raises(ValueError, match="under data/"):
        refresh.unpack(archive, destination)
    assert not destination.exists()


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_bundle_rejects_links_and_special_files(tmp_path, kind):
    archive, destination = tmp_path / "input.tar.gz", tmp_path / "unpacked"
    bundle(archive, "data/escape", kind=kind)
    with pytest.raises(ValueError, match="regular files"):
        refresh.unpack(archive, destination)
    assert not destination.exists()


def test_bundle_extracts_private_data_with_private_file_permissions(tmp_path):
    archive, destination = tmp_path / "input.tar.gz", tmp_path / "unpacked"
    bundle(archive, "data/nested/input.csv")
    refresh.unpack(archive, destination)
    result = destination / "data/nested/input.csv"
    assert result.read_bytes() == b"real input fixture\n"
    assert result.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="must be empty"):
        refresh.unpack(archive, destination)


@pytest.mark.parametrize(
    "files", [{}, {"data/input.csv": "0" * 64}, {"data/extra.csv": "0" * 64}]
)
def test_bundle_rejects_unlisted_extra_or_corrupted_data_before_extracting(
    tmp_path, files
):
    archive, destination = tmp_path / "input.tar.gz", tmp_path / "unpacked"
    bundle(archive, "data/input.csv", files=files)
    with pytest.raises(ValueError, match="manifest files|checksum mismatch"):
        refresh.unpack(archive, destination)
    assert not destination.exists()


def test_pack_round_trips_through_unpack_and_skips_unused_data(tmp_path):
    data = tmp_path / "data"
    for name in (*refresh.REQUIRED_FILES, "predictions/cache/a.json", "thumbs/t.webp"):
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).write_text(name)
    (data / "gt_dominant_taxon.provenance.txt").write_text(" export of 2026-08-27 \n")
    archive, destination = tmp_path / "input.tar.gz", tmp_path / "unpacked"
    refresh.pack(data, archive)
    refresh.unpack(archive, destination)
    manifest = json.loads((destination / "input-manifest.json").read_text())
    assert manifest["label_source"] == "export of 2026-08-27"
    assert "data/predictions/cache/a.json" in manifest["files"]
    assert not (destination / "data/thumbs").exists()
    for name, checksum in manifest["files"].items():
        assert refresh.digest(destination / name) == checksum


def test_pack_names_missing_inputs_and_writes_nothing(tmp_path):
    (tmp_path / "data").mkdir()
    with pytest.raises(ValueError, match="splits.csv"):
        refresh.pack(tmp_path / "data", tmp_path / "input.tar.gz")
    assert not (tmp_path / "input.tar.gz").exists()


def test_bundle_checks_total_size_before_writing_any_file(tmp_path, monkeypatch):
    archive, destination = tmp_path / "input.tar.gz", tmp_path / "unpacked"
    bundle(archive, "data/input.csv")
    monkeypatch.setattr(refresh, "MAX_BUNDLE_BYTES", 1)
    with pytest.raises(ValueError, match="uncompressed limit"):
        refresh.unpack(archive, destination)
    assert not destination.exists()


def test_missing_real_data_fails_without_touching_published_snapshot(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/index.html").write_text("last verified public snapshot")
    result = invoke(tmp_path)
    assert result.returncode != 0
    assert "required real snapshot inputs missing" in result.stderr
    assert (tmp_path / "docs/index.html").read_text() == "last verified public snapshot"
    assert not (tmp_path / "snapshots").exists()


def invoke(repo, *args):
    return subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            "build",
            "--repo",
            str(repo),
            "--date",
            "2026-10-16",
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "LABELBOX_API_KEY": "must-not-be-used-by-the-build"},
    )


def fixture_repo(root, *, fail_builder=False):
    """Small subprocess stand-ins exercise publication orchestration, not metric formulas."""
    for name in refresh.REQUIRED_FILES:
        path = root / "data" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("cached input")
    (root / "data/gt_dominant_taxon.csv").write_text(
        "global_key,wcvp_canonical_name\ncomb_one.JPG,Hura crepitans\n"
    )
    (root / "data/gt_dominant_taxon.provenance.txt").write_text(
        "Labelbox export merged on 2026-08-27.\n"
    )
    cache = root / "data/predictions/cache"
    cache.mkdir(parents=True)
    (cache / "one.json").write_text("{}")
    for folder in ("bin", "dashboard", "labelling", "predict", "docs"):
        (root / folder).mkdir()
    (root / "docs/index.html").write_text("last verified public snapshot")
    (root / "docs/crownfirst-atlas.html").write_text(
        "old model catalogue, do not restamp"
    )
    (root / "docs/explorer.html").write_text("old photo catalogue, do not restamp")
    shutil.copy2(REPO / "bin/publish_pages.sh", root / "bin/publish_pages.sh")
    (root / "labelling/gt_from_publication.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "if '--check' not in sys.argv: Path('data/gt_publication_reviewed.csv').write_text('reviewed input')\n"
    )
    (root / "labelling/assess_species.py").write_text(
        "from pathlib import Path\nPath('assessment_ran').write_text('recomputed')\n"
    )
    (root / "labelling/embed_input.py").write_text(
        "from pathlib import Path\n"
        "Path('data/next_batch').mkdir(exist_ok=True)\n"
        "Path('data/next_batch/labelled_for_embed.csv').write_text('global_key,image_url\\n')\n"
    )
    (root / "predict/embed.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "assert Path(sys.argv[sys.argv.index('--input')+1]).is_file()\n"
        "out=Path(sys.argv[sys.argv.index('--out-dir')+1]);out.mkdir(exist_ok=True)\n"
        "(out/'embeddings.npz').write_text('vectors for every named frame')\n"
    )
    (root / "labelling/rank_queue.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "labels=Path(sys.argv[sys.argv.index('--species-csv')+1]).read_text()\n"
        "Path('data/next_batch').mkdir(exist_ok=True)\n"
        "Path('data/next_batch/queue_novelty.csv').write_text('ranked after '+labels)\n"
    )
    (root / "dashboard/measure.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "out=Path(sys.argv[sys.argv.index('--out-dir')+1]);out.mkdir()\n"
        "(out/'reference.json').write_text('{}')\n(out/'per_species_health.csv').write_text('species,n\\nHura,1\\n')\n"
        "(out/'run_log.txt').write_text('Recorded source provenance\\nOutput: '+str(out/'reference.json')+'\\n')\n"
    )
    builder = (
        "from pathlib import Path\nimport sys\n"
        "out=Path(sys.argv[sys.argv.index('--out')+1])\n"
        "tables=Path(sys.argv[sys.argv.index('--verify-against')+1])\n"
        "assert (tables/'reference.json').is_file()\n"
        "out.write_text('<html>verified <a href=\"send_batches.csv\">batches</a></html>')\n"
        "(out.parent/'send_batches.csv').write_text('batch_id,global_key\\n1,comb_one.JPG\\n')\n"
        "(out.parent/'label_queue_team.html').write_text('redirect')\n"
    )
    (root / "dashboard/build_external.py").write_text(builder)
    (root / "dashboard/build_internal.py").write_text(
        "raise SystemExit('unverified metrics')\n" if fail_builder else builder
    )
    (root / "dashboard/build_index.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "Path(sys.argv[sys.argv.index('--out')+1]).write_text('freshly verified public snapshot')\n"
    )
    return root


def test_a_failed_metric_gate_retains_all_public_output_and_snapshot(tmp_path):
    fixture_repo(tmp_path, fail_builder=True)
    result = invoke(tmp_path)
    assert result.returncode != 0
    assert "unverified metrics" in result.stderr
    assert (tmp_path / "docs/index.html").read_text() == "last verified public snapshot"
    assert not (tmp_path / "docs/refresh_status.json").exists()
    assert list((tmp_path / "snapshots").iterdir()) == []


def test_success_rebuilds_and_keeps_source_dates_and_standalone_catalogues(tmp_path):
    fixture_repo(tmp_path)
    result = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "assessment_ran").read_text() == "recomputed"
    assert (tmp_path / "data/next_batch/queue_novelty.csv").read_text() == (
        "ranked after global_key,wcvp_canonical_name\ncomb_one.JPG,Hura crepitans\n"
    )
    assert (
        tmp_path / "docs/index.html"
    ).read_text() == "freshly verified public snapshot"
    assert (
        tmp_path / "docs/explorer.html"
    ).read_text() == "old photo catalogue, do not restamp"
    assert (
        tmp_path / "docs/crownfirst-atlas.html"
    ).read_text() == "old model catalogue, do not restamp"
    assert (tmp_path / "docs/send_batches.csv").is_file()
    status = json.loads((tmp_path / "docs/refresh_status.json").read_text())
    assert status["snapshot_refreshed"] == "2026-10-16"
    assert status["labelbox_merged_on"] == "2026-08-27"
    assert status["labelbox_exports_merged"] is False
    assert status["labelled_frames"] == 1
    assert len(status["reviewed_workbook_sha256"]) == 64
    assert "must-not-be-used" not in json.dumps(status)
    snapshot = tmp_path / "snapshots/model-health-2026-10-16"
    assert (snapshot / "reference.json").is_file()
    assert "snapshot-refresh-" not in (snapshot / "run_log.txt").read_text()
    assert (snapshot / "model_health_dashboard.html").is_file()
    # No same-day early exit leaves stale published output behind.
    (tmp_path / "docs/index.html").write_text("corrupted copy")
    repeated = invoke(tmp_path)
    assert repeated.returncode == 0, repeated.stderr
    assert (
        tmp_path / "docs/index.html"
    ).read_text() == "freshly verified public snapshot"


def test_explicit_exports_require_a_source_date(tmp_path):
    fixture_repo(tmp_path)
    export = tmp_path / "export.ndjson"
    export.write_text("{}\n")
    result = invoke(tmp_path, "--export", str(export))
    assert result.returncode != 0
    assert "--export requires --export-date" in result.stderr
    assert not (tmp_path / "assessment_ran").exists()


def test_same_day_changed_inputs_never_overwrite_a_recorded_snapshot(tmp_path):
    fixture_repo(tmp_path)
    result = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    snapshot = tmp_path / "snapshots/model-health-2026-10-16"
    recorded = (snapshot / "refresh_status.json").read_bytes()
    (tmp_path / "data/publication_final_list.xlsx").write_text(
        "a changed reviewed workbook"
    )
    (tmp_path / "docs/index.html").write_text("last published site")
    result = invoke(tmp_path)
    assert result.returncode != 0
    assert "dated snapshot already exists with different contents" in result.stderr
    assert (snapshot / "refresh_status.json").read_bytes() == recorded
    assert (tmp_path / "docs/index.html").read_text() == "last published site"


def test_export_date_is_not_the_later_merge_date():
    note = "Ground truth merged from Labelbox export Export project - 2024_bci - 8_6_2026.ndjson on 2026-08-27."
    assert refresh.label_dates(note) == ("2026-08-06", "2026-08-27")
    note = "Ground truth: Labelbox project exports of 2026-10-16, unreviewed, merged on 2026-10-17."
    assert refresh.label_dates(note) == ("2026-10-16", "2026-10-17")
    assert refresh.label_dates("Undated export merged on 2026-08-27.") == (
        None,
        "2026-08-27",
    )
