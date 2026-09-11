"""The queue page's second part: why this order, and how far to trust it.

Everything here is closed on the page. A reader working the queue needs the
open panels above it, in ``queue_panels.py``; a reader arguing with the order
opens these. Split out of that module when the page was rearranged to put the
work first and the reasoning after it.
"""

from __future__ import annotations

import core as hc
import queues
from assets import cap, esc, more, panel, pctf, svg_curve, svg_hbar, table
from explain import BAND_SHORT, CONF_BAND_WORDS
from figures import RARE_MAX_SUPPORT, RECOMMENDED_CONF, WAIT_SUPPORT_MIN
from panels import NAMING_NOTE
from queue_panels import QL
from selection_panels import audit_note, confound_note


def p_namings(c):
    """Where the two file namings come from.

    The note under the queue table names the later naming, and the naming
    trips people up in one direction only, into inventing a lens difference.
    The correction is worth reading once, so it sits here rather than there.
    """
    return panel("What the two namings are", NAMING_NOTE, "")


# Okabe-Ito, the palette the labelfirst reports use, so a reader who has seen
# one recognises the other. Blue is the order this page ships; grey is the
# order it replaced, and grey never competes for attention with a result.
LOOK_BLUE, LOOK_GREY, LOOK_AMBER = "#0072B2", "#9e9e9e", "#b5670a"

NO_CURVES = (
    '<p class="note"><b>The ordering has not been scored on this checkout.</b> '
    'The two files behind these charts are written by hand, by '
    '<code>labelling/rank_queue.py</code>, and are not in the repository. Run it '
    'to draw them.</p>')


def discovery_chart(c) -> str:
    """Does ordering by look find species faster than picking at random.

    Drawn from ``discovery_curve.csv``. The population is on the chart, because
    it is not the queue: this is measured on photos a botanist has already named,
    which is the only place the answer is known.
    """
    if not c.discovery:
        return ""
    marks = [(x, f"{int(x):,}") for x in (c.discovery_half_directed,
                                          c.discovery_half_random) if x]
    return (svg_curve([("ordered by look", c.discovery, LOOK_BLUE),
                       ("random order", c.discovery_random, LOOK_GREY)],
                      title="Species found, over photos that already carry a name",
                      x_title="photos named", y_title="distinct species",
                      rules=[(c.discovery_half, "half the species")],
                      marks=marks)
            + f'<p class="note"><b>What this is measured on.</b> The '
              f'{int(c.discovery_photos):,} photos a botanist has already named, carrying '
              f'{int(c.discovery_species):,} species between them. Not the queue. It shows '
              f'the method works where the answer is known.</p>'
            + f'<p class="note">Half those species take '
              f'{int(c.discovery_half_directed or 0):,} photos in this order and '
              f'{int(c.discovery_half_random or 0):,} in a random one. Read it as evidence '
              f'for the ordering, not as a promise about the queue: this run starts from '
              f'nothing, and the queue starts from every photo already named.</p>')


def novelty_chart(c) -> str:
    """How far down the queue the ordering keeps separating photos.

    Written to describe whatever shape the data has, not the shape expected of
    it: on the pool measured so far the line falls steeply and then keeps
    falling, with no flat part at all, so a note promising one would be telling
    a reader to look for something that is not there.
    """
    if not c.novelty_curve:
        return ""
    return (svg_curve([("distance", c.novelty_curve, LOOK_AMBER)],
                      title="How unlike the named photos each one looks, by its place",
                      x_title="place in the queue", y_title="distance")
            + '<p class="note"><b>How to read this:</b> each point averages a slice of '
              'the queue. The line falls, so photos near the top really are less like the '
              'named ones than photos near the bottom. Most of that fall is in the first '
              'quarter of the queue, and past it the line keeps dropping, but slowly. The '
              'photos it separates there differ from each other far less than the ones '
              'at the head do.</p>')


def contact_sheet(c) -> str:
    """The head of each queue, as pictures.

    Every other figure on this page is about frames the reader has never seen.
    The picture is the centre crop, the same region the model scored, so what is
    on screen is what the order was decided on.
    """
    if not c.thumbs:
        return ""
    out = []
    for q in queues.QUEUE_ORDER:
        shots = c.thumbs.get(q)
        if not shots:
            continue
        cells = "".join(
            f'<img src="{uri}" width="{hc.THUMB_PX}" height="{hc.THUMB_PX}" '
            f'alt="{esc(stem)}, guessed {esc(pred) or "nothing"}" '
            f'title="{esc(stem)} &#10; {esc(pred)}"/>'
            for stem, pred, uri in shots)
        out.append(f'<h3 class="sub">{esc(cap(QL[q][0]))}</h3>'
                   f'<p class="qrule">{esc(QL[q][1])}</p>'
                   f'<div class="sheet">{cells}</div>')
    return ("".join(out)
            + f'<p class="note"><b>What you are looking at.</b> The first '
              f'{hc.THUMBS_PER_QUEUE} photos of each queue, in the order above, cut down '
              f'to the middle of the frame. That is the region Pl@ntNet scored, so this is '
              f'what the order was decided on.</p>')


SCORED = ("<b>Ordering by look finds species faster than working down a random "
          "list.</b> The charts below score that on photos already named, show where "
          "the ordering stops separating photos, and put the head of every queue on "
          "screen.")
UNSCORED = ("<b>The queue is ordered by look: the photo least like everything already "
            "named comes first.</b> That ordering has not been scored on this checkout, "
            "so this panel makes no claim about what it buys.")


def p_look(c):
    """The evidence that ordering by look does anything, and what it costs.

    The summary changes with the evidence. A closed panel has to stand alone, so
    it must not assert the finding on a checkout where nothing has been scored.
    """
    charts = discovery_chart(c) + novelty_chart(c)
    # The discovery curve is one run from nothing. The audit under it is the
    # same question asked properly: several random starts, against a random
    # order, with a range and a p-value. The confound test is the cost side,
    # and replaces the two hand-counted shares that used to stand alone.
    body = ((charts or NO_CURVES) + audit_note(c) + confound_note(c)
            + contact_sheet(c))
    return panel("Why the queue is in this order",
                 SCORED if c.discovery else UNSCORED,
                 body, open_=False, anchor="why-this-order")


def _near_copy_note(c) -> str:
    """Whether the wrong-guess share leans on near-copies of the rule's frames.

    Once flights are held back whole, the rule is graded there too and the page
    prints that grade. Until then it says the share is a floor it cannot size.
    """
    held = c.held_wait
    if held["n"]:
        return ('<p class="note"><strong>The same rule on flights held back whole:'
                f'</strong> it reaches {held["n"]:,} of the {held["n_frames"]:,} frames '
                f'there, and the first guess is wrong on {pctf(held["err"])} of those. '
                'Those frames hold different species in different shares, so how many the '
                'rule reaches differs for that reason alone.</p>'
                + more("Why grade it on those flights too",
                       '<p class="note">The frames above were held back one by one, so each '
                       'shares a flight with a frame the rule was picked on. Frames from one '
                       'flight overlap, so one can be a near-copy of another. No frame above '
                       'shares a flight with the ones held back whole.</p>'))
    return ('<p class="note"><strong>Why the wrong-guess share is a floor, not an '
            'estimate:</strong> the split was drawn frame by frame, not site by site. '
            'Drone frames from one flight over one site overlap, so a held-out '
            "frame, one kept back from the rule's frames, can be a near-copy of "
            'one it learned from. So the share above is the least the rule gets '
            'wrong, and we have not measured how much more.</p>'
            + more("What would fix it",
                   '<p class="note">Every site with labelled frames has frames both held '
                   'back for grading and used to pick the rule. Grading the rule on '
                   'flights held back whole is what fixes it. Until then this caveat '
                   'stands.</p>'))


def _wait_rule(c) -> str:
    """The rule in force, what it reaches, and every caveat on it."""
    best = c.best
    return (f'<div class="rec"><strong>Suggested rule: leave a frame for later when '
            f'Pl@ntNet is at least {RECOMMENDED_CONF} confident and its species already has '
            f'{WAIT_SUPPORT_MIN} or more labelled frames.</strong> On the '
            f'{len(c.test_recs):,} frames held back for grading, that rule reaches '
            f'{best["n"]:,} of them ({pctf(best["share"])}), and the first guess is wrong '
            f'on {pctf(best["err"])} of those.</div>'
            # Every share in the comparison table below is out of this count.
            f'<p class="note"><strong>What those {len(c.test_recs):,} frames are:</strong> '
            f'the labelled frames held back for grading. The '
            f'rule was chosen on the other frames, so no frame here helped pick the rule, '
            f'and every count below is out of those {len(c.test_recs):,}. '
            # Two hold-outs, described in almost the same words on two pages that
            # link to each other. A reader assumes one is a subset of the other.
            f'They are not the model-health page\'s {int(c.cf["n_frames"])} frames fixed '
            f'in advance; the two overlap and neither contains the other.</p>'
            + _near_copy_note(c)
            # What a wait is not, and how long it lasts, is what a reader who
            # wants to act on the rule asks second. The rule itself, in the box
            # at the top of the panel, says it leaves a frame for later and
            # nothing more, so neither line is load-bearing where it stood.
            + more("What a wait does, and how long it lasts",
                   '<p class="note"><strong>Nothing here is a label.</strong> A frame that '
                   "can wait keeps whatever label it has, or none; the rule only pushes it "
                   "down the queue. The decision also expires with the model. Pl@ntNet "
                   "ships a new one every few months, and re-running this page after that "
                   "can bring any frame back to the top.</p>")
            + more("Where the species half of the rule is counted",
                   f'<p class="note">{len(c.eligible)} species reach {WAIT_SUPPORT_MIN} '
                   f'labelled frames inside the frames a rule may learn from, which is the '
                   f'second half of the rule. Counting every label gives a larger number, '
                   f'so this will not match the &ldquo;too few labels to judge&rdquo; '
                   f'count above.'
            # Two unrelated counts on this page are 41 today, and a reader who meets
            # the second one takes it for a back-reference to the heading.
            + (f' It is also a different set from the {c.counts["ranking"]} species in the '
               f'heading above, which happens to be the same size.'
               if c.counts["ranking"] == len(c.eligible) else '')
            + '</p>'))


def _rules_compared(c) -> str:
    """Every confidence threshold side by side, so the one in force is a choice
    a reader can check rather than a number to accept."""
    body = (f'<h3 class="sub">The {len(c.ops)} rules we compared</h3>'
            + table([("how sure the model has to be", False), ("frames that can wait", True),
                     ("share of the queue", True), ("of those, first guess wrong", True),
                     ("rarely-labelled frames it pushed down", True),
                     ("of what is left at the top, share rarely labelled", True)],
                    [[f'<strong>{o["label"]}</strong>' if o is c.best else o["label"],
                      f'{o["n"]:,}', pctf(o["share"]), pctf(o["err"]), f'{o["rare"]}',
                      pctf(o["rare_rest"])] for o in c.ops]))
    return body + (f'<p class="note">A species with fewer than {RARE_MAX_SUPPORT} labelled '
                   f'frames counts as rarely labelled: {len(c.rare)} of {c.n_sp} species, '
                   f'{c.n_rare_test} of the {len(c.test_recs):,} held-out frames. The second '
                   f'half of the rule leaves every one of them at the top of the queue.</p>')


def _confidence_evidence(c) -> str:
    """How often the first guess is right at each confidence band, over all frames
    at once. This is the evidence that ordering the queue by confidence works."""
    # Same blue as the chart on the model-health page: same measure, so a colour
    # change would read as meaning something. Green is spoken for by the tags.
    flat = c.flat
    return ('<h3 class="sub">Can we trust the confidence? In bulk yes, on rare species no</h3>'
            + svg_hbar([(CONF_BAND_WORDS[band], k / nn if nn else 0.0,
                         f'{pctf(k / nn) if nn else "n/a"} of {nn:,} frames', "#1565c0")
                        for band, nn, k in c.bins_all],
                       title="how often the first guess is right, "
                             "by the model's own confidence")
            + '<p class="note">Over all frames at once the score is trustworthy: when the '
              'model is sure it is almost always right. That is what makes ordering the '
              'queue possible at all. <strong>On rarely-labelled species it is not</strong>, '
              'so ordering on confidence alone would push exactly the species you care '
              'about to the bottom:</p>'
            + table([("labelled frames for that species", False),
                     (f"frames the model was {c.flat_thr} or more sure about", True),
                     ("of those, first guess wrong", True)],
                    [[BAND_SHORT[lab], f"{flat[lab][0]:,}",
                      pctf(flat[lab][1] / flat[lab][0])]
                     for lab in hc.BUCKET_ORDER if lab in flat])
            + '<p class="note">Raising the confidence line does not repair this. '
              'Requiring the species to have been measured first does, which is why the '
              'suggested rule has two conditions.</p>')


def p_evidence(c):
    """The wait rule, the thresholds it was chosen against, and the calibration
    behind ordering on confidence at all.

    One panel, closed, rather than three: a reader working the queue needs the
    two open panels above and nothing else, and a reader arguing with the rule
    wants all three pieces of evidence in one place. Splitting them made the
    page three screens long to say one thing.
    """
    # The counts were in the summary and have moved down here. "and why the line
    # sits where it does" already says what the panel is for, so the numbers were
    # scope rather than the finding, and they made a stable header move on every
    # snapshot. Every other summary on this page keeps its number, because there
    # the number is the reason to open the panel.
    return panel("Which frames can wait, and why the line sits where it does",
                 # The rule and what it reaches are stated in full in the box at
                 # the head of the panel, in the same numbers, and a summary line
                 # is read to decide whether to open the panel rather than to
                 # carry the rule away. So the summary says what is inside.
                 "<b>Read this to move the confidence line, or to check the wait "
                 "rule.</b>",
                 _wait_rule(c) + _rules_compared(c) + _confidence_evidence(c),
                 anchor="which-frames-can-wait")
