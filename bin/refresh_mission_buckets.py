#!/usr/bin/env python3
"""Rewrite input/mission_buckets.csv from a live listing of the private buckets.

Needs the aws CLI (`uvx --from awscli aws` works) with a profile that can list
the buckets. Run it when a new mission is copied; the build never lists anything.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUCKETS = ("2024-bci", "2024-panama")


def listing(aws: list[str], bucket: str, prefix: str) -> list[str]:
    """Names one level below s3://bucket/prefix (the `PRE name/` lines)."""
    out = subprocess.run([*aws, "s3", "ls", f"s3://{bucket}/{prefix}"],
                         capture_output=True, text=True, check=True).stdout
    return [ln.split("PRE", 1)[1].strip().rstrip("/") for ln in out.splitlines() if "PRE" in ln]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", required=True)
    p.add_argument("--endpoint-url", default="https://object-arbutus.alliancecan.ca")
    p.add_argument("--aws", default="uvx --from awscli aws", help="command that runs the aws CLI")
    p.add_argument("--out", type=Path, default=REPO / "input" / "mission_buckets.csv")
    args = p.parse_args(argv)
    aws = [*args.aws.split(), "--profile", args.profile, "--endpoint-url", args.endpoint_url]

    rows: dict[str, str] = {}
    for bucket in BUCKETS:
        for year in listing(aws, bucket, "drone_missions/"):
            for mission in listing(aws, bucket, f"drone_missions/{year}/"):
                if rows.setdefault(mission, bucket) != bucket:
                    sys.exit(f"{mission} is in both {rows[mission]} and {bucket}")
    if not rows:
        sys.exit("listing returned no missions; keeping the existing table")
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["mission", "bucket"])
        w.writerows(sorted(rows.items()))
    print(f"{len(rows)} missions written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
