"""Count the 2024_bci data rows whose photo still points at the suspended host.

Labelbox loads a photo from ``row_data``. Rows left on
``object-arbutus.cloud.computecanada.ca`` (the suspended lefolab account) show
labellers a blank frame, and nothing else in the refresh notices. This pages the
dataset with the read-only key, counts those rows, HEADs every row's photo anonymously and counts what does not
answer 200 (a host-only check misses a folder renamed on the new host), and writes
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
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlparse

DATASET_NAME = "2024_bci"
OLD_HOST = "object-arbutus.cloud.computecanada.ca"
OUT_PATH = "data/photo_links.json"
EXAMPLES = 5
WORKERS = 32
TIMEOUT = 60


def head(url: str) -> str:
    """The status an anonymous HEAD gets, or "error" when nothing answers."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=TIMEOUT) as r:
            return str(r.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception:  # timeout, DNS, TLS: the labeller sees a blank frame either way
        return "error"


def count(rows, probe=head) -> dict:
    rows = [(r.global_key, r.row_data or "") for r in rows]
    old = [k for k, u in rows if urlparse(u).hostname == OLD_HOST]
    with ThreadPoolExecutor(WORKERS) as pool:
        codes = list(pool.map(lambda r: probe(r[1]) if r[1] else "no row_data", rows))
    tally = Counter(codes)
    broken = [k for (k, _), c in zip(rows, codes) if c != "200"]
    return {"status": "checked", "total_rows": len(rows), "old_host_rows": len(old),
            "old_host": OLD_HOST, "examples": old[:EXAMPLES],
            "broken_rows": len(broken), "broken_examples": broken[:EXAMPLES],
            "status_codes": dict(sorted(tally.items()))}


def dataset_rows(client):
    """The rows of the one dataset named `2024_bci`, paged by the SDK."""
    datasets = [d for d in client.get_datasets() if d.name == DATASET_NAME]
    if len(datasets) != 1:
        raise LookupError(f"{len(datasets)} datasets named {DATASET_NAME}, expected 1")
    return datasets[0].data_rows()


def check(client, probe=head) -> dict:
    return count(dataset_rows(client), probe)


def make_client(key):
    import labelbox as lb
    return lb.Client(api_key=key)


def run(out: str, client_factory=make_client, probe=head) -> dict:
    try:
        key = os.environ.get("LABELBOX_API_KEY")
        if not key:
            raise RuntimeError("LABELBOX_API_KEY is not set")
        result = check(client_factory(key), probe)
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
        print(f"{result['old_host_rows']:,} of {result['total_rows']:,} rows are on {OLD_HOST}; "
              f"{result['broken_rows']:,} do not answer 200 {result['status_codes']}")
    else:
        print(f"photo links not checked: {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
