"""List the batches of 2024_bci as Labelbox shows them now, for the send record.

The weekly export names a hand-sent batch only after it lands, up to a week late.
`project.batches()` answers at once, with each batch's name and size, so
`record_sends.py` can record a batch whose pinned frames match that size. Writes
``data/live_batches.json`` for the build to read; the build itself makes no
network call.

Strictly read-only: no Labelbox write call. It never fails the refresh. With no
key, no SDK or an API error it writes the file with status "not checked" and the
reason, and exits 0.

    LABELBOX_API_KEY=... python labelling/fetch_live_batches.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

PROJECT_ID = "cmp375mkq0dhr07w92diwbmuh"  # 2024_bci
OUT_PATH = "data/live_batches.json"
KNOWN = (ImportError, OSError, ValueError, KeyError, RuntimeError, LookupError)


def make_client(key):
    import labelbox as lb
    return lb.Client(api_key=key)


def run(out: str, client_factory=make_client) -> dict:
    try:
        from lbox.exceptions import LabelboxError
        known = (*KNOWN, LabelboxError)
    except ImportError:  # no SDK: the client import below reports it
        known = KNOWN
    try:
        key = os.environ.get("LABELBOX_API_KEY")
        if not key:
            raise RuntimeError("LABELBOX_API_KEY is not set")
        project = client_factory(key).get_project(PROJECT_ID)
        result = {"status": "checked",
                  "batches": [{"name": b.name, "size": b.size} for b in project.batches()]}
    except known as exc:  # never fail the refresh
        # The class name only: SDK messages can carry signed URLs or the key.
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        result = {"status": "not checked", "reason": reason}
    result["checked"] = datetime.now(timezone.utc).date().isoformat()
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
        print(f"{len(result['batches'])} live batches in 2024_bci")
    else:
        print(f"live batches not checked: {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
