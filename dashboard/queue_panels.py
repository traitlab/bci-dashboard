"""Panels used only by the queue page. ``panels.PANELS`` still names every
panel on both pages.
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
    '<p class="note"><b>This order has not been graded.</b> Nothing measures whether it '
    'fills gaps faster than sending photos at random. It is a reasonable guess about '
    'where our labels are thin. The wait rule further down <em>is</em> measured.</p>')


def p_todo(c):
    # The panel opened on a sentence about how the pool is ordered, which is not
    # what this list is: these are species statuses, and the pool is the next
    # panel's subject. The hero card already says the page puts the pool in an
    # order, and the summary above already says these rows are cheapest first.
    body = ['<ul class="todo">']
    body += [f'<li><span class="n">{c.counts[k]}</span> species '
             f'<span class="tag {k}">{esc(lab)}</span> {esc(act)}</li>'
             for k, (lab, act) in STATUS.items()]
    body.append(f'</ul><p class="note">Each of the {c.n_sp} species sits in exactly one row. '
                # There is no species table on this page: the sortable one is on the
                # model-health page, named explicitly rather than as "below".
                f'The frame counts and accuracy behind each status are in the species '
                f'table on the model-health page, '
                f'<code>model_health_dashboard.html</code>.</p>'
                f'<p class="note"><strong>Cheaper still, and in no row above: {c.gen_one:,} '
                f'frames whose botanist label stops at the genus.</strong> Their five '
                f'candidates hold exactly one species from that genus, so the question is yes '
                f'or no, not which of {c.n_sp}. No species was named on them, so they sit '
                f'outside the {c.n_sp} scored here.</p>')
    return panel(f"Where to spend botanist time next: {c.counts['ranking']} cheap "
                 f"confirmations, {c.counts['unreachable']} not worth time yet",
                 "<b>Work top to bottom.</b> Rows are ordered cheapest useful work "
                 "first. Three of them you can skip: "
                 + ", ".join(f"&ldquo;{uncap(STATUS[k][0])}&rdquo;" for k in SKIP_STATUSES)
                 + ". They are not all at the bottom.",
                 "\n".join(body), open_=True)


def p_send(c):
    # What "the pool" is, above the table whose third column is a share of it.
    body = (f'<p class="note">The pool is {c.n_unlab:,} of {len(c.h.split_rows):,} photos: '
            f'the ones with a cached Pl@ntNet answer and no botanist label. The other '
            f'{len(c.h.split_rows) - c.n_unlab:,} are already labelled or have no answer to '
            f'rank. Every share below is out of that {c.n_unlab:,}.</p>')
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
               'knows.</b> Inside a queue the weakest guesses come first, so a number near '
               'the bottom of the scale means Pl@ntNet recognised almost nothing. That is '
               'the reason to look, not a reason to doubt the name.</p>'
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
             f'Some already have more than {WAIT_SUPPORT_MIN} labelled frames; they are here '
             f'on the other half of the rule, right less than {pctf(hc.HARD_MAX_TOP1)} of '
             f'the time.</p>'
             # Two CSVs sit in the snapshot folder and the page named both as the
             # thing to work, 200 lines apart. This says which is which.
             f'<p class="note"><code>send_first_queue.csv</code> in the snapshot folder '
             f'holds this same order, one row per frame.</p>'
             f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Likeliest to be junk or to '
             f'show no plant, and no automatic rule for junk is reliable, so check that '
             f'handful by eye.</p>'
             # Kept because it names an unscored population, not because it is a fact
             # about the drone: nothing on this page grades that camera. "Camera",
             # not "lens", is the word CONTEXT.md settles on for the pair.
             f'<p class="note"><b>The long-lens camera is ungraded.</b> Every frame scored here came '
             f'from the wide-angle camera (<i>zoom</i>), all {c.scored_cams["zoom"]:,}. No '
             f'botanist has labelled a <i>tele</i> frame, so this page says nothing about '
             f'them. Tele is {c.queue_cams["tele"]:,} of the queue '
             f'({pctf(c.queue_cams["tele"] / sum(c.queue_cams.values()))}); sending them is '
             f'how it becomes known.</p>')
    # The same two queues the hero counts, added the same way, so this number and
    # the hero's agree.
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
            # What this count is: every share in the comparison table below is out
            # of it, so a reader who cannot picture the set cannot audit the table.
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
    # No "undone at the next model change" clause in this title: the ask below
    # already says the ranking is recomputed whenever Pl@ntNet updates.
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
    return panel(f'The {len(c.ops)} rules we compared, and why the one in force won',
                 f'<b>Read this only if you want to move the confidence line.</b> The rule '
                 f'in force is <em>{b["label"]}</em>. Each row trades how many frames it '
                 f'takes off the queue against how often a frame it pushed down was named '
                 f'wrong after all.', body,
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
                     (f"frames the model was {c.flat_thr} or more sure about", True),
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
