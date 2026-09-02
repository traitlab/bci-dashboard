"""The panels only the queue page carries. ``panels.PANELS`` still names every
panel on either page, so a builder asks by id as before.
"""

from __future__ import annotations

import core as hc
from assets import cap, esc, panel, pctf, svg_hbar, table
from explain import BAND_SHORT, CONF_BAND_WORDS
from figures import RARE_MAX_SUPPORT, RECOMMENDED_CONF, WAIT_SUPPORT_MIN
from status_words import STATUS, SKIP_STATUSES, uncap

# Enough to answer "what do I send next" without a CSV reader. A batch is 100
# frames, so 25 is one morning\'s work and still short enough to read.
SEND_PREVIEW = 25

# Queue name -> (what it is, why it is worth sending). Shown in the order
# hc.QUEUE_ORDER gives, which is the order the CSV is sorted in.
QL = {"long_tail": ("Species we barely have, or barely get right",
                    f"The guess points at a species with fewer than "
                    f"{hc.WELL_SAMPLED_MIN_N} labelled frames, or one the model gets "
                    f"wrong even with more. These frames fill the long tail the "
                    f"labelling programme exists for"),
      "low_conf_known": ("A usually-right species, guessed weakly",
                         "The species is normally identified well but the model is "
                         "unsure here, so the photo is either an odd one worth having "
                         "or a quiet miss"),
      # Not "Everything else": the row below it is a further category, so a row
      # named for the leftovers sitting third contradicts "work top to bottom".
      "normal": ("The ordinary queue",
                 "Neither a cheap confirmation nor safe to leave, so these follow "
                 "the first two"),
      "can_wait": ("Confident on a well-covered species",
                   "The two-part rule below says these can wait; look at them last")}


# Above the 25 filenames, not below them: a reader who meets the list first has
# already accepted it as instructions by the time the caveat arrives.
UNGRADED_NOTE = (
    '<p class="note"><b>This order has not been graded.</b> The wait rule further down '
    'is measured on held-out frames and prints how often it is wrong. Nothing measures '
    'whether sending these photos first fills gaps faster than sending photos at random. '
    'Treat the order as a reasonable guess about where our labels are thin.</p>')


def p_todo(c):
    # The page-level orientation moved down here off the head: this is the open panel,
    # so it is the first thing a reader lands in either way.
    body = ['<p class="note">Every unlabelled photo already has a Pl@ntNet guess, and every '
            'species already has a measured record. Together those two put the pool in an '
            'order: the frames that buy the most per label first.</p>',
            '<ul class="todo">']
    body += [f'<li><span class="n">{c.counts[k]}</span> species '
             f'<span class="tag {k}">{esc(lab)}</span> {esc(act)}</li>'
             for k, (lab, act) in STATUS.items()]
    body.append(f'</ul><p class="note">Each of the {c.n_sp} species sits in exactly one row. '
                # There is no species table on this page. The sortable one is on the
                # model-health page, and "below" sent the reader looking for it here.
                f'The frame counts and accuracy behind each status are in the species '
                f'table on the model-health page, '
                f'<code>model_health_dashboard.html</code>.</p>'
                f'<p class="note"><strong>Cheaper still, and in no row above: {c.gen_one:,} '
                f'frames whose botanist label stops at the genus.</strong> Their five '
                f'candidates hold exactly one species from that genus, so the question is '
                f'yes or no, not which of {c.n_sp}. They never named a species, so they sit '
                f'outside the {c.n_sp} scored here. The model-health page says more.</p>')
    return panel(f"Where to spend botanist time next: {c.counts['ranking']} cheap "
                 f"confirmations, {c.counts['unreachable']} not worth time yet",
                 "<b>Work top to bottom.</b> Rows are ordered cheapest useful work "
                 "first, and three of them are work you can skip: "
                 + ", ".join(f"&ldquo;{uncap(STATUS[k][0])}&rdquo;" for k in SKIP_STATUSES)
                 + ". They are not all at the bottom.",
                 "\n".join(body), open_=True)


def p_send(c):
    # What "the pool" is, above the table whose third column is a share of it.
    body = (f'<p class="note">The pool is {c.n_unlab:,} of {len(c.h.split_rows):,} photos: '
            f'the ones with a cached Pl@ntNet answer and no botanist label. Every share '
            f'below is out of that {c.n_unlab:,}.</p>')
    body += table([("queue", False), ("unlabelled frames", True),
                  ("share of the pool", True)],
                 [[f'<strong>{esc(QL[q][0])}</strong>' if q in ("long_tail", "low_conf_known")
                   else esc(QL[q][0]),
                   f'{c.queue_counts.get(q, 0):,}',
                   pctf(c.queue_counts.get(q, 0) / c.n_unlab if c.n_unlab else None)]
                  for q in hc.QUEUE_ORDER])
    # The list itself, not a pointer to it: the counts above say how much work
    # there is, and the CSV in the snapshot folder said which photo.
    head = c.queue_rows[:SEND_PREVIEW]
    # Both notes sit above the table, not below it. The queue is ordered weakest
    # first, so the first screen is full of 0.001s, and a reader who meets those
    # before the gloss sees expert time being spent on coin flips.
    body += ('<h3 class="sub">The next ' + f'{len(head)}' + ' photos, in order</h3>'
             + UNGRADED_NOTE
             + '<p class="note"><b>Read the confidence column as how little the model '
               'knows, not as how likely the named species is.</b> A frame lands in a '
               'queue on which species was guessed, whatever the confidence, and inside a '
               'queue the weakest guesses come first. A number near the bottom of the '
               'scale means Pl@ntNet recognised almost nothing, which is the reason to '
               'look.</p>'
             + table([("#", True), ("photo", False), ("Pl@ntNet's guess", False),
                      ("confidence", True), ("frames that species has", True)],
                     [[f"{i}", f'<code class="key">{esc(stem)}</code>',
                       f'<span class="sp">{esc(cap(pred))}</span>', f"{cf:.3f}",
                       f"{c.support.get(pred, 0):,}"]
                      for i, (_, stem, pred, cf) in enumerate(head, 1)]))
    top_lt = sorted(c.lt_species.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    body += ('<p class="note"><b>Most-named species in the first queue.</b> '
             + ", ".join(f'<span class="sp">{esc(cap(s))}</span> ({k:,})' for s, k in top_lt)
             + '. '
             # Several of these have well over ten labels, and a reader who checks
             # them against the species table finds the queue name contradicted.
             f'Some of these already have more than {WAIT_SUPPORT_MIN} labelled frames. '
             f'They are here on the other half of the rule: the model still gets them '
             f'right less than {pctf(hc.HARD_MAX_TOP1)} of the time.</p>'
             # Two CSVs sit in the snapshot folder and the page named both as the
             # thing to work, 200 lines apart. This says which is which.
             f'<p class="note">The snapshot folder holds this same order as '
             f'<code>send_first_queue.csv</code>, one row per frame, and '
             f'<code>send_batches.csv</code>, that list cut into batches of at most 100. '
             f'<b>Work the batches file.</b></p>'
             f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Those are the likeliest to '
             f'be junk or to show no plant (leaves in the water, bare trunks). No automatic '
             f'rule for junk is reliable, so check that handful by eye.</p>'
             f'<p class="note"><b>The drone carries two cameras.</b> Every frame scored on '
             f'this page came from the wide-angle one, called <i>zoom</i> in the file '
             f'names: all {c.scored_cams["zoom"]:,} of them. The long-lens camera '
             f'(<i>tele</i>) has no botanist label yet, so how well the model reads it is '
             f'not known from here. Tele is {c.queue_cams["tele"]:,} of the '
             f'{sum(c.queue_cams.values()):,} photos in this queue '
             f'({pctf(c.queue_cams["tele"] / sum(c.queue_cams.values()))}), and sending '
             f'them is how it becomes known.</p>'
             # The pool is now defined above the share table. What is left here is
             # the accounting for the rest of the corpus and the model-change note.
             f'<p class="note">The other {len(c.h.split_rows) - c.n_unlab:,} of the '
             f'{len(c.h.split_rows):,} photos are already labelled, or have no cached answer '
             f'to rank. A model update re-sorts this queue exactly as it re-sorts the '
             f'can-wait one.</p>')
    # The same two queues the hero counts, added the same way. When the heading
    # named only the first queue, the hero's larger number and this smaller one
    # looked like two answers to the same question.
    send_now = (c.queue_counts.get("long_tail", 0)
                + c.queue_counts.get("low_conf_known", 0))
    return panel(f"What to send to the botanist first: {send_now:,} "
                 f"of {c.n_unlab:,} unlabelled photos",
                 f"<b>Work the queues top to bottom.</b> "
                 f"{c.queue_counts.get('long_tail', 0):,} photos point at a species we "
                 f"barely have, or barely get right; "
                 f"{c.queue_counts.get('low_conf_known', 0):,} show a usually-right species "
                 f"the model is unsure of here. Both buy more per label than anything "
                 f"below.",
                 # Open with the overview above it. This page is opened to answer
                 # "what do I label next", and the answer is the queue table, not
                 # a summary of the queue table. A reader who has to click to
                 # reach the deliverable has been asked to guess where it is.
                 body, open_=True, anchor="what-to-send-first")


def p_wait(c):
    best = c.best
    body = (f'<div class="rec"><strong>Suggested rule: leave a frame for later when '
            f'Pl@ntNet is at least {RECOMMENDED_CONF} confident and its species already has '
            f'{WAIT_SUPPORT_MIN} or more labelled frames.</strong> On the '
            f'{len(c.test_recs):,} frames held back for grading, that rule reaches '
            f'{best["n"]:,} of them ({pctf(best["share"])}), and the first guess is wrong '
            f'on {pctf(best["err"])} of those.</div>'
            # What 479 is. Every count in the comparison table below is a share of
            # it, so a reader who cannot picture the set cannot audit the table.
            f'<p class="note"><strong>What those {len(c.test_recs):,} frames are.</strong> '
            f'The labelled frames marked <code>test</code> in <code>splits.csv</code>, an '
            f'input to this page rather than something it computes. The rule was chosen on '
            f'the other frames, so nothing here is graded on the frames that picked it. '
            f'Every count below is out of those {len(c.test_recs):,}.</p>'
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
            f'the rule. Counting every label gives a larger number, so this will not match '
            f'the rarely-labelled count elsewhere on this page.'
            # Two unrelated counts on this page are 41 today, and a reader who meets
            # the second one takes it for a back-reference to the heading.
            + (f' It is also a different set from the {c.counts["ranking"]} species in the '
               f'heading above, which happens to be the same size.'
               if c.counts["ranking"] == len(c.eligible) else '')
            + '</p>')
    # The "undone at the next model change" clause moved out of the title: the
    # ask below already says the ranking is recomputed whenever Pl@ntNet updates.
    return panel(f"Which frames can wait: {best['n']:,} of the {len(c.test_recs):,} frames "
                 f"held back for grading",
                 "<b>Use this to order the queue, not to close frames.</b> These are the "
                 "frames to look at last, and the ranking is recomputed from scratch "
                 "whenever Pl@ntNet updates.", body)


def p_rules(c):
    body = table([("how sure the model has to be", False), ("frames that can wait", True),
                  ("share of the queue", True), ("of those, first guess wrong", True),
                  ("rarely-labelled frames it pushed down", True),
                  ("of what is left at the top, share rarely labelled", True)],
                 [[f'<strong>{o["label"]}</strong>' if o is c.best else o["label"],
                   f'{o["n"]:,}', pctf(o["share"]), pctf(o["err"]), f'{o["rare"]}',
                   pctf(o["rare_rest"])] for o in c.ops])
    body += (f'<p class="note">A species with fewer than {RARE_MAX_SUPPORT} labelled frames '
             f'counts as rarely labelled: {len(c.rare)} of {c.n_sp} species, {c.n_rare_test} '
             f'of the {len(c.test_recs):,} held-out frames. The second half of the rule '
             f'leaves every one of them at the top of the queue.</p>')
    # Four of the five rows describe rules that are not in force, so the summary
    # carries the one that is and the other four open on request. The arithmetic
    # below is unchanged; this is page weight, not evidence.
    b = c.best
    return panel(f'The {len(c.ops)} rules I compared, and why {b["label"]} is the one '
                 f'in force',
                 "<b>Read this only if you want to move the confidence line.</b> Each row "
                 "trades how many frames it takes off the queue against how often a frame "
                 "it pushed down was named wrong after all.", body,
                 anchor="how-the-rules-compare")


def p_conf(c):
    # Same blue as the next panel's chart: same measure, so a colour change would
    # read as meaning something. Green is spoken for by the status tags.
    flat = c.flat
    body = (svg_hbar([(CONF_BAND_WORDS[band], k / nn if nn else 0.0,
                       f'{pctf(k / nn) if nn else "n/a"}  ·  {nn:,} frames', "#1565c0")
                      for band, nn, k in c.bins_all],
                     title="how often the first guess is right, by the model's own confidence")
            + '<p class="note">Over all frames at once the score is trustworthy: when the '
              'model is sure it is almost always right. That is what makes ordering the '
              'queue possible at all. <strong>On rarely-labelled species it is not</strong>, '
              'so ordering on confidence alone would push exactly the species you care '
              'about to the bottom:</p>'
            + table([("labelled frames for that species", False),
                     ("frames the model was 0.7 or more sure about", True),
                     ("of those, first guess wrong", True)],
                    [[BAND_SHORT[lab], f"{flat[lab][0]:,}",
                      pctf(flat[lab][1] / flat[lab][0])]
                     for lab in hc.BUCKET_ORDER if lab in flat])
            + '<p class="note">Raising the confidence line does not repair this. '
              'Requiring the species to have been measured first does, which is why the '
              'suggested rule has two conditions.</p>')
    return panel("Can we trust the model's confidence? In bulk yes, on rare species no",
                 "<b>This is the evidence behind the two-part rule above.</b> Read it if "
                 "someone proposes ordering the queue on confidence alone.", body,
                 anchor="can-we-trust-the-confidence")
