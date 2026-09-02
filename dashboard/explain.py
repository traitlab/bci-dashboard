"""The model-health panels that are mostly explanation rather than measurement.

``weighting_panel`` answers the question the two headline numbers provoke: how
one model scores 81% and 56% at once. ``method_panel`` names the model, the
request settings, and the assumption that cannot be checked offline.

Every figure arrives verified from ``core`` or is recomputed from the same
records. Nothing is hardcoded.
"""

from collections import Counter
from statistics import median

import core as hc
from assets import cap, esc, panel, pctf, svg_hbar, svg_weight_pair
from crop_overlap import CROP_SIZE

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

def _conf_band_words():
    """"0.7 to 0.8", not "[0.7,0.8)".

    Interval notation is a convention a botanist has no reason to know, and the
    half-open bracket is the part that carries the meaning. The keys are the
    band strings the CSVs and the run log use, and those stay: this maps them
    for display only, and is built from ``hc.CONF_BINS`` so a changed band
    cannot leave a stale phrase behind.
    """
    words = {}
    for lo, hi in hc.CONF_BINS:
        hi = min(hi, 1.0)
        words[f"[{lo:.1f},{hi:.1f})"] = (
            f"under {hi:.1f}" if lo == 0.0
            else f"{lo:.1f} and up" if hi >= 1.0
            else f"{lo:.1f} to {hi:.1f}")
    return words


CONF_BAND_WORDS = _conf_band_words()

# Frames at or below this many labels are "thin" in the near-miss comparison.
THIN_MAX = 4
FAT_MIN = 25


def _near_miss(recs):
    """Wrong first guesses, and the share whose right answer is still listed."""
    wrong = [r for r in recs if r["ranked"][0][0] != r["gt"]]
    got = sum(1 for r in wrong if r["gt"] in [b for b, _ in r["ranked"][:5]])
    return len(wrong), got / len(wrong) if wrong else 0.0


def candidates_panel(*, recs, n_scored, gen_n, gen_none):
    """Where the five-candidate limit comes from, and what it hides.

    ``recs`` is every frame that got a prediction, species-level or not, so the
    list-length picture covers a slightly larger set than ``n_scored``, the frames
    the accuracy rates are measured on. That difference is stated on the page:
    the count first appeared as a bare chart label, leaving a reader to guess why
    the page had two totals.
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
    mid_clause = (f", and {pctf(1 - hidden[mid])} when it returns {mid}" if mid else "")
    return panel(
        f"Why only {top} guesses per photo, and what that hides",
        f"<b>Two different limits cut that list, one at each end.</b> We asked for the best "
        f"{top}, and Pl@ntNet drops anything it scores below {floor:.3f} whether we asked "
        f"for "
        f"it or not. Both put a ceiling on the numbers above.",
        # Explicit: the summary states the list length, which is a fetch setting
        # rather than a fixed fact, so it must not decide the anchor.
        f'<p class="note">Every request carried <code>nb-results={top}</code>: reply with your '
        f'{top} best guesses, best first. Pl@ntNet describes the setting only as a way to '
        f'"restrict size of output list of probable species". It publishes no maximum and no '
        f'default. So if we asked for a longer list, the only ceiling would be how many '
        f'candidates the model has for that photo.</p>'
        f'<p class="note">The {top} is an inherited '
        f'<code>config.yaml</code> value (<code>identify_nb_results: {top}</code>) with no '
        f'recorded reason behind it. It is a setting to revisit, not a property of the '
        f'model.</p>'
        + f'<p class="note">The chart below counts the {len(recs):,} labelled frames that '
          f'have a cached Pl@ntNet answer. That is more than the {n_scored:,} frames the '
          f'accuracy rates are measured on. A list length can be read off a frame whose '
          f'label stops at the genus, but an accuracy cannot.</p>'
        + svg_hbar(rows, title=f"how long the returned list actually was, {len(recs):,} frames")
        + f'<p class="note">{full:,} of {len(recs):,} photos came back with a full {top} '
          f'({pctf(full / len(recs))}) and none came back with more. The shorter lists are the '
          # One notation for one number: the floor was printed as a percentage and
          # then as a decimal one sentence later, and the reader had to spot that
          # 0.1% and 0.001 were the same cutoff before the argument made sense.
          f'other cut: <b>Pl@ntNet never returns a species it scores below '
          f'{floor:.3f}</b>. '
          f'Of the {len(scores):,} guesses on this page, {at_floor} sit exactly on '
          f'{floor:.3f}, and {just_above:,} more sit just above it, under '
          f'{2 * floor:.3f}. Nothing goes lower.</p>'
          f'<p class="note">A model that simply had no smaller numbers would not stop dead '
          f'on a round one, so that floor is a rule and not a coincidence. A short list '
          f'therefore means fewer than {top} species cleared it.</p>'
          f'<p class="note">Pl@ntNet spreads 100% of its confidence across every species it '
          f'knows. When it returns only {shortest}, that species holds '
          f'{pctf(1 - hidden[shortest])} of the whole{mid_clause}. <b>When it returns a full '
          f'{top}, those {top} hold only {pctf(1 - hidden[top])} between them.</b></p>'
          f'<p class="note">So on '
          f'those photos a typical {pctf(hidden[top])} of the confidence sits on species we '
          f'never received. On {half:,} of the {full:,} full lists ({pctf(half / full)}) '
          f'more than half of it does.</p>'
          f'<p class="note"><b>What the cap hides is a right answer in position {top + 1}</b>, '
          f'indistinguishable here from Pl@ntNet never having heard of the plant. Both look '
          f'like a miss.</p>'
          f'<p class="note">The clearest symptom is among the {gen_n:,} frames whose botanist '
          f'label stops at the genus. On {gen_none:,} of them no species from that genus '
          f'appears anywhere in the {top}. For a genus the model plainly knows, some of those '
          f'right answers are sitting in the confidence we never got to see.</p>'
          f'<p class="note">Raising it is not free. These answers are cached, so rebuilding '
          f'this page costs nothing. But a longer list means asking Pl@ntNet again for every '
          f'photo in the collection, at one paid call each.</p>'
          f'<p class="note"><b>If that call is made, ask for more than a longer list.</b> The '
          f'same endpoint takes <code>detailed=true</code>, which returns "extra identification '
          f'results such as results per family and results per genus" under '
          f'<code>otherResults</code>. A genus label is scored here by chopping the genus '
          f'off a predicted species name, and a family label cannot be scored offline at '
          f'all. Pl@ntNet will state both directly if asked.</p>',
        anchor="why-only-five-guesses-per-photo")


def weighting_panel(*, per_species, sp_recs, support, buckets, now, n, n_sp,
                    corpus_block):
    """The four corpus-wide numbers, and why two of them disagree.

    ``corpus_block`` is the grid of the four rates and the caveats they inherit,
    built by the caller because they are page copy rather than a computation. They
    live inside this panel so the numbers and the explanation of them have one home.
    """
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
        # The "why X and Y disagree" clause is gone: the paragraph under the
        # headline grid answers that once, and repeating it here made this the
        # longest title on the page.
        "Every labelled frame, scored on the centre crop: four rates",
        "<b>Quote the number at the top of the page, not these four.</b> These cover "
        "every labelled frame instead of the frozen sample, so they answer a different "
        "question. If you cite one of them anyway, cite the per-species rate, never the "
        # What the two rates each ask used to be spelled out here and again in
        # HERO_READING, directly under the four cards. Said once, next to the
        # cards, where a reader is looking at the numbers it explains.
        "per-frame one.",
        # No note restating the two rates: the summary names both, the headline cards
        # state the distinction, and the chart labels its own bars with it.
        corpus_block
        + svg_weight_pair(rows,
                          label_a=f"one vote per species ({n_sp} votes)",
                          label_b=f"one vote per frame ({n:,} votes)")
        + f'<p class="note">Picture {n_sp} classes, one per species, {n:,} students, one quiz. '
          f'Count students and the big classes decide; score each class once and a class of one '
          f'counts as much as <em>{esc(cap(big["species"]))}</em>\'s '
          f'{big["n_labelled_crowns"]:,}.</p>'
          # Name the bars by their own labels, not by position: the second share is
          # a sliver too thin to carry a printed label, so "2% of the bottom" sent a
          # reader looking for a 2% they could not find.
          f'<p class="note">The {singles} single-frame species are '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the votes in the '
          f'one-vote-per-species bar. They are only '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the votes in the '
          f'one-vote-per-frame bar, a slice too thin to be labelled there. '
          f'The key says why. '
          f'Pl@ntNet is right {pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} of the '
          f'time on species we labelled once, against '
          f'{pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} at {BAND_WORD[fat]}. Rare in '
          f'our labels usually means rare in Pl@ntNet\'s photos too.</p>'
          f'<p class="note">Misses differ at each end. The right name is still in the five '
          f'for {pctf(thin_in5)} of misses on species with {THIN_MAX} frames or fewer '
          f'({thin_n} misses), against {pctf(fat_in5)} of the {fat_n} misses at '
          f'{FAT_MIN}+ frames. Misses on common '
          f'species are near '
          f'misses settled from the short list; on rare ones the model does not know the '
          f'plant.</p>'
          f'<p class="note"><b>Set aside species under {hc.WELL_SAMPLED_MIN_N} frames and '
          f'the scores become {pctf(well_micro)} per frame and {pctf(well_macro)} per '
          f'species</b>, '
          f'{100 * (well_micro - well_macro):.0f} points apart instead of {gap:.0f}. A '
          f'one-frame species scores only 0% or 100%, so those {singles} votes are coin '
          f'flips.</p>'
          # From the deleted accuracy-by-support panel, which was this panel's own
          # key redrawn as a bar chart plus this one paragraph.
          f'<div class="warn"><strong>Read the bands as how common a species is, not as '
          f'training data.</strong> These predictions come from a frozen Pl@ntNet regional '
          f'model that has never seen a single BCI label, so labelling a species does not '
          f'make Pl@ntNet better at it. Common species simply have more reference photos '
          f'inside Pl@ntNet already. What extra labels buy is knowledge: below about '
          f'{hc.WELL_SAMPLED_MIN_N} frames a per-species accuracy jumps around too much to '
          f'act on, and above it the species can enter the queue-ordering rule.</div>',
        # Both headline rates are in the summary and both move every snapshot.
        anchor="why-the-two-headline-scores-differ")


def method_panel(*, tag, n, n_sp, n_cand, checks):
    """Model, request settings, evaluated set, and the untestable assumption."""
    body = ('<ul class="prov">'
            f'<li>Predictions: <code>identify/k-central-america</code>, model run '
            f'<code>{esc(tag)}</code>. The Central America regional model, not the '
            f'worldwide one, so a regional restriction is already in place.</li>'
            f'<li>Request settings: <code>nb-results={n_cand}</code>, sent explicitly on every '
            f'request from <code>config.yaml</code> <code>identify_nb_results</code> and not '
            f'an API default, plus <code>no-reject=true</code>, organs detected '
            f'automatically, and <code>include-related-images=false</code>, on a '
            f'{CROP_SIZE}&nbsp;px centre crop of each frame photo. A correct answer at '
            f'position '
            f'{n_cand + 1} '
            f'or beyond was never returned and cannot be seen here.</li>'
            f'<li>Evaluated set: {n:,} frames across {n_sp} species carrying a botanist '
            f'label that names a species rather than only a genus. They are the historical '
            f'labelling record, not a random draw. So these rates carry over to unlabelled '
            f'frames only under an assumption that cannot be tested offline.</li>'
            f'<li>This is where the labels came from, in the merge script\u2019s own words. '
            f'&ldquo;{esc(hc.gt_provenance())}&rdquo; The merge keeps the newer label: where a '
            f'photo carries one from that export it wins, everything else keeps the '
            f'earlier offline label. That batch has had no review step on Labelbox yet. '
            f'The line is read from the sidecar <code>labelling/gt_from_export.py</code> '
            f'writes beside the label file. So it names the batch this page was built over, '
            f'not one fixed in the prose.</li>'
            f'<li>Snapshot: this page reports one dated '
            f'<code>model-health-&lt;date&gt;/</code> folder, the latest state, with no trend '
            f'over earlier folders. Its model tag is read from its own '
            f'<code>run_log.txt</code>, which records the endpoint and the model run '
            f'name.</li>'
            f'<li>Every number here is recomputed from the source data at build time and '
            f'cross-checked against the {len(checks)} CSVs the measurement pass wrote into '
            f'the snapshot folder. A mismatch aborts the build.</li>'
            # Build provenance is a maintainer's question, not a reader's, and it
            # lives in the README beside the source. One line stays so an archived
            # copy of this page still says where to look.
            '<li>Rebuild: see the README beside this dashboard&rsquo;s source.</li></ul>')
    # Two panels above already end "and what it does not measure"/"does not
    # tell you". This one is provenance: which model, which frames, which files.
    return panel("How this was measured: the model, the frames, the files",
                 "<b>Read this before quoting any number outside the team.</b> It names "
                 "the model, the request settings, and the one assumption that cannot be "
                 "checked offline.", body, anchor="how-this-was-measured")
