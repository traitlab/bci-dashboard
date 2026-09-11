"""The frozen sample, reduced to what it corrects on this page.

The set-aside 300 answered one question once: how much the centre crop's
region defect costs. That answer is a correction on the corpus rates above it,
so the page carries the gap and its population, and nothing else. The level it
was derived from, both intervals, the two amendments the design requires
verbatim, and the p-values live in ``bci-dashboard-docs/metrics.md``, which is
the writeup ``hypothesis.md`` A2 and A4 name.

The gap is published rather than the level on purpose. A2 attaches the
already-seen caveat to the crown arm's own accuracy and says in terms that the
paired comparison does not carry it, so the gap travels without a warning the
level cannot travel without.

The 300 frames were fixed on 2026-08-26, before any of these numbers existed.
"""

from __future__ import annotations

from assets import esc, panel, pctf
from figures import CONFIRMATORY_CSV
from panels import CENTRE_CROP_IS, NAMING_IS

def cam_phrase(cameras):
    """Name the file naming in the queue page's words.

    Read from the frame keys rather than assumed, so a future sample carrying
    both namings does not render as one naming with two names.
    """
    return NAMING_IS.get(cameras) or f"these file namings: {esc(cameras)}"


def require(cf):
    """The frozen read, or a refusal to build.

    The gap is the only thing correcting the rates above it, so a page that
    quietly drops it publishes a known-low number as if it were clean. The
    stamp is checked for the same reason it always was: the design allows one
    look, and an exploratory number must not reach a collaborator.
    """
    if cf is None:
        raise SystemExit(
            f"{CONFIRMATORY_CSV} is missing, so the correction the headline rates "
            f"are read against cannot be published. Run: python3 "
            f"dashboard/score_confirmatory.py --out {CONFIRMATORY_CSV}")
    if cf.get("stamp") != "CONFIRMATORY":
        raise SystemExit(
            f"the frozen result is stamped {cf.get('stamp')!r}, not 'CONFIRMATORY'. "
            f"The stopping rule says the read happens once on the complete set, so "
            f"an exploratory number must not be published here.")
    return cf


def floor_note(cf):
    """The one line that travels with the cards on the first screen.

    Cause before number: a reader who stops after one sentence should know why
    the rates above are a floor. The last sentence is load-bearing -- the gap
    was measured with the botanist's outlines in hand, and without it a reader
    reasonably reads a correction as a pending gain.
    """
    gap = 100 * cf["crown_minus_photo"]
    return (
        f'<p class="note"><strong>Read these rates as a floor.</strong> They score the '
        f'centre crop, {CENTRE_CROP_IS.split(", ")[-1]}, against a label for the whole '
        f'frame. On {int(cf["n_frames"])} frames set aside in advance, asking about the '
        f'outlined crowns instead moved the rate by {gap:+.1f} points. That needs a botanist&rsquo;s outlines, so it is a '
        f'<a href="#where-the-headline-comes-from">correction</a>, not a gain waiting to '
        f'be collected.</p>')


def p_floor(c):
    """Which frames the correction was measured on, and what limits it.

    Kept on the page because the house rule is that a published number carries
    its population, and the gap in the note above is the one number that would
    otherwise not. Everything a reader might want beyond that -- the level, the
    intervals either way, the two required amendments, the tests -- is in the
    writeup, cited rather than reproduced.
    """
    cf = require(c.cf)
    lo, hi = cf["crown_minus_photo_site_lo"], cf["crown_minus_photo_site_hi"]
    body = (
        f'<p class="note"><strong>Which frames.</strong> {int(cf["n_frames"])} frames from '
        f'{int(cf["n_sites"])} sites and {int(cf["n_days"])} flight days, fixed before any '
        f'of these numbers existed. Both ways of asking ran on every one.</p>'
        f'<p class="note"><strong>What was compared.</strong> One Pl@ntNet call per '
        f'outlined crown, pooled into one name for the frame by crown area. Against '
        f'{CENTRE_CROP_IS}, which every other rate on this page uses.</p>'
        f'<p class="note"><strong>How sure.</strong> We are 95% sure the true gap is '
        f'between {100 * lo:+.1f} and {100 * hi:+.1f} points. Frames from one site look '
        f'alike, so the range comes from redrawing the {int(cf["n_sites"])} sites with '
        f'replacement {int(cf["bootstrap_draws"]):,} times.</p>'
        f'<p class="note">On {int(cf["crown_only_hits"])} frames the outlines got the name '
        f'right and the centre crop did not. On {int(cf["photo_only_hits"])} it went the '
        f'other way.</p>'
        f'<div class="warn"><p><strong>How far the gap reaches.</strong></p><ul>'
        f'<li><strong>One export batch.</strong> Every frame here carries '
        f'{cam_phrase(cf["cameras"])}. Later flights were exported under the other '
        f'naming.</li>'
        f'<li><strong>{int(cf["n_sites"])} of the 17 field sites.</strong> '
        f'The other five are unknowns.</li>'
        f'<li><strong>Per frame, not per species.</strong> The two commonest of its '
        f'{int(cf["n_species"])} species are {pctf(cf["top2_species_share"])} of the '
        f'{int(cf["n_frames"])} frames, so the gap leans towards what the model knows '
        f'best.</li></ul></div>'
        f'<p class="note">Which frames, what counts as right and when we could look were '
        f'all fixed before the data. The full read and the warnings the design requires '
        f'are in its writeup, sent on request.</p>')
    return panel(
        'What the centre crop costs, and how far that number reaches',
        f"<b>Scoring the centre crop instead of a botanist&rsquo;s outlines costs "
        f"{100 * cf['crown_minus_photo']:.1f} points.</b> Measured once, on "
        f"{int(cf['n_frames'])} frames fixed in advance.", body,
        # The id predates this panel. A saved link should still land on the
        # question it was saved for, which is the one narrowed here.
        anchor="where-the-headline-comes-from")
