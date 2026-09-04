#!/usr/bin/env python3
"""The landing page GitHub Pages serves at the root of the site.

Two links and the date they were built. It exists because the reviewer asked for one
bookmarkable address rather than a file someone has to be sent each time, and a
bookmark that lands on a directory listing is not that.

The date is read back out of the built pages, so a rebuild moves it here too.
Nothing else is carried across and nothing is measured: a number belongs on one
of the two pages, under the provenance that explains it, not on a signpost.

    python3 dashboard/build_index.py --build build --out docs/index.html
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PAGES = [
    ("model_health_dashboard.html",
     "How well does Pl@ntNet name BCI trees?",
     "Accuracy of the predictions, per species and overall, with what each "
     "number was measured on."),
    ("label_queue_dashboard.html",
     "What to label next",
     "The order the unlabelled photos should be worked through, and the "
     "reasoning behind that order."),
]

STYLE = """*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:#1a1a1a;background:#f8f9fa;line-height:1.5;
  max-width:780px;margin:0 auto;padding:32px 24px 64px;
}
h1{font-size:1.6rem;font-weight:700;margin-bottom:4px;color:#212121}
.subtitle{font-size:0.85rem;color:#757575;margin-bottom:28px}
a.card{
  display:block;text-decoration:none;color:inherit;background:#fff;
  border:1px solid #e0e0e0;border-radius:6px;padding:16px 18px;margin-bottom:12px;
}
a.card:hover{border-color:#1565c0}
a.card b{display:block;font-size:1.05rem;color:#1565c0;margin-bottom:4px}
a.card span{font-size:0.9rem;color:#424242}
"""


def build_stamp(text: str) -> str:
    """The build date off a built page, and nothing else.

    A page's own subtitle carries the snapshot date, the model tag and two
    counts after it, separated by middots. Those are numbers, and a number
    belongs on the page that can say what it was measured on. Here they are a
    headline with no provenance under it, so only the first field survives.

    The separator is decoded before the caller escapes the line. Left encoded,
    it was escaped twice and the front door read `built 2026-09-04 &middot;`.
    """
    found = re.search(r'<div class="subtitle">(.*?)</div>', text, re.S)
    if not found:
        return ""
    line = html.unescape(re.sub(r"<[^>]+>", "", found.group(1))).strip()
    return line.split("\u00b7", 1)[0].strip()


def build(build_dir: str) -> str:
    cards = []
    stamp = ""
    for name, title, blurb in PAGES:
        path = os.path.join(build_dir, name)
        with open(path, encoding="utf-8") as fh:
            stamp = stamp or build_stamp(fh.read())
        cards.append(f'<a class="card" href="{html.escape(name)}">'
                     f'<b>{html.escape(title)}</b>'
                     f'<span>{html.escape(blurb)}</span></a>')
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>BCI tree identification dashboards</title>"
            f"<style>{STYLE}</style></head><body>"
            "<h1>BCI tree identification</h1>"
            f'<div class="subtitle">{html.escape(stamp)}</div>'
            + "".join(cards) +
            "</body></html>\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--out", default=os.path.join("docs", "index.html"))
    args = ap.parse_args()
    out = build(args.build)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"  wrote     {args.out}  ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
