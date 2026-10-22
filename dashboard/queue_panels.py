"""Panels used only by the queue page, the open half a reader acts on. The
closed half that argues for the order is ``queue_why_panels.py``, and
``page.PANELS`` still names every panel on both pages.
"""

from __future__ import annotations

from urllib.parse import quote

import core as hc
import queues
from assets import cap, esc, explorer_link, more, panel, pctf, table
from panels import NAMING_IS, NAMING_NOTE
from selection_panels import _pct as sel_pct
from status_words import STATUS

# Enough to answer "what do I send next" without a CSV reader. A batch is 100
# frames, so 25 is one morning\'s work and still short enough to read.
SEND_PREVIEW = 25

# Queue name -> (what it is, which frames land in it). The second half is the
# rule `queues.queue_of_prediction` applies, written from the same constants it
# reads, in the order it tries them: first match wins. Shown in the order
# queues.QUEUE_ORDER gives, which is the order the CSV is sorted in.
QL = {"long_tail": ("Species with few labelled frames, or often wrong",
                    f"Fewer than {hc.WELL_SAMPLED_MIN_N} labelled frames, or right less "
                    f"than {pctf(hc.HARD_MAX_TOP1, 0)} of the time"),
      "low_conf_known": ("A usually-right species, guessed weakly",
                         f"Right at least {pctf(hc.RELIABLE_MIN_TOP1, 0)} of the time "
                         f"overall, but confidence under {hc.LOW_CONF:.2f} here"),
      # Named by its WAIT_CONF threshold: this queue is everything the wait
      # rule (`can_wait` below) does not catch.
      "normal": (f"Worth a look, confidence under {hc.WAIT_CONF:.2f}",
                 "Not in the two queues above, and Pl@ntNet is under "
                 f"{hc.WAIT_CONF:.2f} confident here"),
      "can_wait": ("Confident on a well-covered species",
                   f"Confidence {hc.WAIT_CONF:.2f} or more, and {hc.WELL_SAMPLED_MIN_N} or "
                   f"more labelled frames already")}


# Below the un-measured claim either way: a reader who meets the batch-1
# control before the caveat above it would read the control as the whole
# answer, rather than as the one thing this checkout can still measure.
def _batch1_note(c) -> str:
    if not c.n_batch1:
        return ""
    n_control = min(queues.control_size(), len(c.queue_rows))
    return (
        f'<p class="note"><b>Batch 1 carries the comparison.</b> {n_control} of its '
        f'{c.n_batch1} photos are drawn at random from the whole pool instead of '
        'from the head of this order. When they come back labelled, the two groups can be '
        'compared. This only works on the first batch: every later pool has already been '
        'reshaped by this order.</p>')

# The fallback for a checkout with no audit file: labelfirst has measured
# nothing yet, so the note cannot say more than that.
_UNMEASURED_NOTE = (
    '<p class="note"><b>This order has not been measured yet.</b> Nothing here measures '
    'whether it fills gaps faster than sending photos at random. It is a reasonable '
    'guess about where our labels are thin. The wait rule further down <em>is</em> '
    'measured.</p>')


# Above the 25 filenames, not below them: a reader who meets the list first has
# already accepted it as instructions by the time the caveat arrives.
def ungraded_note(c) -> str:
    """What the order above is measured against, and what it is not.

    ``c.selection_audit`` is the same audit ``selection_panels.audit_note``
    reads: rare species found faster than a random order, on the labelled
    frames that already carry a name. That is what is measured. This pool,
    the unlabelled photos the table above orders, is not: it carries no label
    yet, so nothing here checks whether the order fills gaps faster than a
    random one on it. Absent the audit file, the note degrades to the plain
    claim that nothing has been measured.
    """
    a = getattr(c, "selection_audit", None)
    if not a:
        return _UNMEASURED_NOTE + _batch1_note(c)
    saved = ""
    if a["passed"] and a["labels_saved_pct"] is not None:
        saved = (f' It needs {sel_pct(a["labels_saved_pct"])} fewer labels for the same '
                 'rare species.')
    return (f'<p class="note"><b>What this order is measured against.</b> On the '
            f'{a["n_frames"] or 0:,} labelled frames that already carry a name, this '
            f'ordering finds rare species faster than a random order.{saved} This pool is '
            'not: it carries no label yet, so nothing here checks whether this order '
            'fills gaps faster than a random one on it.</p>'
            + _batch1_note(c))


# The page's own hand-off: the queue is only worth building if a batch reaches
# Labelbox, and the command that does it is one line. Named here rather than in
# the README because this is where a reader stands when they need it.
#
# The command needs the repository checked out and a Labelbox key, so it sits
# closed, under a summary that says who it is for, directly under the photos it
# sends. Redirect target for label_queue_team.html; keep the id stable.
TEAM_BLOCK_ID = "sending-a-batch"
DISPATCH = more(
    "For the labelling team: send a batch",
    f'<p class="note"><a href="send_batches.csv">send_batches.csv</a> is this same queue '
    f'packed into batches of {queues.BATCH_SIZE}, each species kept whole. To send a '
    'batch, after checking its status in Labelbox, use this command with the chosen '
    'round and batch numbers. This example selects batch 1 of round 1:</p>'
    '<pre class="cmd">python3 labelling/dispatch_round.py --round 1 --csv build/tables/send_batches.csv --batch 1 --test</pre>'
    '<p class="note"><strong>This creates a live five-photo batch and updates metadata '
    'in Labelbox.</strong> <code>--test</code> limits the send to five photos; it is not '
    'an offline preview. Omit it to send the full selected batch.</p>'
    '<p class="note">One batch there is one Labelbox '
    'batch, and <code>global_key</code> is the column Labelbox is given.</p>',
    anchor=TEAM_BLOCK_ID)


def links_note(c) -> str:
    """What the two link columns in the send file reach, and what they do not.

    The standing rule is that a link column is never shipped silently half
    empty. The file has nowhere to say so, so the page says it for both columns
    at once, next to the link to the file.

    The explanation renders only when at least one column is filled; with
    none filled there is a single sentence saying so.
    """
    # Renderer rows carry prediction stems, not the CSV's prefixed global keys.
    keys = [hc.GT_KEY_PREFIX + r[1] for r in c.queue_rows]
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
    """Species-level evidence for reviewing guesses, separate from photo priority."""
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
                f'<p class="note"><strong>Additional candidate checks: '
                f'{c.gen_one:,} frames whose label stops at the genus and whose '
                f'{hc.in_words(c.n_cand)} candidates hold exactly one species from '
                f'it.</strong> The candidate still needs expert confirmation; '
                f'alternatives outside the returned list remain possible.</p>')
    return panel("How to review model guesses",
                 "<b>These statuses describe model performance, not biodiversity value.</b> "
                 "Use the photo queue to choose work; use these species-level results "
                 "to decide how closely to check a guess.",
                 "\n".join(body), open_=False, anchor="cheapest-confirmation-work")


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
    urls = hc.labelbox_urls()
    explorer_available = "explorer.html" in getattr(c, "available_pages", ())
    images = {} if explorer_available else hc.inventory_image_urls()

    def photo_links(stem):
        key = hc.GT_KEY_PREFIX + stem
        photo = f'<code class="key">{esc(stem)}</code>'
        if explorer_available:
            browse = f'explorer.html#frame={quote(key, safe="")}'
            photo = f'<a href="{esc(browse)}">{photo}</a>'
        elif key in images:
            photo = (f'<a href="{esc(images[key])}" target="_blank" '
                     f'rel="noopener noreferrer">{photo}</a>')
        if key in urls:
            return (photo + f'<br><a href="{esc(urls[key])}" target="_blank" '
                    'rel="noopener noreferrer">Suggest label / correction in Labelbox</a>')
        return photo + '<br><small>No Labelbox item link recorded</small>'
    # One note sits above the table: the queue is ordered weakest first, so the
    # first screen is full of 0.001s and needs the gloss before it, not after.
    # The other two follow the table, where a reader who already has the rows
    # in front of them reads what the order is not measured against and how to
    # read the confidence column.
    body += ('<h3 class="sub">First ' + f'{len(head)}' + ' photos in the ranked pool</h3>'
             + '<p class="note"><b>Photos least similar to labelled examples come first '
               'inside each queue.</b> "How new it looks" is the saved visual distance '
               'to labelled photos, not evidence of a new species. Unranked photos '
               'keep their confidence order.</p>'
             + ('<p class="note">Photo links open the catalogue, which carries its own '
                'saved labels and guesses. Queue scores remain from the snapshot above.</p>'
                if explorer_available else '')
             + table([("#", True), ("photo", False), ("Pl@ntNet's guess", False),
                      ("confidence", True), ("frames that species has", True),
                      ("how new it looks", True)],
                     [[f"{i}", photo_links(stem),
                       f'<span class="sp">{explorer_link(c, pred, "prediction", esc(cap(pred)))}</span>',
                       f"{cf:.3f}",
                       f"{c.support.get(pred, 0):,}", esc(how_new)]
                      for i, (_, stem, pred, cf, _rank, how_new) in enumerate(head, 1)],
                     source="send_first_queue.csv")
             + ungraded_note(c)
             + '<p class="note"><b>Confidence breaks ranking ties.</b> A low score '
               'means the model is unsure of its first guess. Check the guess '
               'against the photo; the score does not confirm a label.</p>')
    return body


def send_notes(c):
    """The four questions a reader of the table above asks, in order: which
    species fill the first queue, where the full list lives, what to do with the
    photos that got no answer, and which frames none of this covers."""
    body = ""
    body += (f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Inspect these photos '
             f'by eye; an empty answer does not establish that no plant is visible.</p>'
             # Names an unscored population. It is an export batch, not a camera.
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
            f'They are the test set '
            f'this page\'s own accuracy is measured on. Sending one back for '
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
                 f"{c.queue_counts.get('long_tail', 0):,} photos point at a species with "
                 f"fewer than {hc.WELL_SAMPLED_MIN_N} labelled frames, or one the model gets right "
                 f"less than {pctf(hc.HARD_MAX_TOP1, 0)} of the time; "
                 f"{c.queue_counts.get('low_conf_known', 0):,} show a usually-right species "
                 f"the model is unsure of here. These queues come first to target gaps "
                 f"in labelled evidence. Inside each queue the photo least like everything already "
                 f"labelled comes first, which applies to {c.n_ranked:,} of the "
                 f"{c.n_unlab:,}; the rest keep their place by confidence. "
                 f'<a href="send_first_queue.csv">send_first_queue.csv</a> holds this same '
                 f"order, one row per frame.",
                 # Open: the answer to "what do I label next" is the queue
                 # table itself, not a summary of it.
                 body, open_=True, anchor="what-to-send-first")
