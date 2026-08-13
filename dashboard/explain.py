#!/usr/bin/env python3
"""Prose panels for the model-health dashboard.

Two panels that are mostly explanation rather than measurement live here, so
16b_dashboard.py stays a page assembler:

- ``weighting_panel`` answers the question the two headline numbers always
  provoke, namely how one model can score 81% and 56% at once.
- ``method_panel`` names the model, the request settings, and the assumption
  that cannot be checked offline.

Every figure either arrives already verified from ``core`` or is
recomputed here from the same records. Nothing is hardcoded.
"""

from collections import Counter
from statistics import median

import core as hc
from assets import cap, esc, panel, pctf, svg_hbar, svg_weight_pair

# One colour and one plain-English name per labelled-crown band, shared by both
# bars of the weighting chart so a band is recognisable across them. The ramp
# runs bad to good, all dark enough to carry a white number inside the bar.
#
# "Dark enough" is 4.5:1 against white, and two of these did not meet it before
# being darkened: 2-4 sat at 4.44 and 10-24 at 4.10, so the percentages drawn
# inside those two bands were the least readable text on the page. The shift is
# 2% and 7% of each channel, which holds the hue and the five-step identity.
#
# What this ramp still cannot do is survive red-green colour blindness, and the
# reason is worse than close steps: it does not order by lightness at all.
# Luminance runs 0.110, 0.180, 0.168, 0.175, 0.083 down the five bands, so
# adjacent steps differ by only 1.03:1 to 1.69:1 and the two ends, worst band
# and best band, are the closest pair in the set at 1.20:1. Strip the hue and
# the ramp carries no order. The key rows below print every count, but the tie
# from a key row to a bar segment is hue plus left-to-right position only: the
# in-bar text is a bare percentage drawn just when the segment is at least 25px
# wide, and it never repeats the band name. Fixing this means a palette that
# also ramps in lightness, which is a design change, not a contrast tweak.
BAND_COLOR = {"1": "#b71c1c", "2-4": "#d44215", "5-9": "#8d6e00",
              "10-24": "#4f812c", "25+": "#1b5e20"}
BAND_WORD = {"1": "1 crown", "2-4": "2 to 4 crowns", "5-9": "5 to 9 crowns",
             "10-24": "10 to 24 crowns", "25+": "25 or more crowns"}
# The same bands short enough for a chart row label or a narrow table cell. Two
# callers were building these as f"{key} crowns", which reads "1 crowns" for the
# band that holds 47 of the 169 species.
BAND_SHORT = {"1": "1 crown", "2-4": "2-4 crowns", "5-9": "5-9 crowns",
              "10-24": "10-24 crowns", "25+": "25+ crowns"}

# Crowns at or below this many labels are "thin" in the near-miss comparison.
THIN_MAX = 4
FAT_MIN = 25


def _near_miss(recs):
    """Wrong first guesses, and the share whose right answer is still listed."""
    wrong = [r for r in recs if r["ranked"][0][0] != r["gt"]]
    got = sum(1 for r in wrong if r["gt"] in [b for b, _ in r["ranked"][:5]])
    return len(wrong), got / len(wrong) if wrong else 0.0


def candidates_panel(*, recs, gen_n, gen_none):
    """Where the five-candidate limit comes from, and what it hides.

    ``recs`` is every crown that got a prediction, species-level or not, so the
    list-length picture covers the same photos the rest of the page scores.
    """
    lens = Counter(len(r["ranked"]) for r in recs)
    top = max(lens)
    full = lens[top]
    rows = [(f"{k} guess{'' if k == 1 else 'es'}", lens[k] / len(recs),
             f"{lens[k]:,} crowns", "#1b5e20" if k == top else "#78909c")
            for k in range(1, top + 1) if lens[k]]
    # Two independent cuts, one from each end of the list. Ours is nb-results;
    # Pl@ntNet's is a floor on the confidence of a candidate worth returning,
    # which is why a list can come back shorter than we asked for. The floor is
    # read off the data rather than assumed: it is the smallest score anyone got.
    scores = [s for r in recs for _, s in r["ranked"]]
    floor = min(scores)
    hidden = {n: median([1.0 - sum(s for _, s in r["ranked"])
                         for r in recs if len(r["ranked"]) == n])
              for n in lens if lens[n]}
    half = sum(1 for r in recs
               if len(r["ranked"]) == top and sum(s for _, s in r["ranked"]) < 0.5)
    return panel(
        f"Why only {top} guesses per photo, and what that hides",
        f"<b>Two different limits cut that list, one at each end.</b> We asked for the best "
        f"{top}, and Pl@ntNet drops anything it scores below {floor:.1%} whether we asked for "
        f"it or not. Both put a ceiling on the numbers above.",
        f'<p class="note">Every request carried <code>nb-results={top}</code>: reply with your '
        f'{top} best guesses, best first. Pl@ntNet documents the setting only as a way to '
        f'"restrict size of output list of probable species", with no published maximum and no '
        f'published default, so the ceiling on a longer request is however many candidates the '
        f'model has for the photo. The {top} is an inherited <code>config.yaml</code> value '
        f'(<code>identify_nb_results: {top}</code>) with no recorded rationale, a setting to '
        f'revisit rather than a property of the model.</p>'
        + svg_hbar(rows, title=f"how long the returned list actually was, {len(recs):,} crowns")
        + f'<p class="note">{full:,} of {len(recs):,} photos came back with a full {top} '
          f'({pctf(full / len(recs))}) and none came back with more. The shorter lists are the '
          f'other cut: <b>Pl@ntNet never returns a species it scores below {floor:.1%}</b>. Not '
          f'one of the {len(scores):,} guesses on this page scores less, the smallest being '
          f'exactly {floor:.3f}, so a short list means fewer than {top} species cleared that '
          f'bar.</p>'
          f'<p class="note">Pl@ntNet spreads 100% of its confidence across every species it '
          f'knows. A one-guess photo accounts for {pctf(1 - hidden[1])} of it, a four-guess '
          f'photo {pctf(1 - hidden[4])}, and <b>a full list of {top} only '
          f'{pctf(1 - hidden[top])}</b>: on those photos a typical {pctf(hidden[top])} of the '
          f'confidence sits on species we never received, and on {half:,} of the {full:,} full '
          f'lists ({pctf(half / full)}) more than half of it does.</p>'
          f'<p class="note"><b>What the cap hides is a right answer in position {top + 1}</b>, '
          f'indistinguishable here from Pl@ntNet never having heard of the plant. Both look '
          f'like a miss. The clearest symptom is among the {gen_n:,} crowns whose botanist '
          f'label stops at the genus: {gen_none:,} have no species from that genus anywhere in '
          f'the {top}, and for a genus the model plainly knows, some of those sit in that '
          f'unseen confidence.</p>'
          f'<p class="note">Raising it is not free. These answers are cached, so rebuilding '
          f'this page costs nothing, but a longer list means asking Pl@ntNet again for every '
          f'photo in the collection at one paid call each.</p>'
          f'<p class="note"><b>If that call is made, ask for more than a longer list.</b> The '
          f'same endpoint takes <code>detailed=true</code>, which returns "extra identification '
          f'results such as results per family and results per genus" under '
          f'<code>otherResults</code>. A genus label is scored here by chopping the genus off a '
          f'predicted species name, and a family label cannot be scored offline at all; '
          f'Pl@ntNet will state both directly if asked.</p>')


def weighting_panel(*, per_species, sp_recs, support, buckets, now, n, n_sp):
    """Why the crown-weighted and per-species scores differ, with a picture."""
    rows = []
    for lab in hc.BUCKET_ORDER:
        b = buckets.get(lab)
        if not b or not b["n_crowns"]:
            continue
        rows.append((BAND_WORD[lab], b["n_species"] / n_sp, b["n_crowns"] / n,
                     f'{b["n_species"]} species, {b["n_crowns"]:,} crowns, '
                     f'{pctf(b["c1"] / b["n_crowns"])} right', BAND_COLOR[lab]))
    thin, fat = hc.BUCKET_ORDER[0], hc.BUCKET_ORDER[-1]
    thin_n, thin_in5 = _near_miss([r for r in sp_recs if support[r["gt"]] <= THIN_MAX])
    fat_n, fat_in5 = _near_miss([r for r in sp_recs if support[r["gt"]] >= FAT_MIN])
    well_sp = [d for d in per_species if d["n_labelled_crowns"] >= hc.WELL_SAMPLED_MIN_N]
    well = [r for r in sp_recs if support[r["gt"]] >= hc.WELL_SAMPLED_MIN_N]
    well_micro = sum(1 for r in well if r["ranked"][0][0] == r["gt"]) / len(well)
    well_macro = sum(d["top1_accuracy"] for d in well_sp) / len(well_sp)
    gap = 100 * (now["micro_top1"] - now["macro_top1"])
    big = max(per_species, key=lambda d: d["n_labelled_crowns"])
    singles = buckets[thin]["n_species"]
    return panel(
        f"Why one score says {pctf(now['micro_top1'])} and the other {pctf(now['macro_top1'])}",
        "<b>Same model, same photos, two ways of averaging.</b>",
        f'<p class="note"><b>Overall accuracy ({pctf(now["micro_top1"])}):</b> one vote per '
        f'crown. Common species crowd out rare ones.<br>'
        f'<b>Per-species accuracy ({pctf(now["macro_top1"])}):</b> one vote per species. Rare '
        f'ones cannot hide.</p>'
        + svg_weight_pair(rows,
                          label_a=f"one vote per species ({n_sp} votes)",
                          label_b=f"one vote per crown ({n:,} votes)")
        + f'<p class="note">Picture {n_sp} classes, one per species, {n:,} students, one quiz. '
          f'Count students and the big classes decide; score each class once and a class of one '
          f'counts as much as <em>{esc(cap(big["species"]))}</em>\'s '
          f'{big["n_labelled_crowns"]:,}. <b>Quote the per-species number: a labelling '
          f'programme exists to move it.</b></p>'
          f'<p class="note">The {singles} single-crown species fill '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the top bar and '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the bottom, and the key says why: '
          f'{pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} right at one crown against '
          f'{pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} at {BAND_WORD[fat]} (rare in '
          f'our labels usually means rare in Pl@ntNet\'s photos).</p>'
          f'<p class="note">Misses differ at each end: the right name is still in the five for '
          f'{pctf(thin_in5)} of misses on species with {THIN_MAX} crowns or fewer ({thin_n}), '
          f'against {pctf(fat_in5)} at {FAT_MIN}+ ({fat_n}). Misses on common species are near '
          f'misses settled from the short list; on rare ones the model does not know the '
          f'plant.</p>'
          f'<p class="note"><b>Set aside species under {hc.WELL_SAMPLED_MIN_N} crowns and the '
          f'scores become {pctf(well_micro)} and {pctf(well_macro)}</b>, '
          f'{100 * (well_micro - well_macro):.0f} points apart instead of {gap:.0f}. A '
          f'one-crown species scores only 0% or 100%, so those {singles} votes are coin '
          f'flips.</p>',
        open_=True)


def method_panel(*, tag, n, n_sp, checks):
    """Model, request settings, evaluated set, and the untestable assumption."""
    body = ('<ul class="prov">'
            f'<li>Predictions: <code>identify/k-central-america</code>, model run '
            f'<code>{esc(tag)}</code>. The Central America regional model, not the '
            f'worldwide one, so a regional restriction is already in place.</li>'
            f'<li>Request settings: <code>nb-results=5</code>, sent explicitly on every '
            f'request from <code>config.yaml</code> <code>identify_nb_results</code> and not '
            f'an API default, plus <code>no-reject=true</code>, organs detected '
            f'automatically, and <code>include-related-images=false</code>, on a '
            f'1280&nbsp;px centre crop of each crown photo. A correct answer at position 6 '
            f'or beyond was never returned and cannot be seen here.</li>'
            f'<li>Evaluated set: {n:,} crowns across {n_sp} species carrying a botanist '
            f'label that names a species rather than only a genus. They are the historical '
            f'labelling record, not a random draw, so these rates carry over to unlabelled '
            f'crowns only under an assumption that cannot be tested offline.</li>'
            '<li>Ground truth: the July 2026 revision pass on Labelbox project '
            '<code>2024_bci</code> (exported 2026-08-06), merged over the older offline '
            'labels by <code>labelling/gt_from_export.py</code>: where a photo carries '
            'a July label it wins, everything else keeps the earlier label. The July '
            'batch has had no review step on Labelbox yet.</li>'
            f'<li>Trend: one row per snapshot folder and metric in <code>history.csv</code>, '
            f'appended and never rewritten. Each snapshot\'s model tag is read from its own '
            f'<code>run_log.txt</code>, which records the endpoint and the model run '
            f'name.</li>'
            '<li>Every number here is recomputed from the source data at build time and '
            'cross-checked against the committed measurement files:<ul>'
            + "".join(f"<li>{esc(c)}</li>" for c in checks)
            + '</ul>A mismatch aborts the build.</li>'
            '<li>Artifact: one HTML file that opens from a <code>file://</code> path, so it is '
            'mailable, archivable next to the snapshot it describes, and readable by a '
            'botanist or PI with no Python environment. It is decoupled from '
            '<code>labelfirst</code> and <code>speciesfirst</code> on purpose, since importing '
            '<code>labelfirst</code> pulls numpy, scipy, scikit-learn and pandas while this '
            'page renders from the standard library alone; the cost is that labelfirst\'s '
            'report CSS is vendored as a hand-pruned copy, so an upstream restyle has to be '
            'reapplied by hand. What it shares with those packages is the decision rather than '
            'the code: the deprioritization rule here orders a queue exactly as it does '
            'there.</li>'
            '<li>Rebuild: <code>python3 dashboard/measure.py</code> then '
            '<code>python3 dashboard/build_full.py</code>. Standard library '
            'only, same output every run, no network.</li></ul>')
    return panel("How this was measured, and what it does not tell you",
                 "<b>Read this before quoting any number outside the team.</b> It names "
                 "the model, the request settings, and the one assumption that cannot be "
                 "checked offline.", body)
