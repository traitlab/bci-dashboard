"""Top-1 on the test frames from flights the train set never saw.

The split in data/splits.csv is drawn frame by frame, and drone frames from one
flight over one site overlap, so a test frame can be a near-copy of a train
frame. tests/test_split_blocking.py pins that every test frame today shares a
flight with a train frame. This module measures the number that does not lean
on that: top-1 on the test frames whose flight (one date, one site) has no
train frame at all. Today that population is empty and the page says so.

A flight is read out of the Labelbox inventory: each frame URL carries a
mission folder named <yyyymmdd>_<site>_<waypoint>_<aircraft>, the same shape
labelling/draw_field_sample.py reads a site out of. A frame whose URL carries
no such folder cannot be placed on a flight; it is counted, not dropped quietly.
"""

from __future__ import annotations

import csv
import json
import os
import re

import core as hc
import species_mix
from assets import more

MISSION_RE = re.compile(r"/(\d{8})_([a-z0-9]+)_")

COLUMNS = ("population", "n_frames", "n_correct_top1", "top1_accuracy")
# The draw's own record, beside the CSV health.py reads the held frames from.
HOLDOUT_JSON = os.path.splitext(hc.HOLDOUT_CSV)[0] + ".json"
FLIGHT_CSV = "flight_holdout.csv"
# The graded row and the drawn row. A drawn frame with no cached answer or no
# label row cannot be graded, so the two counts differ and both are written:
# a grade over fewer frames than were held is a fact a reader should see.
FLIGHT_GRADED_ROW = "holdout_held_graded"
FLIGHT_DRAWN_ROW = "holdout_held_drawn"
# The rows held_out.csv carries, in this order. The unplaced row carries a
# count only: those frames are graded in the overall test rate, never apart.
POPULATIONS = (("test", "test"), ("test_unseen_flight", "unseen"))
UNPLACED_ROW = "test_unplaced"


def flight_of(url: str):
    """(date, site) from a frame URL's mission folder, or None."""
    m = MISSION_RE.search(url or "")
    return (m.group(1), m.group(2)) if m else None


def load_flights(path: str = hc.DATASET_ROWS_COMBINED_JSONL) -> dict:
    """global_key -> (date, site) for every inventory row that has both."""
    flights = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            key, flight = row.get("global_key"), flight_of(row.get("row_data"))
            if key and flight:
                flights[key] = flight
    return flights


def _rate(recs) -> dict:
    correct = sum(1 for r in recs if r["ranked"][0][0] == r["gt"])
    return {"n": len(recs), "correct": correct, "top1": hc.ratio(correct, len(recs))}


def measure(sp_recs, flights: dict) -> dict:
    """Overall test top-1, top-1 on test frames from flights with no train
    frame, and how many frames could not be placed on a flight.

    A train frame with no flight vouches for nothing: the flight it was on
    stays unseen, because nothing says which one that was. Counted apart so a
    page can say so.
    """
    train = [r for r in sp_recs if r["split"] == "train"]
    test = [r for r in sp_recs if r["split"] == "test"]
    seen = {flights[r["global_key"]] for r in train if r["global_key"] in flights}
    placed = [r for r in test if r["global_key"] in flights]
    unseen = [r for r in placed if flights[r["global_key"]] not in seen]
    return {"test": _rate(test), "unseen": _rate(unseen),
            "unplaced": len(test) - len(placed),
            "unplaced_train": sum(1 for r in train if r["global_key"] not in flights)}


def load_manifest(path: str = HOLDOUT_JSON):
    """The flight holdout's own record: which version, how many flights it
    holds, how many frames it drew, and how many species it cannot grade.

    Every number the note prints about the draw comes from here rather than
    from a constant, because the draw is the thing that decided them. An absent
    file returns None and the page says nothing about a holdout, which is what
    a checkout without a drawn one gets.
    """
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def measure_flight_holdout(sp_recs, manifest, flights: dict) -> dict | None:
    """Top-1 on the frames the flight holdout holds, the same computation
    ``measure`` runs on the test frames.

    The population is every scored frame ``health.load_health`` tagged with
    ``core.HOLDOUT_SPLIT``. Those frames are on flights no train frame is on,
    so this rate leans on no near-copy of a frame the labels already know.
    ``mix`` reads the same two rates on the species both sets hold, each
    reweighted to one common species mix (``species_mix.compare``, test as the
    first population), because the two sets hold different species in
    different shares. Its range draws whole sites, read off ``flights``; a
    frame that cannot be placed on a flight has no site, so it is left out of
    ``mix`` and counted in ``mix["unplaced"]``. Returns None when there is no
    drawn holdout to report.
    """
    if not manifest:
        return None
    stats = manifest.get("stats", {})
    held = [r for r in sp_recs if r["split"] == hc.HOLDOUT_SPLIT]
    test = [r for r in sp_recs if r["split"] == "test"]

    def frames(recs):
        return [(r["gt"], flights[r["global_key"]][1], r["ranked"][0][0] == r["gt"])
                for r in recs if r["global_key"] in flights]

    mix = species_mix.compare(frames(test), frames(held))
    mix["unplaced"] = {k: sum(1 for r in recs if r["global_key"] not in flights)
                       for k, recs in (("a", test), ("b", held))}
    return {"version": manifest.get("version", ""),
            "n_flights": int(stats.get("n_held_groups", 0)),
            "n_all_flights": int(stats.get("n_groups", 0)),
            "n_drawn": int(stats.get("n_held", 0)),
            "n_ungradeable": int(stats.get("n_species_ungradeable", 0)),
            "held": _rate(held),
            "mix": mix}


def flight_rows(flight: dict) -> list[dict]:
    """The rows flight_holdout.csv carries. The drawn row is a count only: the
    frames it counts beyond the graded row have no answer to score."""
    held = flight["held"]
    return [{"population": FLIGHT_GRADED_ROW, "n_frames": held["n"],
             "n_correct_top1": held["correct"],
             "top1_accuracy": hc.fmt(held["top1"])},
            {"population": FLIGHT_DRAWN_ROW, "n_frames": flight["n_drawn"],
             "n_correct_top1": "", "top1_accuracy": ""}]


def write_flight_holdout(out_dir: str, flight: dict | None) -> None:
    """Written whenever a holdout is drawn. Absent, no file: a build reading a
    snapshot without one skips the check rather than failing on it."""
    if flight is None:
        return
    with open(os.path.join(out_dir, FLIGHT_CSV), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(flight_rows(flight))


def write_tables(out_dir: str, sp_recs) -> None:
    """Both tables this module owns, named once so a caller cannot write the
    test one and forget the flight one. The flight table is skipped when no
    holdout is drawn."""
    flights = load_flights()
    write_held_out(out_dir, measure(sp_recs, flights))
    write_flight_holdout(out_dir, measure_flight_holdout(sp_recs, load_manifest(), flights))


def rows(result: dict) -> list[dict]:
    """The rows held_out.csv carries, rates written the way every other table
    writes them so the snapshot check can compare within its tolerance."""
    out = [{"population": name, "n_frames": result[key]["n"],
            "n_correct_top1": result[key]["correct"],
            "top1_accuracy": hc.fmt(result[key]["top1"])}
           for name, key in POPULATIONS]
    out.append({"population": UNPLACED_ROW, "n_frames": result["unplaced"],
                "n_correct_top1": "", "top1_accuracy": ""})
    return out


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _flight_sentences(flight: dict) -> str:
    """What the drawn flight holdout adds to the note.

    Names the version, the flights, the frames and the species it cannot
    grade, every one of them read off the draw's own record. Kept apart from
    ``note`` so each sentence stays short enough to read once.
    """
    held, n_f, n_ug = flight["held"], flight["n_flights"], flight["n_ungradeable"]
    n_all = flight["n_all_flights"]
    ver = flight["version"] or "v1"
    if not n_f or not held["n"]:
        return (f'<p class="note">A flight holdout ({ver}) is on record, and no frame '
                f'on it carries an answer to score yet.</p>')
    # Four sentences open, because the guard has to be read where the rate is:
    # these are not the test frames, so the two rates cannot be subtracted. How
    # the holdout was drawn, and which species it cannot grade at all, are read
    # once by someone checking us, so they wait behind a summary line.
    line = (f'<p class="note"><b>A second score, on flights held back whole.</b> '
            f'The first guess is right on {_pct(held["top1"])} of the {held["n"]:,} '
            f'frames on the {n_f:,} held-back flights that carry an answer. These are '
            f'not the test frames, so do not subtract one rate from the other.</p>')
    rest = (f'<p class="note">The {ver} flight holdout holds {n_f:,} of the '
            f'{n_all:,} flights back, whole. ' if n_all else
            f'<p class="note">The {ver} flight holdout holds {n_f:,} whole flights '
            f'back. ')
    rest += ('No train frame sits on any of them, so nothing counted there is a '
             'near-copy of a frame the labels already know. The two sets do not hold '
             'the same species in the same shares, so the two rates grade two '
             'different sets of frames.</p>')
    if n_ug:
        rest += (f'<p class="note">{n_ug:,} species cannot be graded this way, because '
                 f'each one sits on a single flight. Holding that flight would leave '
                 f'the model nothing to learn the species from, so it stays in '
                 f'train.</p>')
    else:
        rest += ('<p class="note">Every species was flown more than once, so none is '
                 'left ungraded.</p>')
    return line + _mix_sentences(flight.get("mix")) + more(
        "How the held-back flights were drawn", rest)


def _pts(x: float) -> str:
    return f"{100 * x:+.1f}".replace("-", "&minus;")


def _range_words(w: dict) -> str:
    """'between X and Y points', or empty when no draw gave a difference."""
    if w["ci95"] is None:
        return ""
    lo, hi = w["ci95"]
    return f"between {_pts(lo)} and {_pts(hi)} points"


def _mix_sentences(mix: dict | None) -> str:
    """The two rates on the same species mix, beside the guard.

    Raw per-frame rates on the shared species, both rates reweighted to the
    combined species mix, the difference with its range, the same difference
    on each set's own mix and whether the three agree in sign, and, behind a
    summary line, how the mix and the range are made and the frames each set
    holds on species the other does not. Empty when there is nothing to
    compare, and said in words when no species is shared.
    """
    if not mix:
        return ""
    if not mix["n_shared_species"]:
        return ('<p class="note">The test frames and the held-back flights share no '
                'species, so the two rates cannot be read on the same species mix.</p>')
    raw, ex, ws = mix["raw"], mix["excluded"], mix["weightings"]
    head = ws["combined"]
    std, ci = head["standardized"], head["ci95"]
    verdict = ("the gap is not measured" if ci is None else
               "the two rates agree within their uncertainty" if ci[0] <= 0 <= ci[1] else
               "the held-back flights score higher" if ci[0] > 0 else
               "the held-back flights score lower")
    line = (f'<p class="note"><b>Read on the same species, {verdict}.</b> On the '
            f'{mix["n_shared_species"]:,} species both sets hold, the first guess is '
            f'right on {_pct(raw["a"])} of {mix["frames"]["a"]:,} test frames and '
            f'{_pct(raw["b"])} of {mix["frames"]["b"]:,} held-back frames. Given the '
            f'same mix of those species, it is {_pct(std["a"])} and {_pct(std["b"])}, '
            f'held-back minus test {_pts(head["difference"])} points.')
    if ci is not None:
        line += f' We are 95% sure the true gap is {_range_words(head)}.'
    line += '</p><p class="note">'
    for key, name in (("a", "the test frames' own mix"),
                      ("b", "the held-back flights' own mix")):
        w = ws[key]
        line += f'On {name} the gap is {_pts(w["difference"])} points'
        line += f', 95% sure {_range_words(w)}. ' if w["ci95"] is not None else '. '
    signs = {(w["difference"] > 0) - (w["difference"] < 0) for w in ws.values()}
    spans_zero = any(w["ci95"] is None or w["ci95"][0] <= 0 <= w["ci95"][1]
                     for w in ws.values())
    if len(signs) > 1:
        line += ('Which set scores higher depends on the mix, so the direction of the '
                 'gap is not settled.</p>')
    elif spans_zero:
        line += ('All three mixes put the gap on the same side, but a range that '
                 'includes zero leaves the direction of the gap unsettled.</p>')
    else:
        line += 'All three mixes put the gap on the same side.</p>'
    rest = (f'<p class="note">The headline mix counts each species by its frames in '
            f'both sets added together, so neither set\'s mix is favoured. For each '
            f'range we re-ran the count {mix["n_draws"]:,} times, each time drawing whole '
            f'sites at random. Frames from one site are alike, and the two sets cover '
            f'{mix["n_sites"]:,} sites. A drawn site brings its frames in both sets. '
            f'In {mix["draws_short"]:,} of the {mix["n_draws"]:,} re-runs some species '
            f'had no frame left in one set. That species was left out of the re-run, '
            f'and the others\' weights scaled up to fill its place. ')
    if mix["draws_empty"]:
        rest += (f'In {mix["draws_empty"]:,} no shared species was left and the re-run '
                 f'was not counted. ')
    rest += (f'The seed is fixed so a rebuild prints the same range. Left out, because '
             f'only one set holds them: {ex["a"]["frames"]:,} test frames on '
             f'{ex["a"]["species"]:,} species and {ex["b"]["frames"]:,} held-back frames '
             f'on {ex["b"]["species"]:,} species.')
    unplaced = mix.get("unplaced", {})
    if any(unplaced.values()):
        rest += (f' Left out because they cannot be placed on a site: '
                 f'{unplaced["a"]:,} test frames and {unplaced["b"]:,} held-back '
                 f'frames.')
    return line + more("How the same species mix is made", rest + '</p>')


def note(result: dict, flight: dict | None = None) -> str:
    """The one paragraph the species panel prints from this file. Every rate
    names its population and n, and the empty case is said in words.

    ``flight`` is ``measure_flight_holdout``'s result, printed beside the test
    score. None, and the paragraph is the one a checkout without a drawn
    holdout gets.
    """
    t, u = result["test"], result["unseen"]
    unplaced = result["unplaced"]
    if u["n"]:
        verdict = (f'No: {u["n"]:,} test frames come from a flight with no train frame, '
                   f'so not every test frame shares its flight with the rest.')
    else:
        verdict = ('Yes: every test frame shares its flight, one date over one site, with '
                   'a train frame, so no test frame comes from a flight the labels never '
                   'saw.')
    line = (f'<p class="note"><b>{verdict}</b> The rate to quote is the page\'s headline '
            f'number, not either rate this note prints: both are read over a subset of '
            f'the frames it covers. The first guess is right on '
            f'{_pct(t["top1"])} of the {t["n"]:,} test frames, mostly on flights that '
            f'also carried a train frame, so this leans on the same-flight subset. ')
    if u["n"]:
        line += (f'On the {u["n"]:,} test frames from flights with no train frame it is '
                 f'right on {_pct(u["top1"])}, the new-flight subset within the test '
                 f'split. Those frames hold different species in different shares from '
                 f'the rest, so the gap between the two rates is not the size of a '
                 f'leak. ')
    else:
        line += ('The second score below is on other frames, held back whole by flight, '
                 'a further new-flight subset. ' if flight else
                 'A set held back by whole flights would grade frames that share a '
                 'flight with no train frame. ')
    if unplaced:
        line += (f'{unplaced:,} test frame{"s" if unplaced != 1 else ""} could not be '
                 f'placed on a flight and {"are" if unplaced != 1 else "is"} left out. ')
    else:
        line += 'Every test frame could be placed on a flight. '
    if result["unplaced_train"]:
        line += (f'{result["unplaced_train"]:,} train frames could not be placed either, '
                 f'so their flights read as unseen. ')
    line = line.rstrip() + '</p>'
    if flight is not None:
        line += _flight_sentences(flight)
    return line


def write_held_out(out_dir: str, result: dict) -> None:
    with open(os.path.join(out_dir, "held_out.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(rows(result))
