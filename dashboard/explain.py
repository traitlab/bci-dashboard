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
from assets import esc, panel, pctf, table
from crop_overlap import CROP_SIZE


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
        rows.append([BAND_WORD[lab], f'{b["n_species"]:,}', f'{b["n_crowns"]:,}',
                     f'{100 * b["n_species"] / n_sp:.0f}%',
                     f'{100 * b["n_crowns"] / n:.0f}%',
                     pctf(b["c1"] / b["n_crowns"])])
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
        "Why the two headline scores differ: the same frames, four rates",
        # The two rates this panel explains, as the cards at the top print them.
        # Which one to quote is said once, on its card, and not again here.
        f"<b>{pctf(now['macro_top1'])} per species and {pctf(now['micro_top1'])} per "
        f"frame, on the same frames.</b>",
        corpus_block
        # A table rather than the two stacked bars this used to draw. The shares
        # the argument turns on are 2% and 6%, too thin to carry a printed label
        # in a bar, so the bars had to be read back out in a sentence underneath.
        # Side by side in two columns they are read off directly.
        + f'<p class="note"><b>Each species casts one vote per species, each frame one '
          f'vote per frame</b>: {n_sp} votes against {n:,}.</p>'
        + table([("Labelled frames per species", False), ("Species", True),
                 ("Frames", True), ("Share of the per-species vote", True),
                 ("Share of the per-frame vote", True), ("First guess right", True)],
                rows, source="support_buckets.csv")
        + f'<p class="note"><b>Read the two share columns against each other.</b> The '
          f'{singles} single-frame species carry '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the per-species vote and '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the per-frame one. They are '
          f'also the row Pl@ntNet gets right least often, '
          f'{pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} against '
          f'{pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} at {BAND_WORD[fat]}. '
          f'That is the gap between the two headline rates.</p>'
          # No cause asserted here: the warning block below gives that claim
          # with its reason attached, where a reader can weigh it.
          f'<p class="note">Misses differ at each end. On species with {THIN_MAX} frames '
          f'or fewer, the right name is still in the {hc.N_CANDIDATES} for {pctf(thin_in5)} '
          f'of {thin_n} misses. At {FAT_MIN}+ it is {pctf(fat_in5)} of {fat_n}. Misses on '
          f'common species are near misses; on rare ones the model does not know the '
          f'plant.</p>'
          f'<p class="note"><b>Set aside species under {hc.WELL_SAMPLED_MIN_N} frames and '
          f'the scores become {pctf(well_micro)} per frame and {pctf(well_macro)} per '
          f'species</b>. That is {100 * (well_micro - well_macro):.0f} points apart, not '
          f'the {gap:.0f} between {pctf(now["micro_top1"])} and {pctf(now["macro_top1"])}. A '
          f'one-frame species scores only 0% or 100%, so those {singles} votes are coin '
          f'flips.</p>'
          f'<div class="warn"><strong>Read those rows as how common a species is, not as '
          f'something labelling changed.</strong> The model dates from '
          f'{hc.PLANTNET_MODEL_VERSION} and our labels did not move it. Common species '
          f'have more reference photos inside Pl@ntNet. What extra labels buy is a rate '
          f'steady enough to act on, which takes about {hc.WELL_SAMPLED_MIN_N} '
          f'frames.</div>',
        # Both headline rates are in the summary and both move every snapshot.
        anchor="why-the-two-headline-scores-differ")


def method_panel(*, tag, n, n_sp, n_cand, checks, out_of_scope=None, out_of_scope_in_world=None):
    """Model, request settings, evaluated set, and the untestable assumption."""
    scope_sentence = ""
    if out_of_scope:
        scope_sentence = (
            f' That restriction excludes {len(out_of_scope)} species BCI has recorded, '
            f'checked against the region’s own species list.')
        if out_of_scope_in_world is not None:
            scope_sentence += (
                f' All {out_of_scope_in_world} of them are on the worldwide list, so the '
                f'region, not the model, is why they never came back.')
    body = ('<ul class="prov">'
            # The tag is `<endpoint-slug>@<run-name>`, so it already carries the
            # endpoint; a typed one could not follow a move to another endpoint.
            f'<li>Predictions: model run {esc(tag)}, the '
            f'{esc(hc.flora_name())} model, so a regional restriction is already '
            f'in place.{scope_sentence}</li>'
            # The date is the whole point of this item. Without it the claim
            # underneath is an assertion; with it, it is a comparison of two
            # dates a reader can check.
            f'<li>Model version: Pl@ntNet reports the model of '
            f'{esc(hc.plantnet_version_words())}, unchanged on '
            f'{esc(hc.date_words(hc.PLANTNET_VERSION_CHECKED))}. BCI labels were first '
            f'sent to Pl@ntNet in July 2026, after that date, so none is in it. Whether '
            f'BCI photos reached it some other way, we cannot say. The {n:,} cached '
            f'answers predate the version field. Every dated answer we hold names this '
            f'same model.</li>'
            f'<li>Request: the settings at the foot of this page, on a '
            f'{CROP_SIZE}&nbsp;px centre crop, organs detected automatically. A correct '
            f'answer at position {n_cand + 1} or beyond was never returned and cannot be '
            f'seen here.</li>'
            f'<li>Evaluated set: {n:,} frames across {n_sp} species whose botanist label '
            f'names a species rather than only a genus. They are what was labelled, not '
            f'a random draw. The rates carry over to unlabelled frames only if those look '
            f'like the labelled ones, which cannot be checked offline.</li>'
            f'<li>Labels: merged from the Labelbox export of '
            f'{esc(hc.gt_export_date_words())}. The merge keeps the newer label, and '
            f'that batch has had no Labelbox review step yet.</li>'
            # Where the snapshot sits and how to rebuild it are a maintainer's
            # questions, not a reader's, and naming a folder on a machine the
            # reader has no access to answers neither. What a reader can use is
            # that the numbers are recomputed and cross-checked every build.
            f'<li>Snapshot: one dated folder, the latest state, with no trend over '
            f'earlier folders. Every number is recomputed at build time and checked '
            f'against the {len(checks)} tables the measurement pass wrote. A mismatch '
            f'aborts the build.</li></ul>')
    # This one is provenance: which model, which frames, which files.
    return panel("How this was measured: the model, the frames, the files",
                 "<b>Read this before quoting any number outside the team.</b>",
                 body, anchor="how-this-was-measured")
