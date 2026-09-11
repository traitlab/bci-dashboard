"""Panels used only by the queue page. ``page.PANELS`` still names every
panel on both pages.
"""

from __future__ import annotations

import core as hc
import queues
from assets import (cap, esc, more, panel, pctf, svg_curve, svg_hbar,
                    table)
from explain import BAND_SHORT, CONF_BAND_WORDS
from figures import RARE_MAX_SUPPORT, RECOMMENDED_CONF, WAIT_SUPPORT_MIN
from panels import NAMING_IS, NAMING_NOTE
from selection_panels import audit_note, confound_note
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
      # Not "Everything else": a further category follows it. The name says why
      # a botanist should open the queue rather than what is in it, because the
      # rule beside it already draws the line against the queue above.
      #
      # It used to read "Not sure enough to leave alone" / "Neither of the two
      # above, and not confident enough to wait", two negations in the label and
      # one in the rule. A reader stopped at it on 2026-09-03 and could not say
      # what it meant. The number was there all along, in `can_wait` below: this
      # queue is everything the wait rule does not catch, so it is the same
      # WAIT_CONF read from the other side. Naming the threshold says in one
      # clause what the negations took two to not say.
      "normal": (f"Worth a look, confidence under {hc.WAIT_CONF:.2f}",
                 "Not in the two queues above, and Pl@ntNet is under "
                 f"{hc.WAIT_CONF:.2f} confident here"),
      "can_wait": ("Confident on a well-covered species",
                   f"Confidence {hc.WAIT_CONF:.2f} or more, and {hc.WELL_SAMPLED_MIN_N} or "
                   f"more labelled frames already")}


# Above the 25 filenames, not below them: a reader who meets the list first has
# already accepted it as instructions by the time the caveat arrives.
UNGRADED_NOTE = (
    '<p class="note"><b>This order has not been measured yet.</b> Nothing here measures '
    'whether it fills gaps faster than sending photos at random. It is a reasonable '
    'guess about where our labels are thin. The wait rule further down <em>is</em> '
    'measured.</p>'
    f'<p class="note"><b>Batch 1 carries the comparison.</b> {queues.control_size()} of its '
    f'{queues.BATCH_SIZE} photos are drawn at random from the whole pool instead of '
    'from the head of this order. When they come back labelled, the two halves can be '
    'compared. This only works on the first batch: every later pool has already been '
    'reshaped by this order.</p>')


# The page's own hand-off: the queue is only worth building if a batch reaches
# Labelbox, and the command that does it is one line. Named here rather than in
# the README because this is where a reader stands when they need it.
#
# Team copy only. The command needs the repository checked out and a Labelbox
# key, so on the public page it is a path a reader cannot walk, and the public
# page links the team page in its place.
DISPATCH = (
    '<h3 class="sub">Sending a batch</h3>'
    f'<p class="note"><a href="send_batches.csv">send_batches.csv</a> is this same queue '
    f'packed into batches of {queues.BATCH_SIZE}, each species kept whole. Send batch 1 '
    f'of round 1 with:</p>'
    '<pre class="cmd">python3 labelling/dispatch_round.py --round 1 --csv build/tables/send_batches.csv --batch 1 --test</pre>'
    '<p class="note">Drop <code>--test</code> once the dry run looks right.</p>')


def dispatch(c) -> str:
    """The send command, on the team copy of the page and nowhere else."""
    return DISPATCH if getattr(c, "team", False) else ""


def links_note(c) -> str:
    """What the two link columns in the send file reach, and what they do not.

    The standing rule is that a link column is never shipped silently half
    empty. The file has nowhere to say so, so the page says it for both columns
    at once, next to the link to the file.

    The paragraph used to open "Every row carries two links" and then report
    both columns filled on no row at all, which is a panel arguing with itself
    in three sentences. A reader believes the first sentence, opens the file,
    finds two empty columns and stops believing the rest of the page. So the
    explanation is rendered only once there is a link to explain. With none
    filled there is one sentence, which is the whole truth and is not
    contradicted two lines later.
    """
    at = queues.SEND_FIRST_COLUMNS.index("global_key")
    keys = [r[at] for r in c.queue_rows]
    box = hc.labelbox_link_coverage(keys)
    images = hc.inventory_image_urls()
    n_img = sum(1 for k in keys if images.get(k))
    if not n_img and not box["n_linked"]:
        return ('<p class="note">No frame links to its photo or its Labelbox row '
                'yet.</p>')
    return (f'<p class="note"><strong>Two link columns, filled where we have one.</strong> '
            f'The first opens the whole frame in any browser, no Labelbox '
            f'seat and no login, and it is filled on {n_img:,} of {len(keys):,} rows. '
            f'The second opens the frame in the project it was labelled '
            f'in, which is the only view that draws the crown being asked about, and it '
            f'is filled on {box["n_linked"]:,}. The {box["n_unlinked"]:,} rows without one '
            f'are frames no Labelbox export names. Those cells are empty rather '
            f'than guessed: a guessed link is a 404 in front of a botanist.</p>')


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
                f'<a href="model_health_dashboard.html">model_health_dashboard.html</a>. '
                f'Which species sits in which row is a column of '
                f'<a href="per_species_health.csv">per_species_health.csv</a>.</p>'
                f'<p class="note"><strong>Cheaper still, and in no row above: '
                f'{c.gen_one:,} frames whose label stops at the genus and whose '
                f'{hc.in_words(c.n_cand)} candidates hold exactly one species from '
                f'it.</strong></p>')
    # The heading names only the cheapest work; the lede lists every skippable
    # row, so one fact does not arrive as two numbers. The count is counted, not
    # written out: a row that leaves SKIP_STATUSES must leave this sentence too.
    n_skip = {2: "Two", 3: "Three", 4: "Four"}.get(len(SKIP_STATUSES), str(len(SKIP_STATUSES)))
    # Whether every skip row also sits last on the page: true only while
    # SKIP_STATUSES is exactly the tail of STATUS, in the same order.
    tail = list(STATUS)[-len(SKIP_STATUSES):]
    position_note = (" They sit last on the page too, in this order." if tail == list(SKIP_STATUSES)
                     else " They are scattered through the list, not grouped at the bottom.")
    return panel(f"Cheapest confirmation work: {c.counts['ranking']} species "
                 f"need a yes or no",
                 "<b>Work top to bottom.</b> Rows are ordered cheapest useful work "
                 f"first. {n_skip} of them you can skip: "
                 + ", ".join(f"&ldquo;{uncap(STATUS[k][0])}&rdquo;" for k in SKIP_STATUSES)
                 + "." + position_note,
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
                   for q in queues.QUEUE_ORDER],
                  source="send_first_queue.csv")
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
                      for i, (_, stem, pred, cf, _rank) in enumerate(head, 1)],
                     source="send_first_queue.csv"))
    return body


def send_notes(c):
    """The four questions a reader of the table above asks, in order: which
    species fill the first queue, where the full list lives, what to do with the
    photos that got no answer, and which frames none of this covers."""
    body = ""
    # The five most-named species in the first queue used to open this note. It
    # was an orientation rather than an instruction, the table above it already
    # names species row by row, and the caveat under it (some of these carry
    # more than the support minimum) only existed to correct the list.
    body += (f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Likeliest to be junk or to '
             f'show no plant, and no automatic rule for junk is reliable, so check that '
             f'handful by eye.</p>'
             # Names an unscored population. It is an export batch, not a camera:
             # saying "the long-lens camera" here invented a lens difference that
             # the flight team confirmed does not exist.
             # One sentence, from the side that matters: that every scored frame
             # carries the earlier naming and that no graded frame carries the
             # later one are the same fact, and the queue share is what says how
             # much of the work the gap covers.
             f'<p class="note"><b>The later export batch is ungraded.</b> No botanist has '
             f'labelled a frame carrying {NAMING_IS["tele"]}, which is '
             f'{c.queue_cams["tele"]:,} of the queue frames '
             f'({pctf(hc.ratio(c.queue_cams["tele"], sum(c.queue_cams.values())))}).</p>'
             # The naming trips people up in one direction only, into inventing a
             # lens difference. The correction is worth keeping and is worth
             # reading once, so it sits behind its own line rather than above.
             + more("What the two namings are",
                    f'<p class="note">{NAMING_NOTE}</p>'))
    return body


def held_out_note(c) -> str:
    """The evaluation frames the queue refused, with the splits they came from.

    Stated, not silent. These frames have a prediction and no label yet, so
    every rule on this page would put them in a queue; what keeps them out is
    that they were drawn into a split, and a botanist's answer on one of them
    would land inside the set the per-species statuses are measured on. A
    reader who compares the pool here against the unlabelled count elsewhere
    has to be able to account for the difference without asking.
    """
    held = getattr(c, "queue_held_out", None) or {}
    n = sum(held.values())
    if not n:
        return ""
    by_split = ", ".join(f"{held[k]} {k}" for k in sorted(held))
    return (f'<p class="note"><strong>{n} frames are kept out of this queue.</strong> '
            f'They are held back for grading ({by_split}), so they are '
            f'part of how this page\'s own numbers are graded. Sending one back for '
            f'labelling would put a new answer into the set those numbers are measured '
            f'on. They are not lost: they are labelled work already accounted for '
            f'elsewhere.</p>')


def p_send(c):
    """The page's answer to "what do I label next": queue sizes, the head of
    the queue, then the caveats that qualify both."""
    body = (send_pool_table(c) + send_preview_table(c) + dispatch(c) + links_note(c)
            + held_out_note(c) + send_notes(c))
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
