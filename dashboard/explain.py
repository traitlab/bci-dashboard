#!/usr/bin/env python3
"""Prose panels for the model-health dashboard.

Two panels that are mostly explanation rather than measurement live here, so
build_full.py stays a page assembler:

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

# One colour and name per labelled-frame band, both bars of the weighting chart.
# All 4.5:1 against white so the in-bar number is readable.
#
# Known limitation: the ramp does not order by lightness (luminance 0.110, 0.180,
# 0.168, 0.175, 0.083; the two ends are the closest pair at 1.20:1), so without
# hue it carries no order. Fixing that is a new palette, not a contrast tweak.
BAND_COLOR = {"1": "#b71c1c", "2-4": "#d44215", "5-9": "#8d6e00",
              "10-24": "#4f812c", "25+": "#1b5e20"}
BAND_WORD = {"1": "1 frame", "2-4": "2 to 4 frames", "5-9": "5 to 9 frames",
             "10-24": "10 to 24 frames", "25+": "25 or more frames"}
# The same bands, short enough for a chart row label. Built as f"{key} frames"
# they read "1 frames" for the band holding 51 of the 186 species.
BAND_SHORT = {"1": "1 frame", "2-4": "2-4 frames", "5-9": "5-9 frames",
              "10-24": "10-24 frames", "25+": "25+ frames"}

# Frames at or below this many labels are "thin" in the near-miss comparison.
THIN_MAX = 4
FAT_MIN = 25


def _near_miss(recs):
    """Wrong first guesses, and the share whose right answer is still listed."""
    wrong = [r for r in recs if r["ranked"][0][0] != r["gt"]]
    got = sum(1 for r in wrong if r["gt"] in [b for b, _ in r["ranked"][:5]])
    return len(wrong), got / len(wrong) if wrong else 0.0


def candidates_panel(*, recs, gen_n, gen_none):
    """Where the five-candidate limit comes from, and what it hides.

    ``recs`` is every frame that got a prediction, species-level or not, so the
    list-length picture covers the same photos the rest of the page scores.
    """
    lens = Counter(len(r["ranked"]) for r in recs)
    top = max(lens)
    full = lens[top]
    rows = [(f"{k} guess{'' if k == 1 else 'es'}", lens[k] / len(recs),
             f"{lens[k]:,} frames", "#1b5e20" if k == top else "#78909c")
            for k in range(1, top + 1) if lens[k]]
    # Two cuts, one from each end: our nb-results, and Pl@ntNet's floor on a
    # candidate worth returning, which is why a list can come back short.
    scores = [s for r in recs for _, s in r["ranked"]]
    floor = min(scores)
    # What makes it a floor rather than a coincidence: dense right above, stopping
    # dead on a round number. "Nothing is below the minimum" is true of any list.
    at_floor = sum(1 for s in scores if s == floor)
    just_above = sum(1 for s in scores if floor < s < 2 * floor)
    hidden = {n: median([1.0 - sum(s for _, s in r["ranked"])
                         for r in recs if len(r["ranked"]) == n])
              for n in lens if lens[n]}
    half = sum(1 for r in recs
               if len(r["ranked"]) == top and sum(s for _, s in r["ranked"]) < 0.5)
    # Read off the list lengths this corpus returned. Naming 1 and 4 outright
    # crashed on a corpus without them, and the point is the trend, not those two.
    shortest = min(hidden)
    middles = [k for k in sorted(hidden) if shortest < k < top]
    mid = middles[len(middles) // 2] if middles else None
    mid_clause = (f", a {mid}-guess photo {pctf(1 - hidden[mid])}" if mid else "")
    return panel(
        f"Why only {top} guesses per photo, and what that hides",
        f"<b>Two different limits cut that list, one at each end.</b> We asked for the best "
        f"{top}, and Pl@ntNet drops anything it scores below {floor:.1%} whether we asked for "
        f"it or not. Both put a ceiling on the numbers above.",
        # Explicit: the summary states the list length, which is a fetch setting
        # rather than a fixed fact, so it must not decide the anchor.
        f'<p class="note">Every request carried <code>nb-results={top}</code>: reply with your '
        f'{top} best guesses, best first. Pl@ntNet documents the setting only as a way to '
        f'"restrict size of output list of probable species", with no published maximum and no '
        f'published default, so the ceiling on a longer request is however many candidates the '
        f'model has for the photo. The {top} is an inherited <code>config.yaml</code> value '
        f'(<code>identify_nb_results: {top}</code>) with no recorded rationale, a setting to '
        f'revisit rather than a property of the model.</p>'
        + svg_hbar(rows, title=f"how long the returned list actually was, {len(recs):,} frames")
        + f'<p class="note">{full:,} of {len(recs):,} photos came back with a full {top} '
          f'({pctf(full / len(recs))}) and none came back with more. The shorter lists are the '
          f'other cut: <b>Pl@ntNet never returns a species it scores below {floor:.1%}</b>. '
          f'Of the {len(scores):,} guesses on this page, {just_above:,} score between '
          f'{floor:.3f} and {2 * floor:.3f} and {at_floor} sit on exactly {floor:.3f}, and '
          f'none goes lower. A model that simply had no smaller numbers would not stop dead '
          f'on a round one, so a short list means fewer than {top} species cleared that '
          f'bar.</p>'
          f'<p class="note">Pl@ntNet spreads 100% of its confidence across every species it '
          f'knows. A {shortest}-guess photo accounts for {pctf(1 - hidden[shortest])} of it'
          f'{mid_clause}, and <b>a full list of {top} only '
          f'{pctf(1 - hidden[top])}</b>: on those photos a typical {pctf(hidden[top])} of the '
          f'confidence sits on species we never received, and on {half:,} of the {full:,} full '
          f'lists ({pctf(half / full)}) more than half of it does.</p>'
          f'<p class="note"><b>What the cap hides is a right answer in position {top + 1}</b>, '
          f'indistinguishable here from Pl@ntNet never having heard of the plant. Both look '
          f'like a miss. The clearest symptom is among the {gen_n:,} frames whose botanist '
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
          f'Pl@ntNet will state both directly if asked.</p>',
        anchor="why-only-five-guesses-per-photo")


def weighting_panel(*, per_species, sp_recs, support, buckets, now, n, n_sp):
    """Why the frame-weighted and per-species scores differ, with a picture."""
    rows = []
    for lab in hc.BUCKET_ORDER:
        b = buckets.get(lab)
        if not b or not b["n_crowns"]:
            continue
        rows.append((BAND_WORD[lab], b["n_species"] / n_sp, b["n_crowns"] / n,
                     f'{b["n_species"]} species, {b["n_crowns"]:,} frames, '
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
        "<b>Same model, same centre crops, two ways of averaging.</b>",
        # No note restating the two rates: the summary names both, the headline cards
        # state the distinction, and the chart labels its own bars with it.
        svg_weight_pair(rows,
                          label_a=f"one vote per species ({n_sp} votes)",
                          label_b=f"one vote per frame ({n:,} votes)")
        + f'<p class="note">Picture {n_sp} classes, one per species, {n:,} students, one quiz. '
          f'Count students and the big classes decide; score each class once and a class of one '
          f'counts as much as <em>{esc(cap(big["species"]))}</em>\'s '
          f'{big["n_labelled_crowns"]:,}. <b>Quote the per-species number: a labelling '
          f'programme exists to move it.</b></p>'
          f'<p class="note">The {singles} single-frame species fill '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the top bar and '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the bottom, and the key says why: '
          f'{pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} right at one frame against '
          f'{pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} at {BAND_WORD[fat]} (rare in '
          f'our labels usually means rare in Pl@ntNet\'s photos).</p>'
          f'<p class="note">Misses differ at each end: the right name is still in the five for '
          f'{pctf(thin_in5)} of misses on species with {THIN_MAX} frames or fewer ({thin_n}), '
          f'against {pctf(fat_in5)} at {FAT_MIN}+ ({fat_n}). Misses on common species are near '
          f'misses settled from the short list; on rare ones the model does not know the '
          f'plant.</p>'
          f'<p class="note"><b>Set aside species under {hc.WELL_SAMPLED_MIN_N} frames and the '
          f'scores become {pctf(well_micro)} and {pctf(well_macro)}</b>, '
          f'{100 * (well_micro - well_macro):.0f} points apart instead of {gap:.0f}. A '
          f'one-frame species scores only 0% or 100%, so those {singles} votes are coin '
          f'flips.</p>',
        open_=True,
        # Both headline rates are in the summary and both move every snapshot.
        anchor="why-the-two-headline-scores-differ")


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
            f'1280&nbsp;px centre crop of each frame photo. A correct answer at position 6 '
            f'or beyond was never returned and cannot be seen here.</li>'
            f'<li>Evaluated set: {n:,} frames across {n_sp} species carrying a botanist '
            f'label that names a species rather than only a genus. They are the historical '
            f'labelling record, not a random draw, so these rates carry over to unlabelled '
            f'frames only under an assumption that cannot be tested offline.</li>'
            '<li>Ground truth: the July 2026 revision pass on Labelbox project '
            '<code>2024_bci</code> (exported 2026-08-06), merged over the older offline '
            'labels by <code>labelling/gt_from_export.py</code>: where a photo carries '
            'a July label it wins, everything else keeps the earlier label. The July '
            'batch has had no review step on Labelbox yet.</li>'
            f'<li>Snapshot: this page reports one dated '
            f'<code>model-health-&lt;date&gt;/</code> folder, the latest state, with no trend '
            f'over earlier folders. Its model tag is read from its own '
            f'<code>run_log.txt</code>, which records the endpoint and the model run '
            f'name.</li>'
            '<li>Every number here is recomputed from the source data at build time and '
            'cross-checked against the CSVs the measurement pass wrote into the snapshot '
            'folder:<ul>'
            + "".join(f"<li>{esc(c)}</li>" for c in checks)
            + '</ul>A mismatch aborts the build.</li>'
            '<li>Artifact: one HTML file that opens from a <code>file://</code> path, so it is '
            'mailable, archivable next to the snapshot it describes, and readable by a '
            'botanist or PI with no Python environment. It renders from the standard library '
            'alone, so it needs no environment to rebuild either.</li>'
            '<li>Rebuild: <code>python3 dashboard/measure.py</code> then '
            '<code>python3 dashboard/build_full.py</code>. Standard library '
            'only, same output every run, no network.</li></ul>')
    return panel("How this was measured, and what it does not tell you",
                 "<b>Read this before quoting any number outside the team.</b> It names "
                 "the model, the request settings, and the one assumption that cannot be "
                 "checked offline.", body)
