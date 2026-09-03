"""Panels used only by the queue page. ``page.PANELS`` still names every
panel on both pages.
"""

from __future__ import annotations

import core as hc
import queues
from assets import cap, esc, panel, pctf, svg_curve, svg_hbar, table
from explain import BAND_SHORT, CONF_BAND_WORDS
from figures import RARE_MAX_SUPPORT, RECOMMENDED_CONF, WAIT_SUPPORT_MIN
from panels import CAMERA_IS
from status_words import STATUS, SKIP_STATUSES, uncap

# Enough to answer "what do I send next" without a CSV reader. A batch is 100
# frames, so 25 is one morning\'s work and still short enough to read.
SEND_PREVIEW = 25

# Queue name -> (what it is, which frames land in it). The second half is the
# rule `queues.queue_of_prediction` applies, written from the same constants it
# reads, in the order it tries them: first match wins. Shown in the order
# queues.QUEUE_ORDER gives, which is the order the CSV is sorted in.
QL = {"long_tail": ("Species we barely have, or barely get right",
                    f"Fewer than {hc.WELL_SAMPLED_MIN_N} labelled frames, or right less "
                    f"than {pctf(hc.HARD_MAX_TOP1, 0)} of the time"),
      "low_conf_known": ("A usually-right species, guessed weakly",
                         f"Right at least {pctf(hc.RELIABLE_MIN_TOP1, 0)} of the time "
                         f"overall, but confidence under {hc.LOW_CONF:.2f} here"),
      # Not "Everything else": a further category follows it.
      "normal": ("The ordinary queue",
                 "Neither of the two above, and not confident enough to wait"),
      "can_wait": ("Confident on a well-covered species",
                   f"Confidence {hc.WAIT_CONF:.2f} or more, and {hc.WELL_SAMPLED_MIN_N} or "
                   f"more labelled frames already")}


# Above the 25 filenames, not below them: a reader who meets the list first has
# already accepted it as instructions by the time the caveat arrives.
UNGRADED_NOTE = (
    '<p class="note"><b>This order has not been graded.</b> Nothing measures whether it '
    'fills gaps faster than sending photos at random. It is a reasonable guess about '
    'where our labels are thin. The wait rule further down <em>is</em> measured.</p>')


# The page's own hand-off: the queue is only worth building if a batch reaches
# Labelbox, and the command that does it is one line. Named here rather than in
# the README because this is where a reader stands when they need it.
DISPATCH = (
    '<h3 class="sub">Sending a batch</h3>'
    f'<p class="note"><a href="send_batches.csv">send_batches.csv</a> is this same queue '
    f'packed into batches of {queues.BATCH_SIZE}, each species kept whole. Send batch 1 '
    f'of round 1 with:</p>'
    '<pre class="cmd">python3 labelling/dispatch_round.py --round 1 --csv build/tables/send_batches.csv --batch 1 --test</pre>'
    '<p class="note">Drop <code>--test</code> once the dry run looks right.</p>')


def p_todo(c):
    """The species statuses as a to-do list, cheapest useful work first."""
    # These rows are species statuses. How the pool is ordered is the next
    # panel's subject.
    body = ['<ul class="todo">']
    body += [f'<li><span class="n">{c.counts[k]}</span> species '
             f'<span class="tag {k}">{esc(lab)}</span> {esc(act)}</li>'
             for k, (lab, act) in STATUS.items()]
    body.append(f'</ul><p class="note">Each of the {c.n_sp} species sits in exactly one row. '
                # The sortable species table is on the model-health page.
                f'The frame counts and accuracy behind each status are in the species '
                f'table on the model-health page, '
                f'<code>model_health_dashboard.html</code>.</p>'
                f'<p class="note"><strong>Cheaper still, and in no row above: {c.gen_one:,} '
                f'frames whose botanist label stops at the genus.</strong> Their five '
                f'candidates hold exactly one species from that genus, so the question is yes '
                f'or no, not which of {c.n_sp}. No species was named on them, so they sit '
                f'outside the {c.n_sp} scored here.</p>')
    # The heading names only the cheapest work; the lede lists all three
    # skippable rows, so one fact does not arrive as two numbers.
    return panel(f"Where to spend botanist time next: {c.counts['ranking']} species "
                 f"are one confirmation away",
                 "<b>Work top to bottom.</b> Rows are ordered cheapest useful work "
                 "first. Three of them you can skip: "
                 + ", ".join(f"&ldquo;{uncap(STATUS[k][0])}&rdquo;" for k in SKIP_STATUSES)
                 + ". They are not all at the bottom.",
                 "\n".join(body), open_=True)


def send_pool_table(c):
    """Each queue and how big it is, out of the pool whose shares it splits."""
    # What "the pool" is, above the table whose third column is a share of it.
    body = (f'<p class="note">The pool is {c.n_unlab:,} of {len(c.h.split_rows):,} photos: '
            f'the ones with a cached Pl@ntNet answer and no botanist label. The other '
            f'{len(c.h.split_rows) - c.n_unlab:,} are already labelled or have no answer to '
            f'rank. Every share below is out of that {c.n_unlab:,}.</p>')
    body += table([("queue", False), ("which frames land here", False),
                   ("unlabelled frames", True), ("share of the pool", True)],
                  [[f'<strong>{esc(QL[q][0])}</strong>' if q in ("long_tail", "low_conf_known")
                    else esc(QL[q][0]),
                    esc(QL[q][1]),
                    f'{c.queue_counts.get(q, 0):,}',
                    pctf(c.queue_counts.get(q, 0) / c.n_unlab if c.n_unlab else None)]
                   for q in queues.QUEUE_ORDER])
    # The ladder is tried in this order and the first match wins, which is the
    # only way to read the table without contradiction: a weak guess on a rare
    # species is long tail, not "guessed weakly".
    body += ('<p class="note">Rows are tried top to bottom. The first one that fits '
             'wins, so a weak guess on a rare species stays in the first queue.</p>')
    return body


def send_preview_table(c):
    """The head of the queue itself, not a pointer to the CSV that holds it.

    The table above says how much work there is. This says which photo."""
    body = ""
    head = c.queue_rows[:SEND_PREVIEW]
    # Both notes sit above the table: the queue is ordered weakest first, so the
    # first screen is full of 0.001s and needs the gloss before it, not after.
    body += ('<h3 class="sub">The next ' + f'{len(head)}' + ' photos, in order</h3>'
             + UNGRADED_NOTE
             + '<p class="note"><b>Inside a queue the photo least like everything already '
               'labelled comes first.</b> Pl@ntNet turns each centre crop into a list of '
               'numbers, and two photos with close numbers look alike to it. A photo far '
               'from every labelled one is the photo we know least about.</p>'
             + '<p class="note"><b>Read the confidence column as how little the model '
               'knows.</b> It breaks the tie, so a number near the bottom of the scale '
               'means Pl@ntNet recognised almost nothing. That is the reason to look, not '
               'a reason to doubt the name.</p>'
             + table([("#", True), ("photo", False), ("Pl@ntNet's guess", False),
                      ("confidence", True), ("frames that species has", True)],
                     [[f"{i}", f'<code class="key">{esc(stem)}</code>',
                       f'<span class="sp">{esc(cap(pred))}</span>', f"{cf:.3f}",
                       f"{c.support.get(pred, 0):,}"]
                      for i, (_, stem, pred, cf, _rank) in enumerate(head, 1)]))
    return body


def send_notes(c):
    """The four questions a reader of the table above asks, in order: which
    species fill the first queue, where the full list lives, what to do with the
    photos that got no answer, and which camera none of this covers."""
    body = ""
    top_lt = sorted(c.lt_species.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    body += ('<p class="note"><b>Most-named species in the first queue.</b> '
             + ", ".join(f'<span class="sp">{esc(cap(s))}</span> ({k:,})' for s, k in top_lt)
             + '. '
             # Several of these have well over ten labels, and a reader who checks
             # them against the species table finds the queue name contradicted.
             f'Some already have more than {WAIT_SUPPORT_MIN} labelled frames; they are here '
             f'on the second half of the first row above, not the first.</p>'
             f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Likeliest to be junk or to '
             f'show no plant, and no automatic rule for junk is reliable, so check that '
             f'handful by eye.</p>'
             # Names an unscored population: nothing on this page grades that
             # camera. "Camera", not "lens", is CONTEXT.md's word for the pair.
             f'<p class="note"><b>The long-lens camera is ungraded.</b> Every frame scored '
             f'here came from {CAMERA_IS["zoom"]}: '
             f'all {c.scored_cams["zoom"]:,} of them. No botanist has labelled a frame from '
             f'{CAMERA_IS["tele"]}, so this page says nothing about those. They are '
             f'{c.queue_cams["tele"]:,} of the queue '
             f'({pctf(hc.ratio(c.queue_cams["tele"], sum(c.queue_cams.values())))}); '
             f'sending them is '
             f'how it becomes known.</p>')
    return body


def p_send(c):
    """The page's answer to "what do I label next": queue sizes, the head of
    the queue, then the caveats that qualify both."""
    body = send_pool_table(c) + send_preview_table(c) + DISPATCH + send_notes(c)
    # The same two queues the hero counts, added the same way, so both agree.
    send_now = (c.queue_counts.get("long_tail", 0)
                + c.queue_counts.get("low_conf_known", 0))
    return panel(f"What to send to the botanist first: {send_now:,} "
                 f"of {c.n_unlab:,} unlabelled photos",
                 f"<b>Work the queues top to bottom.</b> "
                 f"{c.queue_counts.get('long_tail', 0):,} photos point at a species we "
                 f"barely have, or barely get right; "
                 f"{c.queue_counts.get('low_conf_known', 0):,} show a usually-right species "
                 f"the model is unsure of here. Both buy more per label than anything "
                 f"below. Inside each queue the photo least like everything already "
                 f"labelled comes first, which reaches {c.n_ranked:,} of the "
                 f"{c.n_unlab:,}; the rest keep their place by confidence. "
                 f'<a href="send_first_queue.csv">send_first_queue.csv</a> holds this same '
                 f"order, one row per frame.",
                 # Open: the answer to "what do I label next" is the queue
                 # table itself, not a summary of it.
                 body, open_=True, anchor="what-to-send-first")


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
            f'<p class="note"><strong>What those {len(c.test_recs):,} frames are.</strong> '
            f'The labelled frames marked <code>test</code> in <code>splits.csv</code>, an '
            f'input to this page. The rule was chosen on the other frames, so nothing here is '
            f'graded on the frames that picked it. Every count below is out of those '
            f'{len(c.test_recs):,}.</p>'
            # Two hold-outs, described in almost the same words on two pages that
            # link to each other. A reader assumes one is a subset of the other.
            f'<p class="note">Not the set behind the model-health page\'s two headline '
            f'numbers. That is a separate draw of {int(c.cf["n_frames"])} frames from every '
            f'labelled frame, overlapping this one. Neither set contains the other.</p>'
            '<p class="note"><strong>Nothing here is a label.</strong> A frame that can wait '
            "keeps whatever label it has, or none. The rule only pushes frames down the "
            "botanist's queue.</p>"
            f'<p class="note"><strong>The decision expires with the model.</strong> Pl@ntNet '
            f'ships a new model every few months, on its schedule not ours. A frame pushed '
            f'down under <code>{esc(c.tag)}</code> is not pushed down under the next one. '
            f'Re-run this page after a model change and any frame can come back to the '
            f'top.</p>'
            f'<p class="note">{len(c.eligible)} species reach {WAIT_SUPPORT_MIN} labelled '
            f'frames inside the frames a rule may learn from, which is the second half of '
            f'the rule. Counting every label instead, not just those, gives a larger '
            f'number. So this count will not match the &ldquo;too few labels to judge&rdquo; '
            f'count in the list above.'
            # Two unrelated counts on this page are 41 today, and a reader who meets
            # the second one takes it for a back-reference to the heading.
            + (f' It is also a different set from the {c.counts["ranking"]} species in the '
               f'heading above, which happens to be the same size.'
               if c.counts["ranking"] == len(c.eligible) else '')
            + '</p>')


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
                         f'{pctf(k / nn) if nn else "n/a"}  &middot;  {nn:,} frames', "#1565c0")
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
    return panel(f"Which frames can wait, and why the line sits where it does: "
                 f"{c.best['n']:,} of {len(c.test_recs):,} frames held back for grading",
                 "<b>Read this to move the confidence line, or to check the wait rule.</b> "
                 f"The rule in force is <em>{c.best['label']}</em>. It orders the queue, it "
                 "does not close frames, and it is recomputed whenever Pl@ntNet updates.",
                 _wait_rule(c) + _rules_compared(c) + _confidence_evidence(c),
                 anchor="which-frames-can-wait")


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
    """Where the ordering stops telling you anything.

    The line falls fast and then flattens. Past the flat part every photo is
    about as unlike the labelled set as the next, so the queue is back to
    confidence order underneath and there is nothing left to gain by working on.
    """
    if not c.novelty_curve:
        return ""
    return (svg_curve([("distance", c.novelty_curve, LOOK_AMBER)],
                      title="How unlike the named photos each one looks, by its place",
                      x_title="place in the queue", y_title="distance")
            + '<p class="note"><b>Where this flattens, the order stops helping.</b> Each '
              'point averages a slice of the queue. Once the line is level the photos are '
              'all about equally unlike what we have, and the order under them is the old '
              'confidence order.</p>')


def camera_note(c) -> str:
    """The cost of this ordering, in the summary rather than a chart.

    The `tele` in a file name is a naming change, not a second camera: the
    flights that carry it also produced `zoom` names, and the two namings differ
    by the month the frames were exported. So the risk this note carries is that
    a photo reads as new for the batch it came from. Two numbers, so a sentence
    carries it and a chart would only decorate it.
    """
    if not c.head_n:
        return ""
    return (f'<p class="note"><b>What this ordering costs.</b> Of the {c.head_n:,} photos '
            f'it puts first, {pctf(c.head_tele_share)} carry the newer file naming, '
            f'against {pctf(c.queue_tele_share)} across the whole queue. That naming '
            f'marks a later batch of flights, not a different camera. A gap here can be '
            f'the flights and not the species.</p>')


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
    body = (charts or NO_CURVES) + camera_note(c) + contact_sheet(c)
    return panel("Why the queue is in this order",
                 SCORED if c.discovery else UNSCORED,
                 body, open_=False, anchor="why-this-order")
