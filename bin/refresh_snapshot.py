#!/usr/bin/env python3
"""Rebuild a real cached snapshot offline, or safely pack and unpack its private inputs.

Fetching is deliberately a different command. Explicit --export paths are the
only exports merged; without them the cached Labelbox provenance stays intact.
No credential or network client is read here. All private inputs must live in
this checkout's data/, including the inputs read by the research scripts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "gt_dominant_taxon.csv",
    "gt_dominant_taxon.provenance.txt",
    "splits.csv",
    "publication_final_list.xlsx",
    "export_boxes.csv",
    "dataset_rows.jsonl",
    "dataset_rows_combined.jsonl",
    "wcvp_cache.json",
    "checklist_k-central-america.json",
    "embeddings_labelled/embeddings.npz",
    "embeddings_queue/embeddings.npz",
)
# Beyond REQUIRED_FILES: globs under data/ that the offline build also reads.
# The atlas exporter checks encoder provenance against each per-photo cache.
BUNDLE_EXTRA_GLOBS = ("predictions/cache/*.json", "embeddings_labelled/cache/*.json",
                      "embeddings_queue/cache/*.json", "crownfirst/*.json")
CROWNFIRST_EMBEDDINGS = "crownfirst/plantclef2024_tile2x2_max.json"
PAGES = ("model_health_dashboard.html", "label_queue_dashboard.html")
# Explicit public artifact membership. Adding a public file requires review here.
# Expert labels stay private until publication: the labelling queue, its send
# CSVs and the label review queue are private-tier only, in build/private/.
PUBLIC_FILES = frozenset(
    (
        ".nojekyll",
        "about.html",
        "confidence_calibration.csv",
        "confused_pairs.csv",
        "coverage_gate.csv",
        "crownfirst-atlas.html",
        "embedding-atlas.html",
        "explorer.html",
        "index.html",
        "model_health_dashboard.html",
        "name_reconciliation.csv",
        "per_species_health.csv",
        "refresh_status.json",
        "reject_sweep.csv",
        "scope.csv",
        "support_buckets.csv",
    )
)
# A label column, a recorded label in the embedded page data, or a Labelbox link:
# any of them in a public file means a private-tier build reached docs/.
LABEL_MARKERS = re.compile(
    rb'gt_species|recorded_label|labelbox_url|app\.labelbox\.com'
    rb'|"label":"|"recorded_taxon":"|"annotation_url":"'
)
MAX_BUNDLE_BYTES = 2 * 1024**3
MAX_BUNDLE_MEMBERS = 100_000


def unpack(archive: Path, destination: Path) -> None:
    """Accept regular files beneath data/ only, before writing any archive entry."""
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("bundle destination must be empty")
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if not members or len(members) > MAX_BUNDLE_MEMBERS:
            raise ValueError("input bundle is empty or has too many entries")
        seen = set()
        total = 0
        for member in members:
            path = PurePosixPath(member.name)
            if (
                not path.parts
                or (
                    path.parts[0] != "data"
                    and not (member.name == "input-manifest.json" and member.isfile())
                )
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or not (member.isdir() or member.isfile())
                or (path.parts == ("data",) and not member.isdir())
            ):
                raise ValueError(
                    "bundle must contain only regular files and directories under data/"
                )
            if str(path) in seen:
                raise ValueError("input bundle contains a duplicate path")
            seen.add(str(path))
            total += member.size
            if total > MAX_BUNDLE_BYTES:
                raise ValueError("input bundle exceeds the 2 GiB uncompressed limit")
        verify_bundle_manifest(source, members)
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    source.extractfile(member) as incoming,
                    target.open("xb") as outgoing,
                ):
                    shutil.copyfileobj(incoming, outgoing)
                target.chmod(0o600)


def pack(data: Path, archive: Path) -> None:
    """Write the bundle unpack accepts: a manifest plus the data/ files the build reads."""
    names = {name for name in REQUIRED_FILES}
    for pattern in BUNDLE_EXTRA_GLOBS:
        names.update(
            str(path.relative_to(data)) for path in data.glob(pattern) if path.is_file()
        )
    missing = sorted(n for n in names if not (data / n).is_file())
    if missing:
        raise ValueError("input files missing from --data: " + ", ".join(missing))
    provenance = (data / "gt_dominant_taxon.provenance.txt").read_text(encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "prepared_on": datetime.now(timezone.utc).date().isoformat(),
        "label_source": provenance.strip(),
        "files": {f"data/{n}": digest(data / n) for n in sorted(names)},
    }
    payload = json.dumps(manifest, sort_keys=True, indent=2).encode()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as out:
        header = tarfile.TarInfo("input-manifest.json")
        header.size = len(payload)
        out.addfile(header, io.BytesIO(payload))
        for name in sorted(names):
            out.add(data / name, arcname=f"data/{name}", recursive=False)


def verify_bundle_manifest(source, members) -> None:
    manifests = [m for m in members if m.name == "input-manifest.json"]
    if len(manifests) != 1 or manifests[0].size > 20 * 1024**2:
        raise ValueError("input bundle requires one input-manifest.json")
    with source.extractfile(manifests[0]) as stream:
        manifest = json.load(stream)
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or manifest.get("schema_version") != 1:
        raise ValueError("input manifest must declare schema_version 1 and a files map")
    try:
        date.fromisoformat(manifest["prepared_on"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("input manifest must record its preparation date") from None
    if (
        not isinstance(manifest.get("label_source"), str)
        or not manifest["label_source"].strip()
    ):
        raise ValueError("input manifest must record the source label provenance")
    data_files = {
        str(PurePosixPath(m.name)): m
        for m in members
        if m.isfile() and m.name != "input-manifest.json"
    }
    if set(files) != set(data_files):
        raise ValueError("input manifest files do not match the bundle contents")
    for name, member in data_files.items():
        expected = files[name]
        if not isinstance(expected, str) or not re.fullmatch(
            r"[a-fA-F0-9]{64}", expected
        ):
            raise ValueError("input manifest contains an invalid SHA-256")
        with source.extractfile(member) as stream:
            if _digest(stream) != expected.lower():
                raise ValueError("input bundle file checksum mismatch")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return (
            hashlib.file_digest(source, "sha256").hexdigest()
            if hasattr(hashlib, "file_digest")
            else _digest(source)
        )


def _digest(source) -> str:
    checksum = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        checksum.update(chunk)
    return checksum.hexdigest()


def validate_inputs(repo: Path, exports: list[Path]) -> None:
    missing = [
        name
        for name in REQUIRED_FILES
        if not (repo / "data" / name).is_file()
        or not (repo / "data" / name).stat().st_size
    ]
    cache = repo / "data" / "predictions" / "cache"
    if not cache.is_dir() or not any(cache.glob("*.json")):
        missing.append("predictions/cache/*.json")
    if missing:
        raise ValueError(
            "required real snapshot inputs missing or empty: " + ", ".join(missing)
        )
    for export in exports:
        if not export.is_file() or not export.stat().st_size:
            raise ValueError("an explicit Labelbox export is missing or empty")
    provenance = (repo / "data" / "gt_dominant_taxon.provenance.txt").read_text(
        encoding="utf-8"
    )
    if not re.search(r"\bon (\d{4}-\d{2}-\d{2})\b", provenance) and not exports:
        raise ValueError("cached Labelbox ground truth has no recorded source date")


def validate_export_labels(repo: Path, exports: list[Path]) -> None:
    """Run the real merger's parser and corpus filter before it writes any GT."""
    if not exports:
        return
    merger = runpy.run_path(str(repo / "labelling/gt_from_export.py"))
    with (repo / "data/splits.csv").open(encoding="utf-8", newline="") as source:
        corpus = {row["global_key"] for row in csv.DictReader(source)}
    labelled, *_ = merger["union_exports"](exports)
    rework = merger["rework_frames"](exports)
    prefix = merger["GT_KEY_PREFIX"]
    if not any(prefix + stem in corpus and stem not in rework for stem in labelled):
        raise ValueError("explicit Labelbox exports contain no usable in-corpus labels")


def validate_public_output(directory: Path) -> None:
    """Fail closed without deleting unrecognized files or following links."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("public output must be a regular directory")
    if any(
        path.name not in PUBLIC_FILES or path.is_symlink() or not path.is_file()
        for path in directory.iterdir()
    ):
        raise ValueError(
            "public output contains unexpected files or non-regular entries"
        )
    for path in sorted(directory.iterdir()):
        if LABEL_MARKERS.search(path.read_bytes()):
            raise ValueError(
                f"public output contains a label column or Labelbox link: {path.name}"
            )


def run(repo: Path, script: str, *args: str, env: dict, research: bool = False) -> None:
    command = (
        [sys.executable] + ([] if research else ["-S"]) + [str(repo / script), *args]
    )
    # SDK errors can contain signed asset URLs. Only the separate fetch step
    # talks to Labelbox; this offline command's output contains no API response.
    subprocess.run(command, cwd=repo, env=env, check=True)


def build_atlas_pages(
    repo: Path, data: Path, stage: Path, rendered: Path, *, env: dict, public: bool
) -> None:
    """Rebuild the explorer and embedding atlas from the vectors this run holds.

    ``public`` exports them without recorded labels or Labelbox links.
    """
    work = stage / ("atlas-public" if public else "atlas")
    work.mkdir()
    pca, atlas, catalogue = work / "atlas-pca.json", work / "atlas.json", work / "catalogue.json"
    tier = ("--public",) if public else ()
    root, out = ("--data-root", str(data), *tier), ("--output",)
    labelling = {"research": True, "env": env}
    run(repo, "labelling/export_embedding_atlas.py", *root, *out, str(pca), **labelling)
    run(repo, "labelling/project_atlas_tsne.py", "--atlas", str(pca), "--data", str(data),
        *out, str(atlas), **labelling)
    comparison: list[str] = []
    if (crownfirst := data / CROWNFIRST_EMBEDDINGS).is_file():
        comparison = ["--comparison", str(work / "comparison.json")]
        run(repo, "labelling/compare_embedding_atlases.py", *root,
            "--crownfirst-embeddings", str(crownfirst),
            "--encoder-label", "Crownfirst experiment: PlantCLEF 2024 tile2x2 max",
            *out, comparison[1], **labelling)
    run(repo, "labelling/export_explorer.py", *root, "--plantnet-atlas", str(atlas),
        *out, str(catalogue), **labelling)
    run(repo, "dashboard/build_explorer.py", "--input", str(catalogue),
        *out, str(rendered / "explorer.html"), env=env)
    run(repo, "dashboard/build_embedding_atlas.py", "--input", str(atlas), *comparison,
        "--catalogue", str(catalogue), *out, str(rendered / "embedding-atlas.html"), env=env)


def label_dates(provenance: str) -> tuple[str | None, str | None]:
    """Keep the source export date separate from the later local merge."""
    exported = re.search(r"\bexports? of (\d{4}-\d{2}-\d{2})\b", provenance)
    legacy = re.search(r"(\d{1,2})_(\d{1,2})_(\d{4})", provenance)
    if exported:
        export_date = date.fromisoformat(exported.group(1)).isoformat()
    elif legacy:
        month, day, year = map(int, legacy.groups())
        export_date = date(year, month, day).isoformat()
    else:
        export_date = None
    merged = re.search(r"\bon (\d{4}-\d{2}-\d{2})\b", provenance)
    return export_date, date.fromisoformat(
        merged.group(1)
    ).isoformat() if merged else None


def refresh(
    repo: Path, generated: str, exports: list[Path], export_date: str | None
) -> None:
    date.fromisoformat(generated)
    if exports and not export_date:
        raise ValueError(
            "--export requires --export-date, the actual source export date"
        )
    if export_date:
        date.fromisoformat(export_date)
        if not exports:
            raise ValueError("--export-date requires at least one explicit --export")
    validate_inputs(repo, exports)
    validate_export_labels(repo, exports)
    validate_public_output(repo / "docs")
    data = repo / "data"
    build = repo / "build"
    build.mkdir(parents=True, exist_ok=True)
    snapshots = repo / "snapshots"
    snapshots.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("BCI_")}
    env.update(
        BCI_DASHBOARD_REPO=str(repo),
        BCI_DASHBOARD_DATA=str(data),
        BCI_DASHBOARD_SNAPSHOTS=str(snapshots),
        BCI_WCVP_CACHE=str(data / "wcvp_cache.json"),
    )
    # Validate the reviewed workbook before a merge changes accumulated GT.
    run(repo, "labelling/gt_from_publication.py", "--check", env=env)
    flags = [value for path in exports for value in ("--export", str(path))]
    if exports:
        run(
            repo,
            "labelling/gt_from_export.py",
            *flags,
            "--note",
            f"Ground truth: Labelbox project exports of {export_date}, unreviewed, merged on {generated}.",
            env=env,
        )
    run(repo, "labelling/gt_from_publication.py", env=env)
    # Give every named frame a vector first, so the frames labelled since the
    # bundled embeddings were drawn can anchor. It runs before the assessment,
    # which records the npz it read and fails verification if the npz changes
    # after. The fetch skips what the npz and the per-photo cache already hold.
    run(repo, "labelling/embed_input.py", "--named", *flags, env=env)
    run(
        repo,
        "predict/embed.py",
        "--input",
        str(data / "next_batch" / "labelled_for_embed.csv"),
        "--out-dir",
        str(data / "embeddings_labelled"),
        # One photo takes seconds, so a backlog spans several runs. Each run
        # stops in time to finish, and the restored cache carries the rest.
        "--budget-minutes",
        "60",
        research=True,
        env=env,
    )
    run(repo, "labelling/assess_species.py", research=True, env=env)
    # Re-anchor the send order on every labelled frame, including the pool
    # photos named since the embedding files were drawn.
    run(
        repo,
        "labelling/rank_queue.py",
        "--species-csv",
        str(data / "gt_dominant_taxon.csv"),
        research=True,
        env=env,
    )
    with tempfile.TemporaryDirectory(
        prefix="snapshot-refresh-", dir=build
    ) as temporary:
        stage = Path(temporary)
        rendered = stage / "build"
        rendered.mkdir()
        tables = rendered / "tables"
        env["BCI_DASHBOARD_TABLES"] = str(tables)
        run(repo, "dashboard/measure.py", "--out-dir", str(tables), env=env)
        # The queue page reads this from the tables it verifies against. No ledger
        # yet writes nothing and the page says pending. It is not linked, so not published.
        run(repo, "labelling/read_round.py", "--all", "--out", str(tables / "round_readout.csv"), env=env)
        # Temporary output paths are presentation details, not source provenance.
        # Canonicalize those paths so an identical retry keeps the dated snapshot.
        run_log = tables / "run_log.txt"
        if run_log.is_file():
            run_log.write_text(
                run_log.read_text(encoding="utf-8").replace(
                    str(tables), str(build / "tables")
                ),
                encoding="utf-8",
            )
        # The change log is staged beside the pages and promoted last, so a failed
        # build leaves the recorded history as it was. The pages read this copy.
        source_note = (data / "gt_dominant_taxon.provenance.txt").read_text(
            encoding="utf-8"
        )
        export_source_date, merged_on = label_dates(source_note)
        with (data / "gt_dominant_taxon.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            label_count = sum(1 for _ in csv.DictReader(source))
        recorded_manifest = repo / "history" / "manifest.jsonl"
        staged_manifest = stage / "history" / "manifest.jsonl"
        staged_manifest.parent.mkdir()
        if recorded_manifest.is_file():
            shutil.copy2(recorded_manifest, staged_manifest)
        env["BCI_DASHBOARD_MANIFEST"] = str(staged_manifest)
        sys.path.insert(0, str(REPO / "dashboard"))
        import manifest

        manifest.append(
            str(staged_manifest),
            manifest.entry(
                str(tables),
                run_date=generated,
                export=export_date or export_source_date or generated,
                frames=label_count,
            ),
        )
        published = stage / "docs"
        shutil.copytree(repo / "docs", published)
        # build/ holds the private tier, build/public/ the --public builds.
        public = rendered / "public"
        public.mkdir()
        # The explorer and embedding atlas are rebuilt from this run's vectors.
        # The crownfirst atlas needs an external experiment file, so it is copied.
        names = ["crownfirst-atlas.html"]
        try:
            build_atlas_pages(repo, data, stage, rendered, env=env, public=False)
            build_atlas_pages(repo, data, stage, public, env=env, public=True)
        except subprocess.CalledProcessError as error:
            print(
                f"::warning::atlas pages kept from docs, rebuild failed: {error}",
                flush=True,
            )
            names += ["explorer.html", "embedding-atlas.html"]
        # docs/ is the public tier, so a page kept from it stays public-only.
        for name in names:
            if (published / name).is_file():
                shutil.copy2(published / name, public / name)
        builds = [(script, rendered / name, ()) for script, name in
                  zip(("build_external.py", "build_internal.py"), PAGES)]
        builds.append(("build_external.py", public / PAGES[0], ("--public",)))
        for script, out, tier in builds:
            run(
                repo,
                "dashboard/" + script,
                *tier,
                "--out",
                str(out),
                "--generated",
                generated,
                "--verify-against",
                str(tables),
                env=env,
            )
        # Use the existing publisher against staged public output. Its script
        # locates its root from its own location, so the copies stay isolated
        # until both builds and every linked CSV check have succeeded.
        (stage / "bin").mkdir()
        shutil.copy2(
            repo / "bin" / "publish_pages.sh", stage / "bin" / "publish_pages.sh"
        )
        (stage / "dashboard").symlink_to(repo / "dashboard", target_is_directory=True)
        subprocess.run(
            ["bash", str(stage / "bin" / "publish_pages.sh")],
            cwd=stage,
            env=env,
            check=True,
        )
        status = {
            "snapshot_refreshed": generated,
            "labelbox_export_date": export_source_date,
            "labelbox_merged_on": merged_on,
            "labelbox_exports_merged": bool(exports),
            "labelbox_provenance": source_note.strip(),
            "labelled_frames": label_count,
            "labelbox_gt_sha256": digest(data / "gt_dominant_taxon.csv"),
            "reviewed_workbook_sha256": digest(data / "publication_final_list.xlsx"),
            "reviewed_gt_sha256": digest(data / "gt_publication_reviewed.csv"),
        }
        (published / "refresh_status.json").write_text(
            json.dumps(status, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        # Check staging and the destination again before promoting any output:
        # the publisher or a concurrent process must not add a private artifact.
        validate_public_output(published)
        validate_public_output(repo / "docs")
        snapshot = stage / "snapshot"
        shutil.copytree(tables, snapshot)
        for name in PAGES:
            shutil.copy2(rendered / name, snapshot / name)
        shutil.copy2(
            published / "refresh_status.json", snapshot / "refresh_status.json"
        )
        # A same-day retry can rebuild the pages, but a recorded snapshot is immutable.
        destination = snapshots / ("model-health-" + generated)
        if destination.exists():

            def recorded_digest(path):
                if path.name == "run_log.txt":
                    text = re.sub(
                        re.escape(str(build))
                        + r"/snapshot-refresh-[^/\s]+/build/tables",
                        str(build / "tables"),
                        path.read_text(encoding="utf-8"),
                    )
                    return hashlib.sha256(text.encode("utf-8")).hexdigest()
                return digest(path)

            expected = {
                str(path.relative_to(snapshot)): recorded_digest(path)
                for path in snapshot.rglob("*")
                if path.is_file()
            }
            recorded = {
                str(path.relative_to(destination)): recorded_digest(path)
                for path in destination.rglob("*")
                if path.is_file()
            }
            if expected != recorded:
                raise ValueError(
                    "dated snapshot already exists with different contents; "
                    "existing snapshot and public pages retained"
                )
        else:
            shutil.copytree(snapshot, destination)
        shutil.copytree(
            rendered,
            build,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("snapshot-refresh-*"),
        )
        recorded_manifest.parent.mkdir(exist_ok=True)
        shutil.copy2(staged_manifest, recorded_manifest)
        shutil.copytree(published, repo / "docs", dirs_exist_ok=True)
    print("Snapshot rebuilt from real cached inputs; public output is in docs/.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser(
        "unpack", help="validate and unpack a decrypted private input bundle"
    )
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--destination", type=Path, required=True)
    bundle = subparsers.add_parser(
        "pack", help="write the private input bundle that unpack expects"
    )
    bundle.add_argument("--data", type=Path, required=True)
    bundle.add_argument("--archive", type=Path, required=True)
    build = subparsers.add_parser(
        "build", help="recompute and publish the cached snapshot offline"
    )
    build.add_argument("--repo", type=Path, default=REPO)
    build.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    build.add_argument("--export", type=Path, action="append", default=[])
    build.add_argument("--export-date")
    args = parser.parse_args(argv)
    try:
        if args.command == "unpack":
            unpack(args.archive, args.destination)
        elif args.command == "pack":
            pack(args.data.resolve(), args.archive)
        else:
            refresh(
                args.repo.resolve(),
                args.date,
                [p.resolve() for p in args.export],
                args.export_date,
            )
    except (
        ValueError,
        OSError,
        tarfile.TarError,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(1, f"Snapshot refresh failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
