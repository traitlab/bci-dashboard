"""The model-health panels that are mostly explanation, not measurement.

``weighting_panel`` answers how one model scores 81% and 56% at once;
``method_panel`` names the model, settings, and the untestable assumption.
Every figure is verified from ``core`` or recomputed from the same
records; nothing is hardcoded.
"""

from collections import Counter
from statistics import median

import core as hc
from assets import esc, panel, pctf, svg_hbar, svg_weight_pair
from crop_overlap import CROP_SIZE

# Said in two panels that a reader can open independently: the species table,
# where it explains what a confidence column of 0.86 means, and the candidates
# panel, where it explains why a short list holds nearly all of it. Written
# once so the two cannot say it in two voices.
CONFIDENCE_IS_SHARED = ("Pl@ntNet spreads 100% of its confidence across every "
                        "species it knows.")

# One colour and name per labelled-frame band, both bars of the weighting chart.
# All 4.5:1 against white so the in-bar number is readable.
#
# Known limitation: the ramp does not order by lightness (luminance 0.110, 0.180,
# 0.168, 0.175, 0.083; the two ends are the closest pair at 1.20:1), so without
# hue it carries no order. Fixing that is a new palette, not a contrast tweak.
BAND_COLOR = {"1": "#b71c1c", "2-4": "#d44215", "5-9": "#8d6e00",
              "10-24": "#4f812c", "25+": "#1b5e20"}
def _band_words():
    """Each labelled-frame band in words, and short enough for a chart label.

    Built from ``hc.SUPPORT_BUCKETS`` for the reason ``_conf_band_words``
    below is: retyped, "2 to 4 frames" keeps saying 4 after the band moves.
    The singular is the reason this is not ``f"{label} frames"`` throughout;
    it would read "1 frames" for the band holding a third of the species.
    """
    long_, short = {}, {}
    for lo, hi, lab in hc.SUPPORT_BUCKETS:
        noun = "frame" if hi == 1 else "frames"
        long_[lab] = (f"{lo} {noun}" if lo == hi
                      else f"{lo} or more {noun}" if hi >= 10 ** 9
                      else f"{lo} to {hi} {noun}")
        short[lab] = f"{lab} {noun}"
    return long_, short


BAND_WORD, BAND_SHORT = _band_words()

def _conf_band_words():
    """"0.7 to 0.8", not "[0.7,0.8)" (a botanist has no reason to know
    interval notation). Built from ``hc.CONF_BINS`` so a changed band
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

# The two ends of the near-miss comparison, read off the bands rather than
# retyped: 4 and 25 are the upper edge of the second band and the lower edge of
# the last, and the prose below prints both. Typed here they would keep saying
# "4 frames or fewer" after the bands moved.
THIN_MAX = hc.SUPPORT_BUCKETS[1][1]
FAT_MIN = hc.SUPPORT_BUCKETS[-1][0]


def _near_miss(recs):
    """Wrong first guesses, and the share whose right answer is still listed."""
    wrong = [r for r in recs if r["ranked"][0][0] != r["gt"]]
    got = sum(1 for r in wrong if r["gt"] in
              [b for b, _ in r["ranked"][:hc.N_CANDIDATES]])
    return len(wrong), got / len(wrong) if wrong else 0.0


def candidates_panel(*, recs, n_scored, gen_n, gen_none):
    """Where the five-candidate limit comes from, and what it hides. ``recs``
    is every frame with a prediction, species-level or not: a slightly
    larger set than ``n_scored``, the frames accuracy is measured on.
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
        f'<p class="note">Every request carried <code>nb-results={top}</code>: reply with '
        f'your {top} best guesses, best first. Pl@ntNet publishes no maximum and no default '
        f'for it, so a longer list would be capped only by how many candidates the model '
        f'has. We chose the {top}. It is a setting in our own <code>config.yaml</code> '
        f'(<code>identify_nb_results</code>), nobody wrote down why, and we can change it. '
        f'It is not a limit of the model.</p>'
        + f'<p class="note">The chart below counts the {len(recs):,} labelled frames that '
          f'have a cached Pl@ntNet answer. That is more than the {n_scored:,} frames the '
          f'accuracy rates are measured on. A list length can be read off a frame whose '
          f'label stops at the genus, but an accuracy cannot.</p>'
        + svg_hbar(rows, title=f"how long the returned list actually was, {len(recs):,} frames")
        + f'<p class="note">{full:,} of {len(recs):,} photos came back with a full {top} '
          f'({pctf(full / len(recs))}) and none came back with more. The shorter lists are '
          # One notation only for the floor, so a reader is not left matching a
          # percentage against a decimal to see they're the same cutoff.
          f'the other cut: <b>Pl@ntNet never returns a species it scores below '
          f'{floor:.3f}</b>. Of the {len(scores):,} guesses here, {at_floor} sit exactly on '
          f'{floor:.3f} and {just_above:,} more just above it, under {2 * floor:.3f}. '
          f'Nothing goes lower. A model that simply ran out of guesses would not stop dead '
          f'on a round number, so {floor:.3f} is a cut-off Pl@ntNet applies. A short list '
          f'means fewer than {top} '
          f'species cleared it.</p>'
          f'<p class="note">{CONFIDENCE_IS_SHARED} When it returns only {shortest}, '
          f'that species holds '
          f'{pctf(1 - hidden[shortest])} of the whole{mid_clause}. <b>When it returns a full '
          f'{top}, those {top} hold only {pctf(1 - hidden[top])} between them</b>, so a '
          f'typical {pctf(hidden[top])} sits on species we never received. On {half:,} of '
          f'the {full:,} full lists ({pctf(half / full)}) more than half the confidence '
          f'sits outside the {top}.</p>'
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
          f'<p class="note"><b>If that call is made, ask for more than a longer list.</b> '
          f'The same endpoint takes <code>detailed=true</code>, which also returns results '
          f'per genus and per family. A genus label is scored here by chopping the genus off '
          f'a predicted species name, and a family label cannot be scored offline at '
          f'all.</p>',
        anchor="why-only-five-guesses-per-photo")


def weighting_panel(*, per_species, sp_recs, support, buckets, now, n, n_sp,
                    corpus_block):
    """The four corpus-wide rates, and why per-species and per-frame ones
    differ. ``corpus_block`` is page copy, passed in by the caller so
    numbers and explanation stay together.
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
    singles = buckets[thin]["n_species"]
    return panel(
        # No "why X and Y disagree" clause here: the paragraph under the headline
        # grid answers that once.
        "Every labelled frame, scored on the centre crop: four rates",
        "<b>Quote the number at the top of the page, not these four.</b> These cover "
        "every labelled frame instead of the frozen sample, so they answer a different "
        "question. If you cite one of them anyway, cite the per-species rate, never the "
        # What the two rates each ask is said once, next to the headline cards
        # where a reader is looking at the numbers it explains.
        "per-frame one.",
        # No note restating the two rates: the summary names both, the headline cards
        # state the distinction, and the chart labels its own bars with it.
        corpus_block
        + svg_weight_pair(rows,
                          label_a=f"one vote per species ({n_sp} votes)",
                          label_b=f"one vote per frame ({n:,} votes)")
          # Name the bars by their own labels, not by position: the second share is
          # a sliver too thin to carry a printed label, so "2% of the bottom" sent a
          # reader looking for a 2% they could not find.
        + f'<p class="note">The {singles} single-frame species are '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the '
          f'one-vote-per-species bar but only '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the one-vote-per-frame one. '
          f'That slice is too thin to label there. '
          f'Pl@ntNet is right {pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} of the '
          f'time on species we labelled once, against '
          f'{pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} at {BAND_WORD[fat]}.</p>'
          # "Rare in our labels usually means rare in Pl@ntNet's photos too" sat
          # here, asserting the cause before the page had shown it. The warning
          # block below gives the same claim with its reason attached, which is
          # where a reader can weigh it.
          f'<p class="note">Misses differ at each end. On species with {THIN_MAX} frames '
          f'or fewer, the right name is still in the {hc.N_CANDIDATES} for {pctf(thin_in5)} of '
          f'{thin_n} misses. At {FAT_MIN}+ frames it is {pctf(fat_in5)} of {fat_n}. '
          f'Misses on common '
          f'species are near '
          f'misses settled from the short list; on rare ones the model does not know the '
          f'plant.</p>'
          f'<p class="note"><b>Set aside species under {hc.WELL_SAMPLED_MIN_N} frames and '
          f'the scores become {pctf(well_micro)} per frame and {pctf(well_macro)} per '
          f'species</b>, '
          f'{100 * (well_micro - well_macro):.0f} points apart, instead of the {gap:.0f} '
          f'between {pctf(now["micro_top1"])} and {pctf(now["macro_top1"])}. A '
          f'one-frame species scores only 0% or 100%, so those {singles} votes are coin '
          f'flips.</p>'
          f'<div class="warn"><strong>Read those rows as how common a species is, not as '
          f'something labelling changed.</strong> These predictions come from a frozen '
          f'Pl@ntNet regional '
          f'model that has never seen a BCI label, so labelling a species does not make '
          f'Pl@ntNet better at it. Common species simply have more reference photos '
          f'inside Pl@ntNet already. Extra labels buy knowledge instead: below about '
          f'{hc.WELL_SAMPLED_MIN_N} frames a per-species accuracy jumps around too much to '
          f'act on, and above it the species has a score steady enough to rank work by.</div>',
        # Both headline rates are in the summary and both move every snapshot.
        anchor="why-the-two-headline-scores-differ")


def method_panel(*, tag, n, n_sp, n_cand, checks):
    """Model, request settings, evaluated set, and the untestable assumption."""
    body = ('<ul class="prov">'
            # The tag is `<endpoint-slug>@<run-name>`, so it already carries the
            # endpoint; printing `identify/k-central-america` beside it said the
            # slug twice in one sentence, and the typed half could not follow a
            # move to another regional endpoint.
            f'<li>Predictions: model run <code>{esc(tag)}</code>, the Central '
            f'America regional model and not the worldwide one, so a regional '
            f'restriction is already in place.</li>'
            f'<li>Request settings: <code>nb-results={n_cand}</code>, '
            f'plus <code>no-reject=true</code>, organs detected '
            f'automatically, and <code>include-related-images=false</code>, on a '
            f'{CROP_SIZE}&nbsp;px centre crop of each frame photo. A correct answer at '
            f'position '
            f'{n_cand + 1} '
            f'or beyond was never returned and cannot be seen here.</li>'
            f'<li>Evaluated set: {n:,} frames across {n_sp} species carrying a botanist '
            f'label that names a species rather than only a genus. They are the historical '
            f'labelling record, not a random draw. These rates carry over to unlabelled '
            f'frames only if unlabelled frames look like labelled ones, and that is not '
            f'something we can check offline.</li>'
            f'<li>Where the labels came from, in the merge script\u2019s own words. '
            f'&ldquo;{esc(hc.gt_provenance())}&rdquo; The merge keeps the newer label, and '
            f'that batch has had no review step on Labelbox yet. '
            f'<code>labelling/gt_from_export.py</code> writes that line beside the label '
            f'file, so it always names the batch this page was built over.</li>'
            f'<li>Snapshot: this page reports one dated '
            f'<code>model-health-&lt;date&gt;/</code> folder, the latest state, with no trend '
            f'over earlier folders. Its model tag is read from its own '
            f'<code>run_log.txt</code>, which records the endpoint and the model run '
            f'name.</li>'
            f'<li>Every number here is recomputed from the source data at build time. '
            f'It is then checked against the {len(checks)} CSVs the measurement pass '
            f'wrote into the snapshot folder. A mismatch aborts the build.</li>'
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
