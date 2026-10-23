"""Synthetic observations for the real offline measurement and page commands.

No private table is copied. Twenty-eight Hura frames have 22 correct top predictions,
four Ceiba frames have two, and one Swartzia frame has no name in the cache's
vocabulary. A genus label and an unreviewed label exercise population boundaries.
The three queued frames cover long-tail, normal and can-wait queues.
These facts are the oracle, independent of the generated measurement tables.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPECIES = ("Hura crepitans", "Ceiba pentandra", "Swartzia simplex")
GENERATED = "2026-10-14"


def write_csv(path, rows, fieldnames) -> None:
    # Reuse the established snapshot serializer without leaving the script
    # directory on sys.path for later tests.
    entry = str(REPO / "dashboard")
    sys.path.insert(0, entry)
    try:
        from snapshot_harness import write_csv as write
    finally:
        sys.path.remove(entry)
    write(path, rows, fieldnames)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def command(root: Path, script: str, *flags: str) -> subprocess.CompletedProcess[str]:
    # -S hides site-packages, including pytest and every predict dependency.
    # core's supported path overrides isolate all reads from the host checkout.
    env = {k: v for k, v in os.environ.items() if not k.startswith("BCI_")}
    env.update(
        BCI_DASHBOARD_REPO=str(root),
        BCI_DASHBOARD_DATA=str(root / "data"),
        BCI_DASHBOARD_TABLES=str(root / "tables"),
        BCI_DASHBOARD_SNAPSHOTS=str(root / "snapshots"),
        BCI_WCVP_CACHE=str(root / "data" / "wcvp_cache.json"),
    )
    return subprocess.run(
        [sys.executable, "-S", str(REPO / "dashboard" / script), *flags],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def build(root: Path, script: str, name: str) -> subprocess.CompletedProcess[str]:
    return command(
        root,
        script,
        "--generated",
        GENERATED,
        "--out",
        str(root / "pages" / name),
        "--verify-against",
        str(root / "tables"),
    )


def write_inputs(root: Path) -> Path:
    data = root / "data"
    cache = data / "predictions" / "cache"
    cache.mkdir(parents=True)
    (root / "input" / "boxes").mkdir(parents=True)
    (root / "snapshots").mkdir()
    (root / "pages").mkdir()
    (root / "config.yaml").write_text(
        "labelbox:\n  link_project: legacy\n", encoding="utf-8"
    )
    write_json(data / "wcvp_cache.json", {})
    labels, splits, boxes, inventory, ids, mechanisms = [], [], [], [], [], {}

    def frame(stem, gt, first, *, score=0.95, split=None, reviewed=True, partial=False):
        key = "comb_" + stem + ".JPG"
        names = [first] if first else []
        if first:
            names += [
                n
                for n in (
                    SPECIES[0],
                    SPECIES[1],
                    "Inga edulis",
                    "Ficus insipida",
                    "Annona glabra",
                )
                if n != first
            ]
        write_json(
            cache / (stem + ".JPG.json"),
            {
                "results": {
                    "species": [
                        {
                            "binomial": n,
                            "max_score": score if i == 0 else 0.01,
                            "coverage": score if i == 0 else 0.01,
                        }
                        for i, n in enumerate(names[:5])
                    ]
                }
            },
        )
        splits.append(
            {
                "global_key": key,
                "split": split if split is not None else ("train" if gt else ""),
            }
        )
        inventory.append(
            {
                "global_key": key,
                "row_data": "https://example.invalid/20261014_sitea_waypoint_aircraft/"
                + stem,
                "metadata": {
                    "original_labelbox_url": f"https://app.labelbox.com/projects/legacy-{len(splits) % 2}/data-rows/{stem}"
                },
            }
        )
        ids.append({"global_key": key, "data_row_id": stem, "project_id": "dispatch"})
        if gt:
            labels.append(
                {
                    "global_key": key,
                    "wcvp_canonical_name": gt,
                    "label_source": "publication_reviewed"
                    if reviewed
                    else "labelbox_unreviewed",
                    "labelbox_name": gt,
                }
            )
            boxes.append(
                {
                    "base_image": stem + ".JPG",
                    "lb_label": gt,
                    "x_min": 1360,
                    "y_min": 860,
                    "x_max": 1680 if partial else 2640,
                    "y_max": 2140,
                }
            )
            if first and first != gt:
                mechanisms[key] = {"mechanism": "species_conflict"}

    for i in range(28):
        frame(
            f"hura_{i:02}_zoom",
            SPECIES[0],
            SPECIES[0] if i < 22 else SPECIES[1],
            split="test" if i % 3 == 0 else "train",
            partial=i == 0,
        )
    for i in range(4):
        frame(
            f"ceiba_{i:02}_zoom",
            SPECIES[1],
            SPECIES[1] if i < 2 else SPECIES[0],
            split="test" if i % 2 == 0 else "train",
        )
    frame("swartzia_zoom", SPECIES[2], SPECIES[0], split="test", partial=True)
    frame("genus_zoom", "Inga", "Inga edulis")
    frame("unreviewed_zoom", SPECIES[1], SPECIES[1], reviewed=False)
    frame("queued_rare_tele", None, "Inga edulis")
    frame("queued_low_zoom", None, SPECIES[0], score=0.3)
    frame("queued_normal_tele", None, SPECIES[0])
    frame("no_answer_zoom", None, None)
    frame("held_test_zoom", None, SPECIES[0], split="test")

    write_csv(data / "gt_publication_reviewed.csv", labels, list(labels[0]))
    write_csv(data / "gt_dominant_taxon.csv", labels, list(labels[0]))
    (data / "gt_dominant_taxon.provenance.txt").write_text(
        "export 10_14_2026\n", encoding="utf-8"
    )
    write_csv(data / "splits.csv", splits, ["global_key", "split"])
    write_csv(data / "export_boxes.csv", boxes, list(boxes[0]))
    write_csv(
        root / "input" / "boxes" / "crop_bounding_boxes.csv", boxes, list(boxes[0])
    )
    write_csv(data / "data_row_ids.csv", ids, list(ids[0]))
    write_csv(
        root / "input" / "growth_form.csv",
        [{"species": s.lower(), "growth_form": "tree"} for s in SPECIES],
        ["species", "growth_form"],
    )
    (data / "dataset_rows_combined.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in inventory), encoding="utf-8"
    )
    next_batch = data / "next_batch"
    next_batch.mkdir()
    write_csv(
        next_batch / "queue_novelty.csv",
        [
            {
                "global_key": "comb_queued_rare_tele.JPG",
                "novelty_rank": 1,
                "distance_to_nearest_labelled": 0.9,
            },
            {
                "global_key": "comb_queued_low_zoom.JPG",
                "novelty_rank": 2,
                "distance_to_nearest_labelled": 0.7,
            },
            {
                "global_key": "comb_queued_normal_tele.JPG",
                "novelty_rank": 3,
                "distance_to_nearest_labelled": 0.4,
            },
        ],
        ["global_key", "novelty_rank", "distance_to_nearest_labelled"],
    )
    write_json(
        next_batch / "queue_novelty.csv.run.json",
        {
            "n_labeled": 34,
            "n_pool": 3,
            "library_version": "synthetic",
            "embedding_sha256": "synthetic-not-an-embedding",
            "extra": {"written": GENERATED},
        },
    )
    sha = hashlib.sha256(
        (data / "gt_publication_reviewed.csv").read_bytes()
    ).hexdigest()
    common = {"inputs": {"gt_sha256": sha}, "library": {"crownfirst": "synthetic"}}
    documents: dict[str, dict] = {
        "transductive.json": {
            "population": {"n_frames": 33, "n_species": 3, "n_seeds": 8},
            "method": {"k": 5},
            "per_species": {
                SPECIES[0].lower(): {
                    "n_frames": 28,
                    "limit": "resolved",
                    "seeds_agreeing": 8,
                }
            },
        },
        "disagreement.json": {
            "population": {
                "n_conflicts": len(mechanisms),
                "n_flagged": len(mechanisms),
            },
            "frames": mechanisms,
            "method": {"synonyms_from": "synthetic", "habit_source": None},
        },
        "reject_sweep.json": {
            "population": {"n_frames": 33, "n_species": 3},
            "method": {"n_folds": 2, "alpha": 0.1},
            "rows": [
                {
                    "max_set_size": 1,
                    "n_accepted": 8,
                    "accept_rate": 8 / 33,
                    "accepted_accuracy": 0.75,
                }
            ],
            "grouped_rows": [
                {"n_accepted": 6, "accept_rate": 6 / 33, "accepted_accuracy": 0.5}
            ],
        },
        "status.json": {
            "population": {"n_species_level": 34, "n_labelled": 35},
            "richness": {
                "observed": 3,
                "singletons": 1,
                "doubletons": 0,
                "unseen_estimate": 0,
                "completeness": 1.0,
            },
        },
    }
    for name, fields in documents.items():
        write_json(data / "model_health" / name, {**common, **fields})
    return root


def measure(root: Path) -> subprocess.CompletedProcess[str]:
    return command(root, "measure.py", "--out-dir", str(root / "tables"))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    root = write_inputs(args.destination)
    proc = measure(root)
    print(proc.stdout, end="")
    if proc.returncode:
        raise SystemExit(proc.stderr)
    for script, name in (
        ("build_external.py", "model_health_dashboard.html"),
        ("build_internal.py", "label_queue_dashboard.html"),
    ):
        proc = build(root, script, name)
        print(proc.stdout, end="")
        if proc.returncode:
            raise SystemExit(proc.stderr)


if __name__ == "__main__":
    main()
