#!/usr/bin/env python3
"""Build the site entry point from the pages present in the publication folder.

Each task keeps its own recorded date. Optional photo tools appear only when
built, so an operational-only build remains a useful, honest landing page.
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from site_navigation import CSS as NAVIGATION_CSS, FAVICON, navigation

# A tile is (file, title, purpose, fragment, figure). The registry holds the
# first four; the figure is read off the linked page when the index is built.
PAGES = [
    ("label_queue_dashboard.html", "Labelling queue",
     "Choose the next batch for expert labelling and inspect why those photos come first.", ""),
    ("model_health_dashboard.html", "Model health",
     "Check how well Pl@ntNet names BCI trees, by species and overall, and what the evaluation covers.", ""),
]

OPTIONAL_PAGES = [
    ("explorer.html", "Browse photos",
     "Explore families, genera and species using Pl@ntNet first guesses or recorded labels.", ""),
    ("embedding-atlas.html", "Drone map",
     "Find photos by drone photo location.", "#view=locations"),
    ("embedding-atlas.html", "Similar photos",
     "Compare a selected photo with Pl@ntNet\u2019s stored visual matches. Looking alike does not confirm the same species.",
     "#view=photos"),
]

EXPERIMENT = "crownfirst-atlas.html"

STYLE = """*{box-sizing:border-box;margin:0;padding:0}
main{max-width:1168px;margin:auto;padding:36px 24px 48px}
h1{font-size:32px;font-weight:650;line-height:1.2;letter-spacing:-.8px;color:var(--ink)}
.intro{font-size:16px;color:var(--slate);margin:12px 0 28px;max-width:65ch}
.tasks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
a.card{display:block;text-decoration:none;color:inherit;background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:22px 24px;min-height:150px}
a.card:hover{border-color:var(--green);background:var(--pale)}
a.card:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
a.card b{display:block;font-size:20px;font-weight:650;color:var(--green);margin-bottom:8px}
a.card span{display:block;font-size:14px;max-width:52ch;color:var(--ink)}
a.card small{display:block;font-size:12px;color:var(--slate);margin-top:14px}
.more{margin-top:20px;font-size:14px}.more a{display:inline-block;padding:10px 0;margin-right:22px}
.scope{font-size:13px;color:var(--slate);margin:26px 0 0;max-width:86ch;border-top:1px solid var(--line);padding-top:18px}
.about h2{font-size:20px;margin:28px 0 8px}.about ul,.about dl{max-width:75ch;font-size:15px}.about li,.about dd{margin:6px 0 6px 18px}.about dt{font-weight:650;margin-top:10px}.about p{max-width:75ch;margin:8px 0}
@media(max-width:900px){.tasks{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){main{padding:24px 14px 36px}h1{font-size:27px}.tasks{grid-template-columns:1fr;gap:12px}a.card{padding:18px;min-height:0}a.card b{font-size:18px}}
"""

CAVEATS = ("Photo counts do not measure tree abundance.",
           "Model guesses need expert confirmation.",
           "Each page describes its own snapshot, so the dates differ from page to page.")


GLOSSARY = (
    ("Close-up", "One drone photo, aimed at one tree crown. A frame is the same thing. It can show more crowns than the one it is aimed at."),
    ("Crown", "The top of one tree, as seen from the drone."),
    ("Centre crown", "The crown the frame is aimed at. Pl@ntNet is sent the centre crop, the middle square of the frame, which should hold this crown. "
                     "The label of the frame is the species with the most crown area in the whole frame, usually this crown but not always."),
    ("Segmentation version", "A run of the tool that outlines crowns in the mission map. The version can differ from mission to mission."),
    ("Mission", "One drone flight session over a site. Each frame belongs to one mission."),
)


def build_stamp(text: str) -> str:
    """Keep label and page dates distinct, without copying evaluation figures."""
    found = re.search(r'<div class="subtitle">(.*?)</div>', text, re.S)
    if not found:
        return ""
    line = html.unescape(re.sub(r"<[^>]+>", "", found.group(1))).strip()
    dates = [field.strip() for field in line.split("\u00b7")
             if re.fullmatch(r"(?:built|snapshot|refreshed|labels as of|Labelbox labels merged) \d{4}-\d{2}-\d{2}", field.strip())]
    return ". ".join(dates)


def build_figure(text: str) -> str:
    """The one figure a page puts on its hero for the index tile, or ''."""
    found = re.search(r'<div class="hero[^"]*" data-tile="([^"]*)"', text)
    return html.unescape(found.group(1)).strip() if found else ""


def scope_sentence(build_dir: str) -> str:
    """What the data covers, counted off the published tables. A figure whose
    table is absent is left out, never typed. Other pages' bylines can import this."""
    def rows(name):
        try:
            with open(os.path.join(build_dir, name), encoding="utf-8", newline="") as fh:
                return list(csv.DictReader(fh))
        except OSError:
            return []

    def many(n, word):
        return f"{n:,} {word}{'' if n == 1 else 's'}"

    parts = ["Drone-photographed crowns only, not every tree"]
    scope = rows("scope.csv")
    if scope:
        # Every frame with a cached answer, labelled or not. Mission and site are
        # blank where the inventory does not name them; a mission starts with the
        # flight date. The date in a file name is when it was written, not flown.
        missions = {r["mission"] for r in scope if r["mission"]}
        sites = {r["site"] for r in scope if r["site"]}
        dates = sorted(m.group(1) for r in scope if (m := re.match(r"(\d{8})", r["mission"])))
        first, last = (f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in (dates[0], dates[-1])) if dates else ("", "")
        span = (f", photographed {first} to {last}" if first != last
                else f", photographed on {first}" if dates else "")
        source = f" from {many(len(missions), 'mission')} at {many(len(sites), 'site')}" if missions else ""
        frames, labelled = (sum(int(r[k]) for r in scope) for k in ("n_frames", "n_labelled"))
        parts.append(f"{many(frames, 'close-up')}{source}{span}, {labelled:,} of them labelled")
    health = rows("per_species_health.csv")
    if health:
        n = sum(int(r["n_labelled_frames"]) for r in health)
        parts.append(f"{n:,} labelled frames across {len(health)} species are scored on Model health")
    queue = rows("send_batches.csv")
    if queue:
        parts.append(f"{len(queue):,} unlabelled photos are queued for labelling")
    return ". ".join(parts) + "."


def scope_byline(build_dir: str, present) -> str:
    """The scope sentence as a data page's byline: the map link when that page is
    built, and the table the counts come off when the snapshot has one."""
    table = (' Counted in <a href="scope.csv">scope.csv</a>.'
             if os.path.isfile(os.path.join(build_dir, "scope.csv")) else "")
    return f'<div class="subtitle">{html.escape(scope_sentence(build_dir))}{_map_link(present)}{table}</div>'


def available_names(build_dir: str) -> set:
    """Pages the index may link: registry files present, plus index and About."""
    names = {page[0] for page in [*PAGES, *OPTIONAL_PAGES]} | {EXPERIMENT}
    return {n for n in names if os.path.isfile(os.path.join(build_dir, n))} | {"index.html", "about.html"}


def build(build_dir: str) -> str:
    present = available_names(build_dir)
    browse = [p for p in OPTIONAL_PAGES if p[0] == "explorer.html" and p[0] in present]
    tiles = []
    # The public tier has no labelling queue, so a registry page can be absent too.
    for name, title, purpose, fragment in browse + [p for p in PAGES if p[0] in present]:
        with open(os.path.join(build_dir, name), encoding="utf-8") as fh:
            text = fh.read()
        tiles.append((name, title, purpose, fragment, build_figure(text), build_stamp(text)))

    # Pages refreshed together carry one stamp, shown once under the grid.
    stamps = {tile[5] for tile in tiles if tile[5]}
    shared = stamps.pop() if len(stamps) == 1 else ""

    def card(name, title, purpose, fragment, figure, stamp):
        line = ". ".join(part for part in (figure, "" if stamp == shared else stamp) if part)
        small = f'<small>{html.escape(line)}</small>' if line else ""
        return (f'<a class="card" href="{name}{fragment}">'
                f'<b>{html.escape(title)}</b><span>{html.escape(purpose)}</span>{small}</a>')

    more = "".join(f'<a href="{name}{fragment}">{html.escape(title)}</a>'
                   for name, title, _, fragment in OPTIONAL_PAGES
                   if name == "embedding-atlas.html" and name in present)
    return (_head("Panama canopy photos and labelling",
                  "Drone photos of the Panama canopy with Pl@ntNet guesses and recorded labels: browse photos, choose the next labelling batch, check model health.", "index.html", present)
            + '<main id="main-content" tabindex="-1"><h1>Panama canopy</h1>'
            + '<p class="intro">Drone photos of the canopy on Barro Colorado Island and other Panama field sites. '
              'Pl@ntNet suggests a name for each photo and botanists confirm it. '
              'This site is a window into the current data for the project leads and the labelling coordinator. '
              'Annotators work in Labelbox, where model guesses are hidden on purpose so they do not bias identifications. '
              'It does not yet suggest where to fly the drone. <a href="about.html">About</a></p>'
            + '<div class="tasks">' + "".join(card(*tile) for tile in tiles) + '</div>'
            + (f'<p class="more">{more}</p>' if more else "")
            + (f'<p class="scope">{html.escape(shared)}</p>' if shared else "")
            + _scope_html(scope_sentence(build_dir), present)
            + "</main></body></html>\n")


def _map_link(present) -> str:
    return (' <a href="embedding-atlas.html#view=locations">See the map</a>.'
            if "embedding-atlas.html" in present else "")


def _scope_html(sentence: str, present) -> str:
    return f'<p class="scope">{html.escape(sentence)}{_map_link(present)}</p>'


def build_about(available, scope: str = "") -> str:
    """What each page is for, the caveats, and a glossary. Carries no data."""
    pages = "".join(
        f'<li><a href="{name}{fragment}">{html.escape(title)}</a>. {html.escape(purpose)}</li>'
        for name, title, purpose, fragment in [*OPTIONAL_PAGES, *PAGES] if name in available)
    experiment = (f'<h2>Experimental matching</h2><p>Pl@ntNet against the recorded PlantCLEF experiment '
                  f'on the same photos: <a href="{EXPERIMENT}#view=models">Compare models (experimental)</a>.</p>'
                  if EXPERIMENT in available else "")
    return (_head("About Panama canopy", "What each page of the Panama canopy site is for, how to read its numbers, and a glossary.", "about.html", available)
            + '<main id="main-content" tabindex="-1" class="about"><h1>About</h1>'
            + '<h2>What each page is for</h2><ul>' + pages + '</ul>'
            + ('<h2>Data scope</h2>' + _scope_html(scope, available) if scope else "")
            + '<h2>Read the numbers with care</h2>' + "".join(f"<p>{c}</p>" for c in CAVEATS)
            + experiment
            + '<h2>Glossary</h2><dl>'
              '<dt>Recorded label</dt><dd>The species name a botanist has recorded for a photo.</dd>'
              '<dt>Pl@ntNet first guess</dt><dd>The species Pl@ntNet ranks first for a photo.</dd>'
              '<dt>Labelled frame</dt><dd>A drone photo that carries a recorded label.</dd>'
              + "".join(f"<dt>{term}</dt><dd>{html.escape(meaning)}</dd>" for term, meaning in GLOSSARY)
              + '</dl>'
            + "</main></body></html>\n")


def _head(title: str, description: str, current: str, available) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="description" content="{description}">'
            f'<title>{title}</title>{FAVICON}<style>{STYLE}{NAVIGATION_CSS}</style></head>'
            f'<body data-workspace="home">' + navigation(current, available=available))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--out", default=os.path.join("docs", "index.html"))
    ap.add_argument("--about-out", default=os.path.join("docs", "about.html"))
    args = ap.parse_args()
    for path, out in ((args.out, build(args.build)),
                      (args.about_out, build_about(available_names(args.build), scope_sentence(args.build)))):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"  wrote     {path}  ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
