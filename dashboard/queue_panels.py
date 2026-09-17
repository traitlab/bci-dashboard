"""Panels used only by the queue page, the open half a reader acts on. The
closed half that argues for the order is ``queue_why_panels.py``, and
``page.PANELS`` still names every panel on both pages.
"""

from __future__ import annotations

import core as hc
import queues
from assets import cap, esc, more, panel, pctf, table
from panels import NAMING_IS, NAMING_NOTE
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
# The command needs the repository checked out and a Labelbox key, so to any
# other reader it is a path they cannot walk. It sits closed, under a summary
# that says who it is for, directly under the photos it sends. There used to be
# a second copy of the whole page for the team, which differed from this one by
# these lines and nothing else. The id is what that page's old address now
# redirects to, so a saved link opens this block.
TEAM_BLOCK_ID = "sending-a-batch"
DISPATCH = more(
    "For the labelling team: send a batch",
    f'<p class="note"><a href="send_batches.csv">send_batches.csv</a> is this same queue '
    f'packed into batches of {queues.BATCH_SIZE}, each species kept whole. Send batch 1 '
    f'of round 1 with:</p>'
    '<pre class="cmd">python3 labelling/dispatch_round.py --round 1 --csv build/tables/send_batches.csv --batch 1 --test</pre>'
    '<p class="note">Drop <code>--test</code> once the dry run looks right.</p>'
    '<p class="note">One batch there is one Labelbox '
    'batch, and <code>global_key</code> is the column Labelbox is given.</p>',
    anchor=TEAM_BLOCK_ID)


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
             f'<p class="note">{NAMING_NOTE}</p>')
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
    return (f'<p class="note"><strong>{n} frames are kept out of this queue.</strong> '
            f'They are held back for grading, so they are '
            f'part of how this page\'s own numbers are graded. Sending one back for '
            f'labelling would put a new answer into the set those numbers are measured '
            f'on. They are not lost: they are labelled work already accounted for '
            f'elsewhere.</p>')


def p_send(c):
    """The page's answer to "what do I label next": queue sizes, the head of
    the queue, then the caveats that qualify both."""
    body = (send_pool_table(c) + send_preview_table(c) + DISPATCH + links_note(c)
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
