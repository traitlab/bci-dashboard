"""Where each drone mission's photos live on private new Arbutus.

The frame URLs in the data still carry the legacy public form,
``https://<legacy host>/<mission>/<flight>/<file>``, optionally with a
``lefolab_drone_missions_wpt/`` folder in front. The photos were copied to two
private buckets as ``drone_missions/<year>/<mission>/<flight>/<file>``, and the
mission alone says which bucket. That mapping is ``input/mission_buckets.csv``, listed
off the buckets by ``bin/refresh_mission_buckets.py`` and committed, so building
a page needs no credential and no network call.

A mission the table does not name raises ``UnknownMission``. There is no
fallback to a guessed bucket: a wrong guess is a 404 at download time, or a
dead link in the send file in front of a botanist.

Stdlib only, because dashboard/ is, and predict/photo.py reuses it.
"""

import csv
from functools import cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

LEGACY_HOST = "object-arbutus.cloud.computecanada.ca"
LEGACY_PREFIX = "lefolab_drone_missions_wpt/"
TABLE = Path(__file__).resolve().parents[1] / "input" / "mission_buckets.csv"


class UnknownMission(LookupError):
    """A legacy URL names a mission absent from mission_buckets.csv."""


@cache
def load_table(path: Path = TABLE) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["mission"]: r["bucket"] for r in csv.DictReader(f)}


def locate(url: str, path: Path = TABLE) -> tuple[str, str] | None:
    """(bucket, key) of a legacy-host URL's photo, None for any other URL."""
    parts = urlsplit(url)
    if parts.hostname != LEGACY_HOST:
        return None
    rel = unquote(parts.path).lstrip("/").removeprefix(LEGACY_PREFIX)
    mission = rel.split("/")[0]
    bucket = load_table(path).get(mission)
    if bucket is None:
        raise UnknownMission(f"mission {mission!r} (from {url}) is not in {Path(path).name}; "
                             "run bin/refresh_mission_buckets.py")
    return bucket, f"drone_missions/{mission[:4]}/{rel}"


def s3_uri(url: str, path: Path = TABLE) -> str:
    """``s3://<bucket>/<key>`` for a legacy-host URL, "" for any other URL."""
    found = locate(url, path)
    return f"s3://{found[0]}/{found[1]}" if found else ""
