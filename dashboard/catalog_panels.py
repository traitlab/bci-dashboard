"""The queue page's open panel when it shows the catalog batches.

Takes the place of ``queue_panels.p_send`` when ``catalog_queue.load`` found
the catalog files. Everything that panel says about the main pool's order (by
how a photo looks, the held-out frames, the later export batch, the photo and
Labelbox links) is not true of these rows, so it is not said here.
"""

from __future__ import annotations

from collections import Counter

import core as hc
import queues
from assets import cap, esc, more, panel, pctf, table
from catalog_queue import batch_rule, packer
from queue_panels import DISPATCH, QL, SEND_PREVIEW, readout_block

# The low-confidence rule the catalog queue runs (`by_margin`): the gap between
# the first two names, not the first score alone.
MARGIN_RULE = ("A usually-right species, two names close",
               (f"Right at least {pctf(hc.RELIABLE_MIN_TOP1, 0)} of the time overall, but "
                f"the first guess leads the second by less than {hc.LOW_CONF:.2f} here"))
LEFT_OUT = {"no_answer": "got an answer with no species",
            "no_prediction": "have no cached Pl@ntNet answer",
            "already_sent": "are already in a round ledger",
            "same_crown": "show a crown another queued frame already shows"}


def _rule(q):
    return MARGIN_RULE if q == "low_conf_known" else QL[q]


def pool_table(c):
    cat = c.catalog
    out = [f"{n:,} {LEFT_OUT.get(s, s)}" for s, n in sorted(cat["status"].items())
           if s != "batched"]
    body = (f'<p class="note">The pool is the {cat["n_pool"]:,} frames of the 2026 catalog: '
            f'Labelbox dataset rows in no project, each sent to Pl@ntNet once. '
            f'{c.n_unlab:,} are queued and batched'
            + (f'; {"; ".join(out)}' if out else "") + '. '
            f'Every share below is out of the {c.n_unlab:,}.</p>')
    body += table([("queue", False), ("which frames land here", False),
                   ("unlabelled frames", True), ("share of the queue", True)],
                  [[esc(_rule(q)[0]), esc(_rule(q)[1]), f'{c.queue_counts.get(q, 0):,}',
                    pctf(c.queue_counts.get(q, 0) / c.n_unlab if c.n_unlab else None)]
                   for q in queues.QUEUE_ORDER], source="send_first_queue.csv")
    return body + ('<p class="note">Rows are tried top to bottom. The first one that fits '
                   'wins, so a weak prediction on a rare species stays in the first queue.</p>')


def links_note(c):
    cat = c.catalog
    return (f'<p class="note"><strong>The photos are in private Arbutus buckets.</strong> '
            f's3_uri in <a href="send_batches.csv">send_batches.csv</a> names where each whole '
            f'frame sits, filled on {cat["n_s3"]:,} of {c.n_unlab:,} rows. It opens only with '
            f'storage credentials, so this page shows no photo and links none. labelbox_url and '
            f'data_row_id are blank: <code>dispatch_round.py</code> looks each frame up in the '
            f'Labelbox dataset by its global_key.</p>')


def batches_table(c):
    """Each batch's make-up, so the rule above can be checked batch by batch."""
    cat = c.catalog
    prio = set(cat["priority_batches"])
    rows = []
    for b, brows in cat["batches"].items():
        n = Counter(r["queue"] for r in brows if r["picked_by"] == "queue")
        rows.append([f"{b}", "yes" if b in prio else "", f"{len(brows):,}"]
                    + [f"{n[q]:,}" for q in queues.QUEUE_ORDER]
                    + [f'{sum(r["picked_by"] == "control" for r in brows):,}'])
    return table([("batch", True), ("priority missions", False), ("photos", True)]
                 + [(q.replace("_", " "), True) for q in queues.QUEUE_ORDER]
                 + [("random control", True)], rows, source="send_batches.csv")


def preview_table(c):
    """The head of the batch file: what goes out first."""
    cat = c.catalog
    head = [r for rows in cat["batches"].values() for r in rows][:SEND_PREVIEW]
    rows = []
    for i, r in enumerate(head, 1):
        q = cat["queue_of"][r["global_key"]]
        rows.append([f"{i}", r["batch_id"], f'<code class="key">{esc(r["global_key"])}</code>',
                     f'<span class="sp">{esc(cap(q["predicted_species"]))}</span>',
                     f'{float(q["confidence"]):.3f}', f'{int(q["species_labelled_crowns"]):,}',
                     esc(r["queue"].replace("_", " ")),
                     "random control" if r["picked_by"] == "control" else "queue order"])
    return (f'<h3 class="sub">First {len(head)} photos in send_batches.csv</h3>'
            + table([("#", True), ("batch", True), ("photo", False),
                     ("Pl@ntNet's prediction", False), ("confidence", True),
                     ("frames that species has", True), ("queue", False),
                     ("picked by", False)], rows, source="send_batches.csv"))


def p_send(c):
    """What to send, batch by batch, and the rules that made the batches."""
    cat = c.catalog
    order = ("Inside each queue the priority-mission frames come first, then "
             + ("the rarest species, by IUCN category, census stems and range, with the "
                "lowest confidence breaking ties." if cat["rarity"] else
                "the lowest confidence first."))
    pk = packer()
    body = (preview_table(c) + DISPATCH
            + more("How the batches are made up",
                   f'<p class="note">{batch_rule(cat)} A batch takes at most '
                   f'{queues.SPECIES_CAP} queue photos of one predicted species and, while '
                   f'other photos are waiting, at most {pk.MISSION_CAP} of one mission, '
                   f'{pk.SITE_CAP} of one site and {pk.SEASON_CAP} of one season. {order} The random control and the queue picks are '
                   f'compared once a round is labelled.</p>'
                   + readout_block(c) + batches_table(c))
            + more("Queue sizes and where the photos are", pool_table(c) + links_note(c)))
    return panel(f"What to send to the botanist next: {c.n_batches} batches of "
                 f"{c.n_unlab:,} unlabelled photos",
                 f"<b>Send the batches in order.</b> {batch_rule(cat)} "
                 f'<a href="send_first_queue.csv">send_first_queue.csv</a> holds the same '
                 f"photos in queue order, one row per frame.",
                 body, open_=True, anchor="what-to-send-first")
