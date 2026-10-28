"""Count the 2024_bci data rows whose photo still points at the suspended host.

Labelbox loads a photo from ``row_data``. Rows left on
``object-arbutus.cloud.computecanada.ca`` (the suspended lefolab account) show
labellers a blank frame, and nothing else in the refresh notices. This pages the
dataset with the read-only key, counts those rows and writes
``data/photo_links.json`` for the build to copy into the tables, so the queue
page can say so. The page build itself makes no network call.

Strictly read-only: no Labelbox write call. It never fails the refresh. With no
key, no SDK or an API error it writes the file with status "not checked" and the
reason, and exits 0.

    LABELBOX_API_KEY=... python labelling/check_photo_links.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from urllib.parse import urlparse

DATASET_NAME = "2024_bci"
OLD_HOST = "object-arbutus.cloud.computecanada.ca"
OUT_PATH = "data/photo_links.json"
EXAMPLES = 5


def count(rows) -> dict:
    total, old, examples = 0, 0, []
    for row in rows:
        total += 1
        if urlparse(row.row_data or "").hostname == OLD_HOST:
            old += 1
            if len(examples) < EXAMPLES:
                examples.append(row.global_key)
    return {"status": "checked", "total_rows": total, "old_host_rows": old,
            "old_host": OLD_HOST, "examples": examples}


def check(client) -> dict:
    datasets = [d for d in client.get_datasets() if d.name == DATASET_NAME]
    if len(datasets) != 1:
        raise LookupError(f"{len(datasets)} datasets named {DATASET_NAME}, expected 1")
    return count(datasets[0].data_rows())


def make_client(key):
    import labelbox as lb
    return lb.Client(api_key=key)


def run(out: str, client_factory=make_client) -> dict:
    try:
        key = os.environ.get("LABELBOX_API_KEY")
        if not key:
            raise RuntimeError("LABELBOX_API_KEY is not set")
        result = check(client_factory(key))
    except Exception as exc:  # never fail the refresh
        # The class name only: SDK messages can carry signed URLs or the key.
        reason = str(exc) if isinstance(exc, (RuntimeError, LookupError)) else type(exc).__name__
        result = {"status": "not checked", "reason": reason}
    result["checked"] = date.today().isoformat()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
        fh.write("\n")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT_PATH)
    result = run(ap.parse_args(argv).out)
    if result["status"] == "checked":
        print(f"{result['old_host_rows']:,} of {result['total_rows']:,} rows are on {OLD_HOST}")
    else:
        print(f"photo links not checked: {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
