"""Inventory the Labelbox dataset with a read-only key.

Pages every data row in the ``2024_bci`` dataset and writes one JSON object per
row to ``data/dataset_rows.jsonl``. This is the one network call in the
selection path; everything downstream (``labelling/next_batch.py``) runs offline
against the cached file, the same way the dashboard runs offline against a
project export.

Why paging rather than ``dataset.export()``: a read-only key cannot create an
export task, for a dataset any more than for a project. ``data_rows()`` is a
plain paged read and is permitted. The cost is that embeddings and annotations
are not reachable this way, only identifiers, media attributes, and metadata.

``--project`` switches the same script to the other half of the inventory. A
data row id is only half a deep link: the other half is the project the row
opens in, and a dataset listing cannot say which project any row is in. Only a
project export states both halves, which is why ``data_row_ids.csv`` covers
1,719 of the 3,781 labelled frames: exactly the rows in the one export on disk.
The remaining frames are not unlinkable, their project has simply never been
exported. ``--project`` may be repeated, and each project is written to its own
NDJSON in the shape ``gt_from_export.py`` already reads, so the union of the
exports is what rebuilds the id table.

Read-only in the sense that matters here: nothing is written back to Labelbox,
no label, batch or row is touched. It does start a server-side export task,
which is the one operation in this file a strictly read-only key may be refused
for. Untested against our key. If it is refused, the fallback is the route the
2026-08-06 file arrived by, an export started from the Labelbox UI by someone
with access to that project, and this script's job is then only to say which
projects to ask for.

Usage:
    python labelling/fetch_dataset.py
    python labelling/fetch_dataset.py --dataset-id <id> --out data/other.jsonl
    # the combined dataset the send queue names its frames from:
    python labelling/fetch_dataset.py --dataset-id cmn5chixy005u07846jctibv1 \
        --out data/dataset_rows_combined.jsonl
    python labelling/fetch_dataset.py --project cmbgnzmhu0bed07027vmxezzd \
        --project cme99tjc606h4075147dfd6j6 --out-dir data/exports

Which dataset is read comes from ``LABELBOX_DATASET_ID`` if the environment or
``.env`` carries it, and from ``config.yaml`` otherwise. ``--dataset-id`` beats
both.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date

import labelbox as lb
import settings

OUT_PATH = "data/dataset_rows.jsonl"
EXPORT_DIR = "data/exports"

# What an export has to carry for gt_from_export.py to mint an id and a label
# from it. Deliberately narrow: no attachments, no metadata, no predictions.
# Every extra field is more of the botanists' work leaving Labelbox onto a
# laptop for no gain, and the export is slower for it.
EXPORT_PARAMS = {"data_row_details": True, "project_details": True,
                 "label_details": True, "performance_details": False,
                 "interpolated_frames": False}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset-id", default=None,
                   help="overrides LABELBOX_DATASET_ID and config.yaml")
    p.add_argument("--out", default=OUT_PATH)
    p.add_argument("--project", action="append", default=[], metavar="PROJECT_ID",
                   help="export this project's rows instead of paging the dataset; "
                        "repeat for each project, one NDJSON written per project")
    p.add_argument("--out-dir", default=EXPORT_DIR,
                   help=f"where --project writes its NDJSONs (default: {EXPORT_DIR})")
    return p.parse_args(argv)


def row_to_dict(row) -> dict:
    metadata = {}
    for field in (row.metadata_fields or []):
        metadata[field.get("name")] = field.get("value")
    return {
        "uid": row.uid,
        "global_key": row.global_key,
        "external_id": row.external_id,
        "row_data": row.row_data,
        "media_attributes": row.media_attributes,
        "metadata": metadata,
        "created_at": str(row.created_at),
    }


def export_project(client, project_id: str, out_dir: str) -> str:
    """Write one project's export to ``<out_dir>/export_<project_id>.ndjson``.

    Streamed line by line rather than assembled in memory: an export of a
    labelled project is tens of thousands of rows, and the consumer reads it a
    line at a time anyway. The project id is in the filename because the whole
    point of exporting more than one is that the rows are not interchangeable,
    and a reader who has to open the file to find out which project it is will
    eventually get it wrong.
    """
    project = client.get_project(project_id)
    print(f"project {project.name} ({project.uid}), "
          f"data_row_count={project.data_row_count}")
    task = project.export(params=EXPORT_PARAMS)
    task.wait_till_done()
    if task.has_errors():
        print(f"WARNING: export task for {project_id} reported errors",
              file=sys.stderr)

    os.makedirs(out_dir or ".", exist_ok=True)
    path = os.path.join(out_dir, f"export_{project_id}.ndjson")
    started, written = time.time(), 0
    with open(path, "w") as out:
        for row in task.get_buffered_stream():
            out.write(json.dumps(row.json) + "\n")
            written += 1
            if written % 500 == 0:
                print(f"  {written} rows  {time.time() - started:.0f}s", flush=True)
    print(f"wrote {written} rows to {path} in {time.time() - started:.0f}s")
    return path


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.project:
        client = lb.Client(api_key=settings.api_key())
        for project_id in args.project:
            export_project(client, project_id, args.out_dir)
        print("next: pass every NDJSON to labelling/gt_from_export.py --export, "
              "which unions them into data/data_row_ids.csv")
        return 0

    configured = settings.setting("labelbox", "dataset_id",
                                  env="LABELBOX_DATASET_ID")
    dataset_id = args.dataset_id or configured
    # One dataset per file. `dashboard/core.py` reads every inventory in
    # `data/` by name and the names are what say which dataset each holds, so
    # paging a second dataset over the default file would silently replace one
    # inventory with another and take the deep links of everything only the
    # first one knows with it. A wrong file here is not an error anywhere
    # downstream, which is why it is a stop here.
    if dataset_id != configured and args.out == OUT_PATH:
        sys.exit(f"ERROR: {OUT_PATH} holds dataset {configured}. Pass --out "
                 f"with a name for dataset {dataset_id}, for example "
                 f"data/dataset_rows_<name>.jsonl.")

    client = lb.Client(api_key=settings.api_key())
    dataset = client.get_dataset(dataset_id)
    print(f"dataset {dataset.name} ({dataset.uid}), row_count={dataset.row_count}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    started = time.time()
    written = 0
    with open(args.out, "w") as out:
        for row in dataset.data_rows():
            out.write(json.dumps(row_to_dict(row)) + "\n")
            written += 1
            if written % 500 == 0:
                print(f"  {written} rows  {time.time() - started:.0f}s", flush=True)

    print(f"wrote {written} rows to {args.out} in {time.time() - started:.0f}s")
    # Which dataset this file holds, beside the file. The dump itself never
    # says: a row carries a global key and a URL, not the dataset it came from,
    # and the name of the file is a convention. Two inventories now sit in
    # `data/`, both gitignored, so without this the only way to tell them apart
    # is a live API call. Same idea as gt_dominant_taxon.provenance.txt.
    provenance = os.path.splitext(args.out)[0] + ".provenance.txt"
    with open(provenance, "w", encoding="utf-8") as fh:
        fh.write(f"Paged from Labelbox dataset {dataset.name} ({dataset.uid}) "
                 f"on {date.today().isoformat()}: {written} rows, "
                 f"row_count reported {dataset.row_count}.\n")
    print(f"wrote {provenance}")
    if written != dataset.row_count:
        print(f"WARNING: paged {written} rows but row_count reports "
              f"{dataset.row_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
