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
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import REFERENCE_SWITCHED_ON, plantnet_version_words
from queues import PREDICTED_LIANA, PUSHED_DOWN, TREES_ONLY_SINCE
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
     "Explore families, genera and species using Pl@ntNet top predictions or recorded labels.", ""),
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

# The landing page's two-sentence intro, in full.
AUDIENCE = ('<p>Drone photos of the canopy on Barro Colorado Island and other Panama field sites. '
            'Pl@ntNet predicts a name for each photo. Botanists label the photos in Labelbox without seeing the prediction.</p>'
            '<p>This site is a window into the current data for the project leads and the labelling coordinator. '
            'Annotators work in Labelbox, where model predictions are hidden on purpose so they do not bias identifications. '
            'It does not yet suggest where to fly the drone.</p>')

CAVEATS = ("Photo counts do not measure tree abundance.",
           "Model predictions need expert confirmation.",
           "Each page describes its own snapshot, so the dates differ from page to page.")


GLOSSARY = (
    ("Close-up", "A frame is one drone photo, aimed at one tree crown. It can show more crowns than the one it is aimed at. The labelling team calls it a close-up."),
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


def _rows(build_dir: str, name: str) -> list[dict]:
    try:
        with open(os.path.join(build_dir, name), encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def many(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _fail(why: str):
    raise SystemExit(f"VERIFY FAIL: the About scope does not add up, {why}")


def _num(rows: list, col: str) -> int:
    return sum(int(r[col]) for r in rows)


def _a(name: str, text: str) -> str:
    return f'<a href="{name}">{text}</a>'


def _evaluation(build_dir: str) -> dict | None:
    """The Pl@ntNet evaluation's counts off scope.csv (and per_species_health.csv
    for the scored frames), or None without scope.csv. Stops the build when a
    branch does not sum to its parent. A column an older table lacks leaves its
    figure out, never typed."""
    scope = _rows(build_dir, "scope.csv")
    if not scope:
        return None
    if any(int(r["n_labelled"]) > int(r["n_frames"]) for r in scope):
        _fail("scope.csv has a mission with more labelled frames than frames, so labelled "
              "+ not yet labelled is not the frames")
    frames, labelled = _num(scope, "n_frames"), _num(scope, "n_labelled")
    # Every frame with a cached answer, labelled or not. Mission and site are
    # blank where the inventory does not name them; a mission starts with the
    # flight date, but a mission folder can hold later photos, so the capture
    # stamps in the frame names set the range and the folder date fills in
    # for a row without one. The date in a file name is when it was written, not flown.
    dates = sorted(d for r in scope for d in (
        (r.get("first_capture"), r.get("last_capture")) if r.get("first_capture")
        else re.findall(r"^\d{8}", r["mission"])))
    first, last = (f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in (dates[0], dates[-1])) if dates else ("", "")
    out = {"frames": frames, "labelled": labelled, "scored": None, "species": None, "not_scored": (),
           "missions": len({r["mission"] for r in scope if r["mission"]}),
           "sites": len({r["site"] for r in scope if r["site"]}),
           "flown": f"{first} to {last}" if first != last else f"on {first}" if dates else ""}
    health = _rows(build_dir, "per_species_health.csv")
    scored = _num(health, "n_labelled_frames") if health else None
    out["species"] = len(health)
    if "n_scored" in scope[0]:
        if scored is not None and scored != _num(scope, "n_scored"):
            _fail(f"scope.csv scores {_num(scope, 'n_scored'):,} frames, per_species_health.csv {scored:,}")
        scored = _num(scope, "n_scored")
    if scored is None:
        return out
    if scored > labelled:
        _fail(f"{scored:,} frames are scored but only {labelled:,} are labelled")
    out["scored"] = scored
    if "n_reviewed" in scope[0]:
        reviewed, no_answer, above = (_num(scope, c) for c in ("n_reviewed", "n_no_answer", "n_above_species"))
        if reviewed != scored + no_answer + above:
            _fail(f"{reviewed:,} frames with a checked label are not {scored:,} scored + {no_answer:,} with "
                  f"no usable answer + {above:,} with a label above species")
        if reviewed > labelled:
            _fail(f"{reviewed:,} frames have a checked label but only {labelled:,} are labelled")
        out["not_scored"] = ((labelled - reviewed, "with a Labelbox label not yet checked for publication"),
                             (no_answer, "with no usable Pl@ntNet answer"),
                             (above, "with a label that stops above species"))
    return out


def _batch_ids(rows: list) -> list:
    return sorted({int(r["batch_id"]) for r in rows})


def _outgoing(build_dir: str) -> dict | None:
    """Where the 2024_bci photos in no project stand, off frames.csv, send_batches.csv
    and send_first_queue.csv, or None unless all three hold the catalog batches."""
    frames, batches = _rows(build_dir, "frames.csv"), _rows(build_dir, "send_batches.csv")
    queue = _rows(build_dir, "send_first_queue.csv")
    if not (frames and batches and queue and "handed_out" in batches[0] and "no_batch_reason" in queue[0]):
        return None
    status, why = Counter(r["status"] for r in frames), Counter(r["no_batch_reason"] for r in queue)
    ready = [r for r in batches if r["handed_out"] == "True"]
    packed = [r for r in batches if r["handed_out"] != "True"]
    priority = {r["global_key"] for r in frames if r["priority_mission"] == "True"}
    # frames.csv calls every unbatched frame no_answer, the kept-out ones too:
    # only a frame with no row in the queue has no species in its answer.
    queued = {r["global_key"] for r in queue}
    no_species = sum(r["status"] == "no_answer" and r["global_key"] not in queued for r in frames)
    out = {"pool": len(frames), "sent": status["already_sent"], "no_species": no_species,
           "ready": len(ready), "ready_ids": _batch_ids(ready), "priority": sum(r["global_key"] in priority for r in ready),
           "packed": len(packed), "packed_ids": _batch_ids(packed),
           "pushed_down": why[PUSHED_DOWN], "liana": why[PREDICTED_LIANA]}
    parts = ("sent", "ready", "packed", "pushed_down", "liana", "no_species")
    if sum(out[p] for p in parts) != out["pool"]:
        _fail(f"the {out['pool']:,} photos in no project are not " + " + ".join(f"{out[p]:,} {p}" for p in parts)
              + f" (frames.csv statuses: {dict(status)})")
    return out


def _apart(build_dir: str) -> str:
    """The overlap of the two populations as the build measured it (pool_overlap.csv),
    or nothing when this build did not measure it."""
    if not os.path.isfile(os.path.join(build_dir, "pool_overlap.csv")):
        return ""
    if shared := len(_rows(build_dir, "pool_overlap.csv")):
        return f" {shared:,} of them are also frames in the evaluation above."
    return " None of them is among the frames in the evaluation above."


def _batches(ids: list) -> str:
    span = f"{ids[0]}-{ids[-1]}" if len(ids) > 1 and ids == list(range(ids[0], ids[-1] + 1)) else ", ".join(map(str, ids))
    return f"batch{'' if len(ids) == 1 else 'es'} {span}"


def _ul(items: list) -> str:
    """A nested list: an item is its text, or (text, sub-items)."""
    return "<ul>" + "".join(f"<li>{i if isinstance(i, str) else i[0] + _ul(i[1])}</li>" for i in items) + "</ul>"


def scope_breakdown(build_dir: str) -> str:
    """What each count on the site covers and why it drops, as HTML counted off the
    published tables. Two populations, never pooled: the frames in the Pl@ntNet
    evaluation, and the photos going out for labelling. A branch whose table is
    absent is left out, never typed. About carries it in full."""
    out = [("<p>Drone photos of tree crowns only. A tree whose crown was not photographed is not here. "
            "A frame is one drone photo.</p>")]
    if e := _evaluation(build_dir):
        head = [f"Frames in the Pl@ntNet evaluation: {_a('scope.csv', format(e['frames'], ','))}"]
        head += [many(e[k], word) for k, word in (("missions", "mission"), ("sites", "site")) if e[k]]
        if e["flown"]:
            head.append(f"flown {e['flown']}")
        subs = []
        if e["scored"] is not None:
            species = f" ({e['species']:,} species)" if e["species"] else ""
            subs.append(f"{_a('per_species_health.csv', format(e['scored'], ',') + ' scored on Model health')}{species}: "
                        f"since {REFERENCE_SWITCHED_ON}, only frames whose species name was checked for the official BCI data "
                        "publication, and with a Pl@ntNet answer naming at least one species")
            if reasons := [f"{n:,} {text}" for n, text in e["not_scored"] if n]:
                subs.append(f"{e['labelled'] - e['scored']:,} not scored: " + ", ".join(reasons))
        labelled = (f"{_a('scope.csv', format(e['labelled'], ',') + ' labelled')}: a botanist outlined the crowns in the "
                    "frame; the label is the species covering the most crown area")
        unlabelled = (f"{_a('scope.csv', format(e['frames'] - e['labelled'], ',') + ' not yet labelled')}, "
                      "already in the botanists' Labelbox project")
        out += [f"<p>{' &middot; '.join(head)}</p>", _ul([(labelled, subs) if subs else labelled, unlabelled])]
        if e["scored"] is not None:
            out.append(f"<p>The reference labels changed on {REFERENCE_SWITCHED_ON}; scores before then "
                       "used the Labelbox labels.</p>")
    if o := _outgoing(build_dir):
        ready = (f"{_a('send_batches.csv', format(o['ready'], ','))} ready to send "
                 f"({_batches(o['ready_ids'])}, handed to the labelling coordinator; they do not change)")
        if o["priority"]:
            ready += (f", {o['priority']:,} of them from priority missions: their crowns were also identified "
                      "on the ground, so a label can be checked twice")
        packed = f"{o['packed']:,} packed after them ({_batches(o['packed_ids'])}, these can still change)"
        items = [f"{o['sent']:,} sent to the botanists' Labelbox project so far",
                 (f"{o['ready'] + o['packed']:,} in batches of up to 100", [ready, packed])]
        kept = [f"{o[k]:,} {text}" for k, text in (
            ("pushed_down", ("pushed down the queue: Pl@ntNet is already confident and the species has enough "
                             "labels, so they wait until Pl@ntNet's model changes. The current model is from "
                             f"{plantnet_version_words()}")),
            ("liana", (f"predicted liana, which are not sent: since {TREES_ONLY_SINCE} only predicted trees go out, "
                       "and the liana call is a Pl@ntNet guess"))) if o[k]]
        if kept:
            items.append((f"{_a('send_first_queue.csv', format(o['pushed_down'] + o['liana'], ','))} in no batch", kept))
        if o["no_species"]:
            items.append(f"{o['no_species']:,} left out: the Pl@ntNet answer names no species")
        apart = _apart(build_dir) if e else ""
        out += [(f"<p>Photos going out for labelling: {o['pool']:,} photos in the 2024_bci Labelbox dataset "
                 f"that are not yet in a Labelbox project, the workspace where botanists label.{apart}</p>"), _ul(items)]
    return "".join(out)


def scope_short(build_dir: str, present) -> str:
    """The scope in one line, as HTML: the evaluation's frames, labelled and scored,
    and the photos ready to send, each linked to the table it is counted off, the
    map when built, and About's full scope."""
    counts = ""
    if e := _evaluation(build_dir):
        counts = f' {_a("scope.csv", many(e["frames"], "frame"))} in the evaluation: {_a("scope.csv", format(e["labelled"], ",") + " labelled")}'
        if e["scored"] is not None:
            counts += ", " + _a("per_species_health.csv", format(e["scored"], ",") + " scored")
        counts += "."
    if o := _outgoing(build_dir):
        counts += f' {_a("send_batches.csv", many(o["ready"], "photo"))} ready to send.'
    return (f'Drone-photographed crowns only.{counts}{_map_link(present)}'
            ' <a href="about.html#scope">Full scope</a>.')


def scope_byline(build_dir: str, present) -> str:
    """The short scope line as a data page's byline."""
    return f'<div class="subtitle">{scope_short(build_dir, present)}</div>'


def available_names(build_dir: str) -> set:
    """Pages the index may link: registry files present, plus index and About."""
    names = {page[0] for page in [*PAGES, *OPTIONAL_PAGES]} | {EXPERIMENT}
    return {n for n in names if os.path.isfile(os.path.join(build_dir, n))} | {"index.html", "about.html"}


def build(build_dir: str) -> str:
    present = available_names(build_dir)
    browse = [p for p in OPTIONAL_PAGES if p[0] == "explorer.html" and p[0] in present]
    tiles = []
    for name, title, purpose, fragment in browse + PAGES:
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

    from page import mark_first_use  # page imports GLOSSARY from here, so not at the top

    more = "".join(f'<a href="{name}{fragment}">{html.escape(title)}</a>'
                   for name, title, _, fragment in OPTIONAL_PAGES
                   if name == "embedding-atlas.html" and name in present)
    head = _head("Panama canopy photos and labelling",
                 "Drone photos of the Panama canopy with Pl@ntNet predictions and recorded labels: browse photos, choose the next labelling batch, check model health.", "index.html", present)
    main = ('<main id="main-content" tabindex="-1"><h1>Panama canopy</h1>'
            + '<p class="intro">Panama canopy drone photos and Pl@ntNet predictions, for the project leads and the labelling coordinator. '
              'Annotators label in Labelbox, where the predictions are hidden; the site does not yet suggest where to fly. '
              '<a href="about.html#audience">About</a></p>'
            + '<div class="tasks">' + "".join(card(*tile) for tile in tiles) + '</div>'
            + (f'<p class="more">{more}</p>' if more else "")
            + (f'<p class="scope">{html.escape(shared)}</p>' if shared else "")
            + f'<p class="scope">{scope_short(build_dir, present)}</p>'
            + "</main></body></html>\n")
    return head + mark_first_use(main)


def _map_link(present) -> str:
    return (' <a href="embedding-atlas.html#view=locations">See the map</a>.'
            if "embedding-atlas.html" in present else "")


def _scope_html(breakdown: str, present) -> str:
    link = _map_link(present).strip()
    return f'{breakdown}{f"<p>{link}</p>" if link else ""}'


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
            + '<h2 id="audience">Who this is for</h2>' + AUDIENCE
            + '<h2>What each page is for</h2><ul>' + pages + '</ul>'
            + ('<h2 id="scope">Data scope</h2>' + _scope_html(scope, available) if scope else "")
            + '<h2>Read the numbers with care</h2>' + "".join(f"<p>{c}</p>" for c in CAVEATS)
            + experiment
            + '<h2>Glossary</h2><dl>'
              '<dt>Recorded label</dt><dd>The species name a botanist has recorded for a photo.</dd>'
              '<dt>Pl@ntNet top prediction</dt><dd>The species Pl@ntNet ranks first for a photo.</dd>'
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
                      (args.about_out, build_about(available_names(args.build), scope_breakdown(args.build)))):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"  wrote     {path}  ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
