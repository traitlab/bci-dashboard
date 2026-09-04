"""Stamp the Pl@ntNet project into cached answers that were written without it.

A project is a filter on one classifier, so the same photo gets different names
from different projects. predict/photo.py now records which project answered.
Every answer fetched before it did records nothing, and after a flora switch an
old answer and a new one are the same file on disk: nothing on it says which
flora produced it, so a page pools two populations and cannot see that it did.

This backfills the key. The project it writes is the endpoint that was in force
when those answers were fetched, which is an assumption, not a measurement: no
cached file recorded it and no run log covers every file. So the stamp carries
``project_source: assumed`` beside it, and dashboard/health.py counts recorded
and assumed answers separately. Do not promote one to the other.

Idempotent. An answer that already names a project is left exactly as it is,
including one naming a different project, because overwriting that is how a real
mismatch would be hidden. Nothing else in the file is touched: the key order is
preserved and the ranked names are re-serialised byte-for-byte from what was
read, so a salvaged or truncated payload is skipped rather than rewritten.

    python3 predict/stamp_cache_project.py                          # report only
    python3 predict/stamp_cache_project.py --write
    python3 predict/stamp_cache_project.py --dir data/crowns/cache --write
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _core():
    """dashboard/core.py by path, for the one definition of these key names."""
    path = REPO / "dashboard" / "core.py"
    spec = importlib.util.spec_from_file_location("_dashboard_core", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_dashboard_core"] = mod
    spec.loader.exec_module(mod)
    return mod


def classify(path: Path, core, project: str):
    """-> (verdict, entry). Verdict says what this file needs, and why.

    unreadable   the payload does not parse, so it gets no provenance at all
    already      it names a project, whatever that project is
    stamp        it names none and can carry one
    """
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unreadable", None
    if not isinstance(entry, dict):
        return "unreadable", None
    recorded = core.entry_project(entry)
    if recorded:
        return ("already" if recorded == project else "foreign"), entry
    return "stamp", entry


def stamp(path: Path, entry: dict, core, project: str) -> None:
    """Write the two provenance keys, leaving every other key where it was."""
    entry[core.PROJECT_KEY] = project
    entry[core.PROJECT_SOURCE_KEY] = core.PROJECT_ASSUMED
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(entry), encoding="utf-8")
    tmp.replace(path)


def run(cache_dir: Path, project: str, write: bool, core) -> dict:
    files = sorted(cache_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"no .json answers in {cache_dir}")
    counts = {"stamp": 0, "already": 0, "foreign": 0, "unreadable": 0}
    foreign = []
    for p in files:
        verdict, entry = classify(p, core, project)
        counts[verdict] += 1
        if verdict == "foreign":
            foreign.append((p.name, core.entry_project(entry)))
        if verdict == "stamp" and write:
            stamp(p, entry, core, project)
    print(f"{cache_dir}  {len(files)} answers")
    print(f"  name no project : {counts['stamp']}"
          f"{' (stamped)' if write else ' (would stamp, re-run with --write)'}")
    print(f"  already {project:16}: {counts['already']}")
    print(f"  name another one: {counts['foreign']}")
    print(f"  unreadable      : {counts['unreadable']}")
    for name, other in foreign[:20]:
        print(f"    {name}: {other}")
    return counts


def main():
    core = _core()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=REPO / "data" / "predictions" / "cache",
                    help="cache directory to stamp (default: the photo cache)")
    ap.add_argument("--project", default=core.EVAL_PROJECT,
                    help="project slug to write (default: the one config.yaml names)")
    ap.add_argument("--write", action="store_true",
                    help="write the files; without it nothing is changed")
    args = ap.parse_args()
    run(args.dir, args.project, args.write, core)


if __name__ == "__main__":
    main()
