#!/usr/bin/env python3
"""Send the next batch of the dashboard's list to the 2024_bci Labelbox project.

For the collaborator who sends batches by hand. One file, no repo checkout: it
reads the published send_batches.csv and asks Labelbox which batches it already
holds, so nobody keeps count. The batch name is the one labelling/rounds.py
defines (batch0001_2026-10), which is how the refresh records a send.

    pip install labelbox
    export LABELBOX_API_KEY=...
    python send_batch.py show       # which batch is next, changes nothing
    python send_batch.py batch      # create it in Labelbox and tag batch_id
    python send_batch.py batch 3    # a given batch instead of the next one

Download: https://raw.githubusercontent.com/traitlab/bci-dashboard/main/bin/send_batch.py
"""

from __future__ import annotations

import csv
import datetime
import io
import os
import re
import sys
import urllib.request

BATCHES_URL = "https://traitlab.github.io/bci-dashboard/send_batches.csv"
PROJECT = DATASET = "2024_bci"
NAME_RE = re.compile(r"^batch(\d{4})_(\d{4}-\d{2})$")  # rounds.BATCH_NAME_RE


def batch_name(n: int, day: datetime.date) -> str:
    return f"batch{n:04d}_{day:%Y-%m}"


def sent_numbers(names) -> dict[int, str]:
    """Batch number -> name, for every batch in the project that is a send."""
    return {int(m[1]): name for name in names if (m := NAME_RE.match(name))}


def pick(batch_ids, sent: dict[int, str], asked: int | None) -> int:
    """The batch to send: the one asked for, or the lowest one not sent yet."""
    if asked is None:
        todo = sorted(set(batch_ids) - set(sent))
        if not todo:
            sys.exit("every batch on the list is already in Labelbox")
        asked = todo[0]
    if asked in sent:
        sys.exit(f"batch {asked} was already sent as {sent[asked]}")
    if asked not in set(batch_ids):
        sys.exit(f"no batch {asked} in {BATCHES_URL}")
    return asked


def main(argv: list[str]) -> None:
    if len(argv) not in (2, 3) or argv[1] not in ("show", "batch"):
        sys.exit(__doc__)
    import labelbox as lb

    client = lb.Client(api_key=os.environ["LABELBOX_API_KEY"])
    rows = list(csv.DictReader(io.StringIO(
        urllib.request.urlopen(BATCHES_URL, timeout=60).read().decode())))
    project = next(p for p in client.get_projects() if p.name == PROJECT)
    sent = sent_numbers(b.name for b in project.batches())
    n = pick([int(r["batch_id"]) for r in rows], sent, int(argv[2]) if len(argv) == 3 else None)
    keys = [r["global_key"] for r in rows if r["batch_id"] == str(n)]
    # The dataset keys a photo by <folder>/<file>, the batch list by file name.
    ds = next(d for d in client.get_datasets() if d.name == DATASET)
    uid = {}
    for r in ds.data_rows():
        uid.setdefault(r.global_key.rsplit("/", 1)[-1], r.uid)
    missing = [k for k in keys if k not in uid]
    if missing:
        sys.exit(f"{len(missing)} photos of batch {n} are not in {DATASET}: {missing[:5]}")
    name = batch_name(n, datetime.datetime.now(datetime.timezone.utc).date())
    if argv[1] == "show":
        again = "batch" if len(argv) == 2 else f"batch {n}"
        print(f"batch {n}: {len(keys)} photos, all in {DATASET}; `{again}` creates {name}")
        return
    batch = project.create_batch(name=name, data_rows=[uid[k] for k in keys])
    mdo = client.get_data_row_metadata_ontology()
    field = mdo.get_by_name("batch_id").uid
    mdo.bulk_upsert([lb.DataRowMetadata(data_row_id=uid[k], fields=[
        lb.DataRowMetadataField(schema_id=field, value=name)]) for k in keys])
    print(f"created {batch.name} with {len(keys)} rows, batch_id set")


if __name__ == "__main__":
    main(sys.argv)
