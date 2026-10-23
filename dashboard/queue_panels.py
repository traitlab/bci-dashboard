"""Panels used only by the queue page, the open half a reader acts on. The
closed half that argues for the order is ``queue_why_panels.py``, and
``page.PANELS`` still names every panel on both pages.
"""

from __future__ import annotations

import os
from urllib.parse import quote

import core as hc
import queues
from assets import cap, esc, explorer_link, more, panel, pctf, table
from panels import NAMING_IS, NAMING_NOTE
from queue_filters import DISPATCH_CMD
from selection_panels import _fmt_pct as sel_pct
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


# Below the un-measured claim either way: a reader who meets the
# control before the caveat above it would read the control as the whole
# answer, rather than as the one thing this checkout can still measure.
def _batch1_note(c) -> str:
    if not c.n_batch1:
        return ""
    n_control = min(queues.control_size(), len(c.queue_rows))
    return (
        f'<p class="note"><b>Every batch carries the comparison.</b> {n_control} of the '
        f'{c.n_batch1} photos in batch 1, and the same share of every later batch, are drawn at '
        'random from the photos not sent yet instead of from the head of this order. When they '
        'come back labelled, the two groups can be compared batch by batch.</p>')

# The fallback for a checkout with no audit file: labelfirst has measured
# nothing yet, so the note cannot say more than that.
_UNMEASURED_NOTE = (
    '<p class="note"><b>This order has not been measured yet.</b> Nothing here measures '
    'whether it fills gaps faster than sending photos at random. The wait rule further down <em>is</em> '
    'measured.</p>')


READOUT_FILE = "round_readout.csv"


# read_round.py arm names, as CONTEXT.md says a page words them
PICKED_BY = {"prioritised": "prioritised", "control": "random control"}


def readout_rows(c) -> list:
    """Closed rows of the round read-out, or [] when the file or any closed row
    is absent. Intervals must be rates in [0, 1]; anything else aborts the build
    rather than printing a number that cannot be one."""
    verify_dir = getattr(c, "verify_dir", None)
    path = os.path.join(verify_dir or "", READOUT_FILE)
    if not verify_dir or not os.path.exists(path):
        return []
    closed = [r for r in hc.read_csv_rows(path) if r["status"] == "closed"]
    for r in closed:
        if not r["corrections_lo"]:  # no labelled row had a first guess, so no interval
            continue
        lo, hi = float(r["corrections_lo"]), float(r["corrections_hi"])
        if not 0 <= lo <= hi <= 1 or int(r["corrections"]) > int(r["n_with_guess"]):
            raise SystemExit(f"VERIFY FAIL: {READOUT_FILE} row {r['scope']}/{r['arm']} has an "
                             f"interval or count that is not a rate: {lo}, {hi}")
    return closed


def readout_block(c) -> str:
    """Prioritised photos against the random control, once a round has closed.
    Until then it says pending. Each row carries how many photos were sent and
    labelled, so a rate is never read without its support."""
    closed = readout_rows(c)
    if not closed:
        return ('<p class="note"><b>Prioritised vs random control:</b> pending, no round '
                'closed yet.</p>')
    rows = []
    for r in closed:
        # read_round scores corrections over labelled rows that had a first guess
        g = int(r["n_with_guess"])
        rate = (f'{pctf(int(r["corrections"]) / g)} ({pctf(float(r["corrections_lo"]))} to '
                f'{pctf(float(r["corrections_hi"]))})') if g else "n/a"
        rows.append([esc(r["scope"]), esc(PICKED_BY.get(r["arm"], r["arm"])), f'{int(r["n_sent"]):,}',
                     f'{int(r["n_labelled"]):,}', f'{int(r["corrections"]):,}', rate,
                     f'{int(r["new_rows"]):,}', f'{int(r["long_tail_rows"]):,}'])
    return ('<p class="note"><b>Prioritised vs random control.</b> For each closed round, the '
            'share of labelled photos where the botanist corrected the model, with its '
            'interval. A small number of labelled photos gives a wide interval; read the '
            'counts first.</p>'
            + table([("round", False), ("picked by", False), ("sent", True), ("labelled", True),
                     ("corrections", True), ("correction rate (interval)", True),
                     ("new rows", True), ("long-tail rows", True)], rows))


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
        # A closed round is a measurement, so the "not measured" line goes.
        return ("" if readout_rows(c) else _UNMEASURED_NOTE) + readout_block(c) + _batch1_note(c)
    saved = ""
    if a["passed"] and a["labels_saved_pct"] is not None:
        saved = (f' It needs {sel_pct(a["labels_saved_pct"])} fewer labels for the same '
                 'rare species.')
    return (f'<p class="note"><b>What this order is measured against.</b> On the '
            f'{a["n_frames"] or 0:,} labelled frames that already carry a name, this '
            f'ordering finds rare species faster than a random order.{saved} '
            + ('This pool is measured by the closed rounds below.</p>' if readout_rows(c) else
               'This pool is not: it carries no label yet, so nothing here checks whether this '
               'order fills gaps faster than a random one on it.</p>')
            + readout_block(c) + _batch1_note(c))


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
    f'packed into batches of {queues.BATCH_SIZE}, {queues.GROUP_PHRASE[queues.GROUP_BY]}. To send a '
    'batch, after checking its status in Labelbox, run this first with the chosen '
    f'round and batch numbers. This example selects batch 1 of round {hc.next_round()}:</p>'
    f'<pre class="cmd">{DISPATCH_CMD.format(round=hc.next_round(), batch=1)}</pre>'
    '<p class="note"><code>--dry-run</code> writes nothing and calls no API: it reports '
    'how many photos it would send and skips any sent in an earlier round. Drop it to send the full batch. '
    '<strong>Adding <code>--test</code> instead creates a live five-photo batch and '
    'updates metadata in Labelbox</strong>; it is not an offline preview.</p>'
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
            f'than guessed.</p>')


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


CALIBRATION_FILE = "confidence_calibration.csv"
# The calibration scope this note reads: every frame with a species-level label.
CALIBRATION_SCOPE = "all_species_level_gt"


def threshold_evidence(c) -> str:
    """How often the first guess was right at each queue cut-off, off the
    calibration table the build verified. Empty when the table or either row is
    absent, rather than a number from somewhere else. The two values are not
    changed here: the table says what each separates."""
    verify_dir = getattr(c, "verify_dir", None)
    path = os.path.join(verify_dir or "", CALIBRATION_FILE)
    if not verify_dir or not os.path.exists(path):
        return ""
    rows = [r for r in hc.read_csv_rows(path) if r["scope"] == CALIBRATION_SCOPE]
    pick = lambda kind, band: next(
        (r for r in rows if r["row_type"] == kind and r["band"] == band), None)
    high = pick("threshold", f">={hc.WAIT_CONF}")
    low = pick("bin", f"[0.0,{hc.LOW_CONF})")
    # An empty band has no accuracy to quote.
    if not high or not low or not int(high["n_crowns"]) or not int(low["n_crowns"]):
        return ""
    total = sum(int(r["n_crowns"]) for r in rows if r["row_type"] == "bin")
    say = lambda r: (f'right on {int(r["n_correct"]):,} of {int(r["n_crowns"]):,} frames '
                     f'({pctf(float(r["top1_accuracy"]))})')
    return (f'<p class="note"><strong>How often the first guess was right.</strong> On the '
            f'{total:,} labelled frames with a species-level label, at confidence '
            f'{hc.WAIT_CONF:.2f} or more it was {say(high)}; under {hc.LOW_CONF:.2f} it was '
            f'{say(low)}. A confident guess can still be wrong: '
            f'{int(high["n_wrong"]):,} frames at {hc.WAIT_CONF:.2f} or more were. '
            f'{hc.WAIT_CONF:.2f} is the confidence line; {hc.LOW_CONF:.2f} marks low confidence. '
            f'Both values were set by judgement, not fitted to this table; the table shows what each separates. '
            f'<a href="{CALIBRATION_FILE}">{CALIBRATION_FILE}</a></p>')


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
             + '<p class="note">"How new it looks" is the distance to '
               'labelled photos only, so it falls down the table overall but not row '
               'by row. It is not evidence of a new species.</p>'
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
            f'They are held back for grading: this page\'s own accuracy is measured '
            f'on them. Sending one for labelling would put a new answer into the set '
            f'those numbers are measured on.</p>')


def p_send(c):
    """The page's answer to "what do I label next": queue sizes, the head of
    the queue, then the caveats that qualify both."""
    # The queue itself first; sizes, link coverage and caveats are checks on it,
    # so they sit closed beneath it.
    body = (send_preview_table(c) + DISPATCH
            + more("Queue sizes, link coverage and caveats",
                   send_pool_table(c) + threshold_evidence(c) + links_note(c) + held_out_note(c) + send_notes(c)))
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
                 f"the model is unsure of here. Inside each queue the photo least like anything labelled "
                 f"comes first, then the one least like the labelled photos and those above it. "
                 f"This applies to {c.n_ranked:,} of the "
                 f"{c.n_unlab:,}; the rest keep their place by confidence. "
                 f'<a href="send_first_queue.csv">send_first_queue.csv</a> holds this same '
                 f"order, one row per frame.",
                 # Open: the answer to "what do I label next" is the queue
                 # table itself, not a summary of it.
                 body, open_=True, anchor="what-to-send-first")
