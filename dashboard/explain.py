"""The model-health panels that are mostly explanation, not measurement.

``weighting_panel`` answers how one model scores two rates far apart at once,
counting species or counting frames; ``method_panel`` names the model, settings,
and the untestable assumption. Every figure is verified from ``core`` or
recomputed from the same records, so no rate is hardcoded here.

Only ``panels.py`` imports this, which normally reads as a seam nobody needed.
It stays separate anyway: the panels here answer "how was this number made" and
the ones in ``panels.py`` report the number, and dissolving three symbols back
into a module already over the 500-line convention moves the lines without
concentrating anything. ``BAND_SHORT`` is the one symbol crossing that is not a
panel, and it is a genuine leak this does not bless.
"""

import core as hc
from assets import esc, panel, pctf, svg_weight_pair
from crop_overlap import CROP_SIZE

# One colour and name per labelled-frame band, both bars of the weighting chart.
# All 4.5:1 against white so the in-bar number is readable.
#
# Known limitation: the ramp does not order by lightness (luminance 0.110, 0.179,
# 0.168, 0.175, 0.083; the two ends sit at 1.20:1 and the closest pair, 2-4
# against 10-24, at 1.02:1), so without hue it carries no order. Fixing that is a
# new palette, not a contrast tweak.
BAND_COLOR = {"1": "#b71c1c", "2-4": "#d44215", "5-9": "#8d6e00",
              "10-24": "#4f812c", "25+": "#1b5e20"}
def _band_words():
    """Each labelled-frame band in words, and short enough for a chart label.

    Built from ``hc.SUPPORT_BUCKETS``: retyped, "2 to 4 frames" keeps saying 4
    after the band moves. The singular keeps this off ``f"{label} frames"``,
    which would read "1 frames".
    """
    long_, short = {}, {}
    for lo, hi, lab in hc.SUPPORT_BUCKETS:
        noun = "frame" if hi == 1 else "frames"
        long_[lab] = (f"{lo} {noun}" if lo == hi
                      else f"{lo} or more {noun}" if hi >= hc.NO_UPPER_BOUND
                      else f"{lo} to {hi} {noun}")
        short[lab] = f"{lab} {noun}"
    return long_, short


BAND_WORD, BAND_SHORT = _band_words()

def _conf_band_words():
    """"0.7 to 0.8", not "[0.7,0.8)": a botanist has no reason to know interval
    notation. Built from ``hc.CONF_BINS`` so a changed band cannot leave a stale
    phrase behind."""
    words = {}
    for lo, hi in hc.CONF_BINS:
        hi = min(hi, 1.0)
        words[f"[{lo:.1f},{hi:.1f})"] = (
            f"under {hi:.1f}" if lo == 0.0
            else f"{lo:.1f} and up" if hi >= 1.0
            else f"{lo:.1f} to {hi:.1f}")
    return words


CONF_BAND_WORDS = _conf_band_words()

# The two ends of the near-miss comparison, read off the bands: the upper edge
# of the second band and the lower edge of the last. The prose below prints both.
THIN_MAX = hc.SUPPORT_BUCKETS[1][1]
FAT_MIN = hc.SUPPORT_BUCKETS[-1][0]


def _near_miss(recs):
    """Wrong first guesses, and the share whose right answer is still listed."""
    wrong = [r for r in recs if r["ranked"][0][0] != r["gt"]]
    got = sum(1 for r in wrong if r["gt"] in
              [b for b, _ in r["ranked"][:hc.N_CANDIDATES]])
    return len(wrong), got / len(wrong) if wrong else 0.0



def weighting_panel(*, per_species, sp_recs, support, buckets, now, n, n_sp,
                    corpus_block):
    """The four corpus-wide rates, and why per-species and per-frame differ.
    ``corpus_block`` is page copy, passed in by the caller so numbers and
    explanation stay together."""
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
    well_sp = [d for d in per_species if d["n_labelled_frames"] >= hc.WELL_SAMPLED_MIN_N]
    well = [r for r in sp_recs if support[r["gt"]] >= hc.WELL_SAMPLED_MIN_N]
    well_micro = sum(1 for r in well if r["ranked"][0][0] == r["gt"]) / len(well)
    well_macro = sum(d["top1_accuracy"] for d in well_sp) / len(well_sp)
    gap = 100 * (now["micro_top1"] - now["macro_top1"])
    singles = buckets[thin]["n_species"]
    return panel(
        "Every labelled frame, scored on the centre crop: four rates",
        "<b>Quote the number at the top of the page, not these four.</b> These cover "
        "every labelled frame instead of the frozen sample, so they answer a different "
        "question. If you cite one of them anyway, cite the per-species rate, never the "
        # What the two rates each ask is said once, next to the headline cards,
        # where a reader is looking at the numbers it explains.
        "per-frame one.",
        corpus_block
        + svg_weight_pair(rows,
                          label_a=f"one vote per species ({n_sp} votes)",
                          label_b=f"one vote per frame ({n:,} votes)")
          # Name the bars by their own labels, not by position: the second share
          # is a sliver too thin to carry a printed label.
        + f'<p class="note">The {singles} single-frame species are '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the '
          f'one-vote-per-species bar but only '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the one-vote-per-frame one. '
          f'That slice is too thin to label there. '
          f'Pl@ntNet is right {pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} of the '
          f'time on species we labelled once, against '
          f'{pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} at {BAND_WORD[fat]}.</p>'
          # No cause asserted here: the warning block below gives that claim
          # with its reason attached, where a reader can weigh it.
          f'<p class="note">Misses differ at each end. On species with {THIN_MAX} frames '
          f'or fewer, the right name is still in the {hc.N_CANDIDATES} for {pctf(thin_in5)} of '
          f'{thin_n} misses. At {FAT_MIN}+ frames it is {pctf(fat_in5)} of {fat_n}. '
          f'Misses on common '
          f'species are near '
          f'misses settled from the short list; on rare ones the model does not know the '
          f'plant.</p>'
          f'<p class="note"><b>Set aside species under {hc.WELL_SAMPLED_MIN_N} frames and '
          f'the scores become {pctf(well_micro)} per frame and {pctf(well_macro)} per '
          f'species.</b> '
          f'That is {100 * (well_micro - well_macro):.0f} points apart, instead of the '
          f'{gap:.0f} between {pctf(now["micro_top1"])} and {pctf(now["macro_top1"])}. A '
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
            # endpoint; a typed one could not follow a move to another endpoint.
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
            # Build provenance is a maintainer's question, not a reader's. One
            # line stays so an archived copy of this page says where to look.
            '<li>Rebuild: see the README beside this dashboard&rsquo;s source.</li></ul>')
    # This one is provenance: which model, which frames, which files.
    return panel("How this was measured: the model, the frames, the files",
                 "<b>Read this before quoting any number outside the team.</b> It names "
                 "the model, the request settings, and the one assumption that cannot be "
                 "checked offline.", body, anchor="how-this-was-measured")
