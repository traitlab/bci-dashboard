"""The frozen experiment's two panels: its method, and its warnings.

One question, asked once on a set-aside sample and read once: does outlining
the trees first beat sending the middle of the photo. ``confirmatory_hero``
draws the two rates, ``p_confirmatory`` says what was done to each frame, and
``p_caveats`` carries the plan's two warnings in the plan's own words.

Separate from ``panels.py`` because the quotes are literals nobody reworks.
"""

from __future__ import annotations

from assets import esc, hero, panel, pctf
from figures import CONFIRMATORY_CSV
from panels import CAMERA_IS, CENTRE_CROP_IS

def cam_phrase(cameras):
    """Name the camera in the queue page's words.

    Read from the frame keys rather than assumed, so a future sample carrying
    both cameras does not render as one camera with two names.
    """
    return (CAMERA_IS.get(cameras)
            or f"these cameras: <code>{esc(cameras)}</code>")

def pfmt(p, draws):
    """A bootstrap p that came back zero is a resolution limit, not a zero.

    Printing 0.00000 claims a precision the resamples cannot buy, so a p below
    one draw is reported as the bound ``draws`` supports.
    """
    floor = 1.0 / draws
    return f"&lt; {floor:.4f}" if p < floor else f"= {p:.5f}"

def confirmatory_hero(cf):
    """The two ways of asking, side by side, outline-first leading.

    Outline-first leads because it names the same thing the label names. The
    centre crop stays beside it because every other number on this page is
    measured that way, and the gap only reads with both in view.
    """
    if cf is None:
        raise SystemExit(
            f"{CONFIRMATORY_CSV} is missing, so the headline this page leads with "
            f"cannot be published. Run: python3 dashboard/score_confirmatory.py "
            f"--out {CONFIRMATORY_CSV}")
    if cf.get("stamp") != "CONFIRMATORY":
        raise SystemExit(
            f"the confirmatory result is stamped {cf.get('stamp')!r}, not "
            f"'CONFIRMATORY'. The stopping rule says the read happens once on the "
            f"complete set, so an exploratory number must not be published here.")
    # The card says what was done to the photo, not what the design calls it, so
    # the two numbers can be told apart without opening the panel below.
    ways = (("crown", "A botanist outlined the trees first"),
            ("photo", "We sent the middle of the photo"))
    return hero([
        (label, pctf(cf[f"{way}_top1"]),
         f'First guess right, on the {int(cf["n_frames"])} set-aside frames',
         f'{int(cf[f"{way}_hits"])} of {int(cf[f"{way}_n"])} frames right. '
         f'We are 95% sure the true rate is between '
         f'{pctf(cf[f"{way}_top1_site_lo"])} and {pctf(cf[f"{way}_top1_site_hi"])}.')
        for way, label in ways])

# Quoted, not summarised, from bci-dashboard-docs/hypothesis.md: both amendments
# require their own words, so they are literals rendered whole. If either changes
# there, change it here in the same session. A2_GLOSS is the one place a page
# prints vocabulary CONTEXT.md retires, which is why
# `tests/test_plain_english.py` drops this block along with the quote.
A2_GLOSS = (
    "<p>Three of the plan&rsquo;s words are not this page&rsquo;s. An <b>arm</b> is one "
    "way of asking. <b>Tiles</b> is a third way of asking, cut partway through. A "
    "<b>quadrat</b> is a marked-out ground plot.</p>")

# The plan's own figure for the crown arm, named once so the gloss cannot end up
# explaining a number the quote no longer carries. tests/test_pages.py holds the
# quote to hypothesis.md word for word.
A2_CROWN_TOP1 = "85.4%"

A2_PRIOR_EXPOSURE = (
    "<p>What that does and does not undermine:</p><ul>"
    "<li><strong>The tiles arm is blind.</strong> Condition 4 excludes every frame with a "
    "quadrat result, so no frame in this sample has ever been scored in that arm.</li>"
    "<li><strong>The frame-level aggregation is new.</strong> The area-weighted crown vote "
    "defined above has never been computed on any sample. What was reported earlier was a "
    f"per-crown top-1 accuracy of {A2_CROWN_TOP1} over the whole corpus, on a different "
    "unit and a "
    "different population.</li>"
    "<li><strong>The sample is new.</strong> These 300 frames were not chosen by looking at "
    "crown results.</li>"
    "<li><strong>But the number was not generated blind.</strong> An operator has seen "
    "crown-arm accuracy, at another unit and on a wider population, before this freeze.</li>"
    "</ul><p>The writeup must say this in those words. The crown arm's own accuracy "
    "carries a prior-exposure caveat. The paired comparison and the tiles arm do not.</p>")

A4_WHAT_THIS_COSTS = (
    "<p><strong>What this costs, stated plainly.</strong> The arm was dropped after its "
    "interim number had been seen, and no amount of reasoning removes that ordering. The two "
    "reasons above are structural and were both knowable on 2026-08-26, before A3. They were "
    "not acted on then. A reader is entitled to weigh that, and the writeup must carry this "
    "paragraph, not a summary of it.</p>")

def p_confirmatory(c):
    """The frozen read behind the headline: what was measured, and on what.

    Separate from the method panel because nothing here comes from the
    snapshot: it is a one-time read of frames fixed before the data existed,
    and mixing it with corpus numbers reports a rate on frames nobody measured.
    Ships collapsed: a reader arrives to look something up, not to read a
    method.
    """
    cf = c.cf
    if cf is None:
        raise SystemExit("p_confirmatory needs the frozen result; see confirmatory_hero")
    body = (
        f'<p class="note"><strong>What we did for the top number.</strong> Every crown a '
        f'botanist had outlined went to Pl@ntNet on its own. The answers were then '
        f'combined into one name for the frame, each crown counting for as much of the '
        f'frame as it covered. So the number says what naming '
        f'costs once someone has found the trees, not what a fully automatic pipeline '
        f'would score.</p>'
        f'<p class="note"><strong>What we did for the second number.</strong> We sent '
        f'{CENTRE_CROP_IS}. Nothing chose that square; it lands where it lands.</p>'
        f'<p class="note"><strong>Which frames, and how many.</strong> '
        f'{int(cf["n_frames"])} frames from {int(cf["n_sites"])} sites and '
        f'{int(cf["n_days"])} flight days, set aside before any of these numbers existed. '
        f'Both ways of asking were run on every one of them: {int(cf["crown_n"])} frames '
        f'each. The two rates therefore come from the same frames and can be compared '
        f'directly.</p>'
        f'<p class="note"><strong>Where the range comes from.</strong> Frames shot at the '
        f'same site look alike, so treating them as {int(cf["n_frames"])} independent tries '
        f'would make us look surer than we are. Instead we re-ran the whole count '
        f'{int(cf["bootstrap_draws"]):,} times. Each time we drew {int(cf["n_sites"])} sites '
        f'at random out of the same {int(cf["n_sites"])}, so some got picked twice and others '
        f'not at all. We kept the middle 95% of the answers. That '
        f'is the range on each card above.</p>')
    return panel(
        'Where these two numbers come from, and what we did to each frame',
        # A pointer, not a second copy of the warning: the next panel gives the
        # mechanism in full.
        "<b>The top number is real but it was not produced blind.</b> It was measured on "
        "frames that were fixed before anyone looked.", body,
        # An explicit id, pinned by a test, so a saved link outlives the wording
        # of the summary above it. slug() would build one from that wording.
        anchor="where-the-headline-comes-from")

def p_caveats(c):
    """The two caveats the design requires, quoted, plus what the rate is not.

    The amendment blocks reproduce ``hypothesis.md`` character for character,
    which is what it requires.
    """
    cf = c.cf
    if cf is None:
        raise SystemExit("p_caveats needs the frozen result; see confirmatory_hero")
    lo, hi = cf["crown_minus_photo_site_lo"], cf["crown_minus_photo_site_hi"]
    body = (
        # The always-visible note above states the gap. This panel adds the
        # range, which is the part the note leaves out.
        f'<p class="note"><strong>The gap between the two numbers is the finding, not '
        f'either number on its own.</strong> We are 95% sure the true gain is between '
        f'{100 * lo:+.1f} and {100 * hi:+.1f} points.</p>'
        f'<p class="note">On '
        f'{int(cf["crown_only_hits"])} frames outlining got the name right where the centre '
        f'crop got it wrong; on {int(cf["photo_only_hits"])} it went the other way. A gap '
        f'that lopsided almost never happens by chance, so we are confident it is real.</p>'
        # Named by what the test does, not by a term the page never defines.
        f'<p class="note">The plan named two tests, and both report a <b>p</b>: the chance '
        f'of a gap at least this big if outlining made no difference. Smaller means harder '
        f'to explain by luck. Re-drawing whole sites at random, rather than single frames, '
        f'gives p {pfmt(cf["p_cluster_bootstrap"], cf["bootstrap_draws"])}. An exact '
        f'McNemar test gives p = {cf["p_mcnemar_exact"]:.5f}. McNemar treats every frame as its own independent draw, and frames from '
        f'one site are not. So the plan named the re-drawing test as the answer where the '
        f'two disagree.</p>'
        # Its own paragraph: the range is a different claim from the p-values.
        f'<p class="note">The ordinary textbook range for the top number would read '
        f'{pctf(cf["crown_top1_wilson_lo"])} to {pctf(cf["crown_top1_wilson_hi"])}. It '
        f'treats every frame as its own independent draw too, so it is narrower than the '
        f'data supports. The two cards at the top carry the whole-site range instead.</p>'
        f'<div class="warn"><p><strong>The top number was not produced blind.</strong> '
        f'Before these frames were set aside, someone on the team had already seen how well '
        f'the outline-first method scored, on a different set of photos. That does not make '
        f'the number wrong and it does not touch the gap above, but the number has to travel '
        f'with this warning.</p>'
        # Warning first, then the glossary key, then the quoted text.
        f'<p>Below in full is amendment A2 of <code>hypothesis.md</code>, in the '
        f'plan&rsquo;s words.</p>'
        + A2_GLOSS +
        # The plan's "top-1" is left unglossed: the sentence below says what it
        # counts, and this page's own prose says "first guess" everywhere.
        f'<p>The {A2_CROWN_TOP1} it names counts only a first guess, per crown, over '
        f'every labelled photo. '
        f'Do not read it against the {pctf(cf["crown_top1"])} at the top, which scores a '
        f'whole frame on this fixed sample.</p>'
        f'{A2_PRIOR_EXPOSURE}</div>'
        f'<div class="warn"><p><strong>Tiles, the third way of asking, was dropped after '
        f'we had seen how it was doing.</strong> Dropping a method after glimpsing its '
        f'result is the kind of choice that can flatter the methods that survive. The '
        f'plan&rsquo;s own wording, amendment A4, follows.</p>'
        f'{A4_WHAT_THIS_COSTS}</div>'
        f'<div class="warn"><p><strong>What this rate is not.</strong></p><ul>'
        f'<li><strong>It does not measure a fully automatic pipeline.</strong> The method '
        f'is handed the botanist&rsquo;s outlines and asked only to name what is inside '
        f'them. Tiles, which would have answered with no outlines at all, is the one that '
        f'was dropped. Read {pctf(cf["crown_top1"])} as the cost of naming trees already '
        f'found.</li>'
        f'<li><strong>It is per frame, not per species.</strong> The sample carries '
        f'{int(cf["n_species"])} species, and the two commonest are '
        f'{pctf(cf["top2_species_share"])} of its {int(cf["n_frames"])} frames. So the rate '
        f'leans towards what the model already knows best. That is this page&rsquo;s own '
        f'objection to the <a href="#why-the-two-headline-scores-differ">'
        f'per-frame figure below</a>. The plan asked for no '
        f'per-species average here, so none is published.</li>'
        f'<li><strong>It is one camera, and not every site.</strong> Every frame '
        f'was shot with {cam_phrase(cf["cameras"])}, at {int(cf["n_sites"])} of '
        f'the 17 field sites. The drone carries a second camera, and no mission in '
        f'this design flies both, so nothing here says how the model reads that one.'
        f'</li></ul></div>'
        f'<p class="note">Every rule behind these numbers predates the data, written down '
        f'in <code>bci-dashboard-docs/hypothesis.md</code>. That is which frames, which '
        f'test, what counts as right, and when we were allowed to look. The plan allows one '
        f'look, so this page prints what the scorer wrote that once and never '
        f'recomputes it.</p>')
    return panel(
        'Two warnings that must travel with the top number, and what it does not measure',
        "<b>Quoted, not summarised.</b> The grey blocks are the plan&rsquo;s own words, "
        "copied rather than reworded.", body,
        anchor="two-warnings")
