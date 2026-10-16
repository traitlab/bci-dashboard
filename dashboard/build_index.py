#!/usr/bin/env python3
"""Build the site entry point from the pages present in the publication folder.

Each task keeps its own recorded date. Optional photo tools appear only when
built, so an operational-only build remains a useful, honest landing page.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Each card is (file, task label, what the reader can do).
from site_navigation import CSS as NAVIGATION_CSS, navigation

PAGES = [
    ("model_health_dashboard.html", "Model health",
     "Check how well Pl@ntNet names BCI trees, by species and overall, and what the evaluation covers."),
    ("label_queue_dashboard.html", "Labelling queue",
     "Choose the next batch for expert labelling and inspect why those photos come first."),
]

OPTIONAL_PAGES = [
    ("explorer.html", "Browse photos",
     "Explore families, genera and species using Pl@ntNet first guesses or recorded labels, then inspect the photos."),
    ("embedding-atlas.html", "Similar photos",
     "Compare a selected photo with Pl@ntNet’s stored visual matches. Looking alike does not confirm the same species."),
    ("crownfirst-atlas.html", "Compare models",
     "Inspect Pl@ntNet and PlantCLEF visual matches for the same photos."),
]

STYLE = """*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:#1a1a1a;background:#f8f9fa;line-height:1.5;
  max-width:780px;margin:0 auto;padding:32px 24px 64px;
}
h1{font-size:1.6rem;font-weight:700;margin-bottom:4px;color:#212121}
.intro{font-size:0.95rem;color:#424242;margin:12px 0 24px}
.scope{font-size:0.85rem;color:#54665d;margin:24px 0 0}
a.card small{display:block;font-size:0.8rem;color:#54665d;margin-top:8px}
a.card{
  display:block;text-decoration:none;color:inherit;background:#fff;
  border:1px solid #e0e0e0;border-radius:6px;padding:16px 18px;margin-bottom:12px;
}
a.card:hover{border-color:#245743}
a.card:focus-visible,summary:focus-visible{outline:3px solid #2d8061;outline-offset:3px}
a.card b{display:block;font-size:1.05rem;color:#245743;margin-bottom:4px}
a.card span{font-size:0.9rem;color:#424242}
details{margin-top:24px}summary{cursor:pointer;margin-bottom:12px;color:#424242}
"""


def build_stamp(text: str) -> str:
    """Keep label and page dates distinct, without copying evaluation figures."""
    found = re.search(r'<div class="subtitle">(.*?)</div>', text, re.S)
    if not found:
        return ""
    line = html.unescape(re.sub(r"<[^>]+>", "", found.group(1))).strip()
    dates = [field.strip() for field in line.split("\u00b7")
             if re.fullmatch(r"(?:built|snapshot|labels as of) \d{4}-\d{2}-\d{2}", field.strip())]
    return ". ".join(dates)


def build(build_dir: str) -> str:
    optional = [page for page in OPTIONAL_PAGES if os.path.isfile(os.path.join(build_dir, page[0]))]
    explorer = [page for page in optional if page[0] == "explorer.html"]
    research = [page for page in optional if page[0] != "explorer.html"]
    available = explorer + PAGES + research
    stamps = {}
    for name, _, _ in available:
        with open(os.path.join(build_dir, name), encoding="utf-8") as fh:
            stamps[name] = build_stamp(fh.read())

    def card(name, title, blurb, fragment=""):
        stamp = stamps[name]
        date = f'<small>{html.escape(stamp)}</small>' if stamp else ""
        return (f'<a class="card" href="{name}{fragment}">'
                f'<b>{html.escape(title)}</b><span>{html.escape(blurb)}</span>{date}</a>')

    cards = [card(*page) for page in explorer]
    if "crownfirst-atlas.html" in stamps:
        cards.append(card("crownfirst-atlas.html", "Camera locations",
                          "Find photos by aircraft camera position, then inspect their visual matches.",
                          "#view=locations"))
    cards.extend(card(*page) for page in PAGES)
    if research:
        cards.append('<details><summary>Similar photos &amp; models</summary>'
                     + "".join(card(*page, fragment="#view=models" if page[0] == "crownfirst-atlas.html" else "")
                               for page in research) + '</details>')
    available_names = {name for name, _, _ in available} | {"index.html"}
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Panama canopy photos and labelling</title>"
            f"<style>{STYLE}{NAVIGATION_CSS}</style></head><body>"
            + navigation("index.html", available=available_names)
            + '<main id="main-content" tabindex="-1"><h1>Panama canopy photos</h1>'
            + '<p class="intro">Explore photos, inspect visual matches and choose what to label next.</p>'
            + "".join(cards)
            + '<p class="scope">Photo tools cover Barro Colorado Island and other Panama field sites. '
              'Model health and labelling queues describe their own recorded snapshots. '
              'Photo counts do not measure tree abundance. Model guesses need expert confirmation.</p>'
            + "</main></body></html>\n")


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
