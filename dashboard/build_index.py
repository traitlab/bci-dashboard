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
main{max-width:1168px;margin:auto;padding:36px 24px 48px}
h1{font-size:32px;font-weight:650;line-height:1.2;letter-spacing:-.8px;color:var(--ink)}
.intro{font-size:16px;color:var(--slate);margin:12px 0 28px;max-width:65ch}
.tasks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
a.card{display:block;text-decoration:none;color:inherit;background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:22px 24px;min-height:150px}
a.card:hover{border-color:var(--green);background:var(--pale)}
a.card:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
a.card b{display:block;font-size:20px;font-weight:650;color:var(--green);margin-bottom:8px}
a.card span{display:block;font-size:14px;max-width:52ch;color:var(--ink)}
a.card small{display:block;font-size:12px;color:var(--slate);margin-top:14px}
.scope{font-size:13px;color:var(--slate);margin:26px 0 0;max-width:86ch;border-top:1px solid var(--line);padding-top:18px}
@media(max-width:640px){main{padding:24px 14px 36px}h1{font-size:27px}.tasks{grid-template-columns:1fr;gap:12px}a.card{padding:18px;min-height:0}a.card b{font-size:18px}}
"""


def build_stamp(text: str) -> str:
    """Keep label and page dates distinct, without copying evaluation figures."""
    found = re.search(r'<div class="subtitle">(.*?)</div>', text, re.S)
    if not found:
        return ""
    line = html.unescape(re.sub(r"<[^>]+>", "", found.group(1))).strip()
    dates = [field.strip() for field in line.split("\u00b7")
             if re.fullmatch(r"(?:built|snapshot|refreshed|labels as of|Labelbox labels merged) \d{4}-\d{2}-\d{2}", field.strip())]
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
        cards.append(card("crownfirst-atlas.html", "Drone map",
                          "Find photos by drone photo location, then inspect their visual matches.",
                          "#view=locations"))
    cards.extend(card(*page, fragment="#view=models" if page[0] == "crownfirst-atlas.html" else "")
                 for page in research)
    cards.extend(card(*page) for page in PAGES)
    available_names = {name for name, _, _ in available} | {"index.html"}
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Panama canopy photos and labelling</title>"
            f'<style>{STYLE}{NAVIGATION_CSS}</style></head><body data-workspace="home">'
            + navigation("index.html", available=available_names)
            + '<main id="main-content" tabindex="-1"><h1>Panama canopy photos</h1>'
            + '<p class="intro">Browse the canopy by taxon or drone photo location, compare visual matches, and choose what to label next.</p>'
            + '<div class="tasks">' + "".join(cards) + '</div>'
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
