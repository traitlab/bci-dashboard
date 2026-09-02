"""Every panel the dashboard pages can carry, and the one context they share.

The 2026-08-27 split gave the panels two audiences. The internal page answers
"what do we label next" and belongs to the labelling team; its real deliverable
is ``send_batches.csv``, so the page stays thin. The external page answers "how
does Pl@ntNet do against the labels" and is the one that leaves the lab. A
panel therefore names its audience once, here, instead of a page hand-keeping a
list of what it happens to include.

The arithmetic lives in ``figures.py``: ``figures.prepare`` computes every
derived figure once and each builder here reads it, rather than each builder
recomputing from ``Health``. Two panels recomputing the same figure is exactly
the drift ``history.verify_snapshot`` exists to catch, and it would catch it
only after both pages were already built.

Stdlib only, like the rest of ``dashboard/``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core as hc
from assets import (CSS, JS, cap, esc, filterable_table, hero, panel,
                    pctf, section, status_legend, status_tag, svg_hbar, table)
from crop_overlap import CROP_SIZE, FRAME_H, FRAME_W
from explain import (BAND_SHORT, CONF_BAND_WORDS, candidates_panel, method_panel,
                     weighting_panel)
from figures import (CONFIRMATORY_CSV, RARE_MAX_SUPPORT, RECOMMENDED_CONF,
                     WAIT_SUPPORT_MIN, conf, top1)

# Enough to answer "what do I send next" without a CSV reader. A batch is 100
# frames, so 25 is one morning's work and still short enough to read.
SEND_PREVIEW = 25
# Same reasoning, shorter: this list is read, not worked through.
REVIEW_PREVIEW = 15

# key -> (label, what to do about it). Order is the order of the to-do list:
# cheapest useful work first, safe-to-skip last.
STATUS = {
    "ranking": ("Right name in the list, not first",
                "Cheapest work here. Confirm the name from the short list instead of "
                "identifying from scratch"),
    "unmeasured": ("Too few labels to judge",
                   "Label a few more before trusting any number for it"),
    "hard": ("Wrong even with enough labels",
             "More labels will not fix this one. Treat it as a model limit"),
    "adequate": ("Mixed", "Keep it in the normal review queue"),
    "reliable": ("Usually right", "Lowest priority. Spot-check a few and move on"),
    # "in five candidates" described the wrong set. core.diagnose reads
    # in_corpus_vocabulary, which is true when the name came back on ANY BCI
    # photo, not only on this species' own frames. Rows showing 0.0% in the
    # list column with a different status are the difference, and the old
    # wording made those rows look like a contradiction.
    "unreachable": ("Never returned on any BCI photo",
                    "Nothing to do until we know whether Pl@ntNet carries this "
                    "species at all"),
}

STATUS_REASON = {
    "ranking": "The right name is already in the five, so this is the cheapest confirmation work.",
    "unmeasured": f"Fewer than {hc.WELL_SAMPLED_MIN_N} labelled frames, so the score is "
                  f"too thin to trust yet.",
    "hard": "Enough frames, but the first guess is still weak, so more labels will not fix it.",
    "adequate": "Mixed results, so keep it in the normal review queue.",
    "reliable": "Usually right, so this species is low priority for extra work.",
    "unreachable": "Pl@ntNet never returned this name on any BCI photo, not just on this "
                   "species\u2019 own frames. Labelling will not recover it. A row showing "
                   "0.0% in the list column under some other status was returned on another "
                   "species\u2019 photo, so the model can produce that name.",
}

def status_precedence_note():
    """One sentence saying a species gets the first status that fits it.

    Built from ``hc.STATUS_PRECEDENCE`` rather than written out, so a change to
    the order in ``diagnose`` cannot leave the page describing the old one.
    """
    names = [STATUS[k][0].lower() for k in hc.STATUS_PRECEDENCE]
    return ("Each species gets one status. The rules are checked in this order: "
            + ", then ".join(f"&ldquo;{n}&rdquo;" for n in names)
            + f". So a few-frame species can still show as &ldquo;{names[2]}&rdquo;. "
            "That is the point: it is cheap work whatever its count. Read the "
            "labelled-frames column next to the status.")


# A 2x2 grid: question asked (rows) by how it was averaged (columns), because
# 50.3% / 79.5% side by side reads as one superseding the other.
# (metric, question, averaged over, note).
HEADLINES = [
    ("macro_top1", "First guess is right", "per species",
     "each of the {n_sp} species counts once, however few frames it has"),
    ("micro_top1", "First guess is right", "per frame",
     "one vote per labelled frame, so common species dominate"),
    ("macro_top5", "Right name is among the {k} requested", "per species",
     "the best we could do if a botanist picked the right name out of the {k} every "
     "time, so a ceiling on our {k}-name request, not on the model"),
    ("micro_top5", "Right name is among the {k} requested", "per frame",
     "we only ever asked Pl@ntNet for {k} names"),
]

# Sits directly under the grid. Without it the two columns read as a
# contradiction rather than as two questions.
HERO_READING = (
    "Read down a column, not across. <b>Per species</b> is the number to quote for "
    "a species picked off the checklist; <b>per frame</b> is the number to quote for "
    "a photo picked off the drive. Per frame is the higher of the two because the "
    "species with many frames are the ones Pl@ntNet already knows."
)

# The centre crop as a share of the frame. Derived, and formatted once, because the
# page printed it twice at two roundings (13.65% and 13.7%) and a reader met both.
CROP_SHARE = f"{100 * CROP_SIZE ** 2 / (FRAME_W * FRAME_H):.1f}%"

# What a reader has to know before any number on the page means anything. The
# crown sentence is here rather than beside the headline because the headline is
# the first thing on the page and a term defined under it is defined too late.
def hero_terms(k):
    """The four words, and the request setting, in the wording the page uses.

    A function rather than a constant because the number of names we ask for is a
    setting, and a setting written into a constant is a sentence that stops being
    true without anything noticing.
    """
    return (
        f"A <b>frame</b> is one {FRAME_W}&times;{FRAME_H} drone photo. A <b>crown</b> is one tree "
        "canopy a botanist outlined inside a frame. A frame's <b>label</b> is the species whose "
        "outlined crowns cover the most area in the <i>whole</i> frame. "
        f"The <b>centre crop</b> is the fixed {CROP_SIZE}&times;{CROP_SIZE} square from the middle "
        f"of a frame, which is {CROP_SHARE} of the frame&rsquo;s area. That square is what "
        "most of this page sends to "
        "Pl@ntNet. "
        f"We ask Pl@ntNet for {k} names per photo (<code>nb-results={k}</code>). That is our "
        "request setting, not a limit of the model. The <b>first guess</b> is the top-ranked "
        "of those names, and <b>right</b> means it matches the frame's label. "
        "<b>Outlining the trees first</b> means something else. We ask Pl@ntNet about each "
        "crown on its own. Then we combine the answers into one name for the frame, weighted "
        "by how much of the frame each crown covers. That is the same rule the label itself is "
        "built from, which is why it is the fairer of the two numbers at the top."
    )

# The two regions above are not the same region, and the numbers below compare
# across them. Stated here rather than in a footnote because every figure on
# this page inherits the mismatch.
def hero_region(c):
    """How far the crop and the label disagree, counted rather than remembered.

    Was a module constant with the counts written into the prose. They were
    stale and measured over the wrong population, which is the failure the rest
    of this file avoids by recomputing every figure at build time.
    """
    half = sum(1 for r in c.sp_recs if (r.get("crop_coverage") or 0) < 0.5)
    none_ = sum(1 for r in c.sp_recs if (r.get("crop_coverage") or 0) == 0)
    return (
        "<strong>These four numbers judge a centre crop against a label for the whole "
        f"frame.</strong> The two are not always looking at the same tree. On {half:,} of "
        f"{len(c.sp_recs):,} scored frames the labelled species covers less than half the "
        f"crop, and on {none_:,} it covers none of it. A wrong answer here is therefore not "
        "always a wrong identification. Read these four as a record of what the centre-crop "
        "path did, not as the model's accuracy. The number at the top of the page, where a "
        "botanist outlined the trees first, is the one to quote: it names the same thing the "
        "label names. "
        '<a href="#where-the-headline-comes-from">Where these two numbers come from</a> '
        "says which frames it was measured on."
    )

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


def cam_phrase(cameras):
    """Name the camera the way the queue page names it, when there is one.

    The frozen sample is single-camera by design, but the field is read from the
    frame keys rather than assumed, so a future sample carrying both must not
    render as one camera with two names.
    """
    return ({"zoom": "the drone&rsquo;s wide-angle camera, named <code>zoom</code> in the "
                     "file names",
             "tele": "the drone&rsquo;s long-lens camera, named <code>tele</code> in the "
                     "file names"}.get(cameras)
            or f"these cameras: <code>{esc(cameras)}</code>")


def pfmt(p, draws):
    """A bootstrap p that came back zero is a resolution limit, not a zero.

    Printing 0.00000 claims a precision 10,000 resamples cannot buy, so a p
    below one draw is reported as the bound the draw count supports.
    """
    floor = 1.0 / draws
    return f"&lt; {floor:.4f}" if p < floor else f"= {p:.5f}"


def confirmatory_hero(cf):
    """The two ways of asking, side by side, outline-first leading.

    Outline-first leads because it names the same thing the label names. The
    centre-crop number stays beside it rather than being retired, because every
    other number on this page is still measured that way and a reader needs the
    two in the same field of view to know what the gap costs.
    """
    if cf is None:
        raise SystemExit(
            f"{CONFIRMATORY_CSV} is missing, so the headline this page leads with "
            f"cannot be published. Run: python3 dashboard/score_confirmatory.py "
            f"--out {CONFIRMATORY_CSV}")
    if cf.get("stamp") != "CONFIRMATORY":
        raise SystemExit(
            f"the confirmatory result is stamped {cf.get('stamp')!r}, not "
            f"'CONFIRMATORY'. The stopping rule says the read happens once on the "
            f"complete set, so an exploratory number must not be published here.")
    # The card says what was done to the photo, not what the design calls it. A
    # reader has to be able to tell the two numbers apart without opening a
    # panel; "region-aligned" and "legacy" did not do that. What each way of
    # asking did in detail is the panel below. The card keeps the rate, its
    # support and its range, which is the whole of what a number needs to
    # travel with.
    ways = (("crown", "A botanist outlined the trees first"),
            ("photo", "We sent the middle of the photo"))
    return hero([
        (label, pctf(cf[f"{way}_top1"]),
         f'First guess right, on the {int(cf["n_frames"])} set-aside frames',
         f'{int(cf[f"{way}_hits"])} of {int(cf[f"{way}_n"])} frames right. '
         f'We are 95% sure the true rate is between '
         f'{pctf(cf[f"{way}_top1_site_lo"])} and {pctf(cf[f"{way}_top1_site_hi"])}.')
        for way, label in ways])





# ---------------------------------------------------------------------------
# Panels. One function per panel, each reading only the prepared context, so a
# page is a list of panel ids rather than 400 lines of interleaved rendering.
# ---------------------------------------------------------------------------

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
                f'<p class="note"><strong>Cheaper still, and not counted in any row above: '
                f'{c.gen_one:,} frames whose botanist label stops at the genus.</strong> Their five '
                f'candidates contain exactly one species from that genus. The question '
                f'there is yes or no, not which of {c.n_sp}. Those frames sit outside the '
                f'{c.n_sp} species scored on this page, because they never named a species. '
                f'The model-health page says more about what those frames can and '
                f'cannot show.</p>')
    return panel(f"Where to spend botanist time next: {c.counts['ranking']} species are a "
                 f"cheap confirmation, {c.counts['unreachable']} are not worth time yet",
                 "<b>Work top to bottom.</b> Rows are ordered cheapest useful work first, "
                 "and the last two rows are work you can skip.",
                 "\n".join(body), open_=True)


def p_send(c):
    body = table([("queue", False), ("unlabelled frames", True),
                  ("share of the pool", True)],
                 [[f'<strong>{esc(QL[q][0])}</strong>' if q in ("long_tail", "low_conf_known")
                   else esc(QL[q][0]),
                   f'{c.queue_counts.get(q, 0):,}',
                   pctf(c.queue_counts.get(q, 0) / c.n_unlab if c.n_unlab else None)]
                  for q in hc.QUEUE_ORDER])
    # The list itself, not a pointer to it: the counts above say how much work
    # there is, and the CSV in the snapshot folder said which photo.
    head = c.queue_rows[:SEND_PREVIEW]
    body += ('<h3 class="sub">The next ' + f'{len(head)}' + ' photos, in order</h3>'
             + table([("#", True), ("photo", False), ("Pl@ntNet's guess", False),
                      ("confidence", True), ("frames that species has", True)],
                     [[f"{i}", f'<code class="key">{esc(stem)}</code>',
                       f'<span class="sp">{esc(cap(pred))}</span>', f"{cf:.3f}",
                       f"{c.support.get(pred, 0):,}"]
                      for i, (_, stem, pred, cf) in enumerate(head, 1)]))
    # How to read the confidence column, next to the column. The queue is ordered
    # weakest first, so the first screen of it is full of 0.001s, and a reader who
    # takes those as predictions sees expert time being spent on coin flips.
    body += ('<p class="note"><b>Read the confidence column as how little the model '
             'knows, not as how likely the named species is.</b> A frame lands in a queue '
             'on which species was guessed, whatever the confidence. Inside a queue the '
             'weakest guesses come first, because those are the frames our labels cover '
             'worst. A guess near the bottom of the scale means Pl@ntNet recognised '
             'almost nothing, which is itself the reason to look.</p>'
             # The wait rule below is graded against a held-out set and prints its
             # error rate. This one is not graded at all, and a page that shows one
             # and not the other reads as if both had been checked.
             '<p class="note"><b>This order has not been graded.</b> The wait rule '
             'further down is measured against frames held back for that purpose, and '
             'prints how often it is wrong. Nothing here measures whether sending these '
             'photos first fills gaps faster than sending photos at random. Treat the '
             'order as a reasonable guess about where our labels are thin, not as a '
             'tested rule.</p>')
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
             f'<p class="note"><code>send_first_queue.csv</code> in the snapshot folder is '
             f'this same order with one row per frame: queue, photo key, the guess and its '
             f'confidence, and how well that species is already measured. '
             f'<code>send_batches.csv</code> is that list cut into batches of at most 100. '
             f'<b>Work the batches file.</b> Open the queue file only to check the '
             f'ordering.</p>'
             f'<p class="note"><strong>{c.n_no_answer} unlabelled photos got no answer at '
             f'all</strong>: the candidate list came back empty. Those are the photos most '
             f'likely to be junk or to show no plant (leaves in the water, bare trunks). '
             f'There '
             f'is no reliable automatic rule for junk, so check that handful by eye before '
             f'queueing them rather than filtering on it.</p>'
             f'<p class="note"><b>The drone carries two cameras, and every frame scored '
             f'on this page came from one of them.</b> The wide-angle camera (called '
             f'<i>zoom</i> in the file names) took all '
             f'{c.scored_cams["zoom"]:,} scored frames. The long-lens camera '
             f'(called <i>tele</i>) took none of them, because no tele frame has a '
             f'botanist label yet. Tele frames are '
             f'{c.queue_cams["tele"]:,} of the {sum(c.queue_cams.values()):,} photos in '
             f'this queue ({pctf(c.queue_cams["tele"] / sum(c.queue_cams.values()))}). '
             f'How well the model reads that camera is not known from here. Sending them '
             f'is how it becomes known.</p>'
             f'<p class="note">The pool is {c.n_unlab:,} of {len(c.h.split_rows):,} photos: '
             f'the frames with a cached Pl@ntNet answer and no botanist label. The other '
             f'{len(c.h.split_rows) - c.n_unlab:,} are already labelled, or have no cached '
             f'answer to rank. The species '
             f'record behind each queue is the one measured above, so a model update '
             f're-sorts this queue exactly as it re-sorts the can-wait one.</p>')
    # The same two queues the hero counts, added the same way. When the heading
    # named only the first queue, the hero's larger number and this smaller one
    # looked like two answers to the same question.
    send_now = (c.queue_counts.get("long_tail", 0)
                + c.queue_counts.get("low_conf_known", 0))
    return panel(f"What to send to the botanist first: {send_now:,} "
                 f"of {c.n_unlab:,} unlabelled photos",
                 f"<b>Work the queues top to bottom.</b> Two queues make up that "
                 f"{send_now:,}. First come {c.queue_counts.get('long_tail', 0):,} photos "
                 f"pointing at a species we barely have, or barely get right. Then "
                 f"{c.queue_counts.get('low_conf_known', 0):,} showing a usually-right "
                 f"species the model is unsure of here. Both buy more per label than "
                 f"anything below them.",
                 # Open with the overview above it. This page is opened to answer
                 # "what do I label next", and the answer is the queue table, not
                 # a summary of the queue table. A reader who has to click to
                 # reach the deliverable has been asked to guess where it is.
                 body, open_=True, anchor="what-to-send-first")


def p_review(c):
    pair_rows = sorted(c.review_pairs.items(), key=lambda kv: -len(kv[1]))[:10]
    # What each table is, before it rather than after it. The heading promises 51
    # frames and the first table showed ten rows summing to a fraction of that,
    # with nothing saying it was a grouping rather than the list.
    body = (f'<p class="note">The {c.review_counts[0]} frames fall into '
            f'{len(c.review_pairs)} label-and-guess pairs. The '
            f'{len(pair_rows)} commonest pairs are first, then the '
            f'{REVIEW_PREVIEW} single frames the model is surest about. All '
            f'{c.review_counts[0]} are in <code>label_review_queue.csv</code> in the '
            f'snapshot folder.</p>'
            + table([("botanist label", False), ("Pl@ntNet's first guess", False),
                   ("frames", True), ("mean confidence", True)],
                  [[f'<span class="sp">{esc(cap(gt))}</span>',
                    f'<span class="sp">{esc(cap(pr))}</span>',
                    f"{len(cs):,}", f"{sum(cs) / len(cs):.2f}"]
                   for (gt, pr), cs in pair_rows])
            if pair_rows else '<p class="note">None at this confidence.</p>')
    # The frames themselves, most confident first, each linked into Labelbox where
    # the link is known. Known means an export carried that data row: the URL is
    # read from what a merge recorded, never guessed and never fetched.
    urls = hc.labelbox_urls()
    top_review = sorted(c.review, key=lambda r: -conf(r))[:REVIEW_PREVIEW]
    linked = sum(1 for r in c.review if r["global_key"] in urls)
    body += table([("frame", False), ("botanist label", False),
                   ("Pl@ntNet's first guess", False), ("confidence", True)],
                  [[(f'<a href="{esc(urls[r["global_key"]])}" target="_blank" '
                     f'rel="noopener">{esc(r["global_key"])}</a>'
                     if r["global_key"] in urls else esc(r["global_key"])),
                    f'<span class="sp">{esc(cap(r["gt"]))}</span>',
                    f'<span class="sp">{esc(cap(top1(r)))}</span>',
                    f"{conf(r):.2f}"]
                   for r in top_review])
    body += (f'<p class="note">The {len(top_review)} most confident disagreements. '
             f'A frame name links straight to its row in Labelbox where we know the link: '
             f'{linked} of {len(c.review)} frames here. We know it only for frames that came '
             f'in on an export these labels were merged from. The rest are listed without a '
             f'link, rather than sent to a guessed address.</p>')
    body += (f'<p class="note">Each row is a labelled frame where the model is at least '
             f'{hc.REVIEW_CONF:.1f} confident in a <em>different</em> species. A first guess '
             f'this confident is right {pctf(c.confident_ok)} of the time in bulk '
             f'({c.confident_hits:,} of {len(c.confident):,}). So each row here is either a '
             f'rare confident mistake by the model, or a wrong label. A wrong label found '
             f'this way is the cheapest label fix available. Offline there is no way to tell '
             f'which of the two it is; that is the botanist\'s minute. '
             f'Every frame is in <code>label_review_queue.csv</code> in the snapshot folder, '
             f'most confident first.</p>'
             f'<p class="note">Not urgent: work this list after the send-first queues. A '
             f'confusion pair that keeps recurring is a signal about the species, not just '
             f'the photo.</p>')
    if c.n_adjudicated:
        body += (f'<p class="note">{c.n_adjudicated} further frame'
                 f'{"" if c.n_adjudicated == 1 else "s"} disagree at this confidence and '
                 f'are not listed: a botanist has already confirmed the label, so the model '
                 f'is simply wrong there and the frame would otherwise return to this list '
                 f'on every build. They still count against the '
                 f'{pctf(c.confident_ok)} above.</p>')
    return panel(f"Labels worth a second look: {c.review_counts[0]} frames where Pl@ntNet "
                 f"confidently disagrees",
                 # No cross-page pointer here: this panel is on the model-health
                 # page and the queues it used to defer to are on the other one.
                 f"<b>Put these {c.review_counts[0]} frames in front of a botanist.</b> "
                 f"Either the label is wrong or the model is, and one look settles "
                 f"which. They are the disagreements most worth an expert's minute.", body)


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
            f'They are the labelled frames marked <code>test</code> in '
            f'<code>splits.csv</code>, which is an input to this page rather than something '
            f'it computes. The species side of the rule was decided from the other frames, '
            f'so nothing here is graded on the frames that chose it. Every count in the '
            f'comparison table below is out of those {len(c.test_recs):,}.</p>'
            # Two hold-outs, described in almost the same words on two pages that
            # link to each other. A reader assumes one is a subset of the other.
            f'<p class="note">This is not the set the model-health page reports its two '
            f'headline numbers on. That one is a separate draw of '
            f'{int(c.cf["n_frames"])} frames, taken from '
            f'every labelled frame rather than from this column, and some frames fall in '
            f'both. Neither set is a subset of the other.</p>'
            '<p class="note"><strong>Nothing here is a label.</strong> A frame that can wait '
            'keeps whatever label it already has, or none at all. No guess is ever written '
            'in as a label by this rule. It only pushes frames down the '
            "botanist's queue.</p>"
            f'<p class="note"><strong>The decision expires with the model.</strong> Pl@ntNet '
            f'ships a new model every few months, on its own schedule rather than ours. A '
            f'frame pushed down the queue under <code>{esc(c.tag)}</code> is not pushed '
            f'down under the next one. Re-run this page after every model change and the '
            f'queue '
            f're-sorts. Any frame can come back to the top.</p>'
            f'<p class="note">{len(c.eligible)} species reach {WAIT_SUPPORT_MIN} labelled '
            f'frames inside the frames a rule is allowed to learn from, which is the second '
            f'half of the rule. Counting every label instead would give a larger number. Do '
            f'not read this against the rarely-labelled count elsewhere on this page, which '
            f'counts every label.'
            # Two unrelated counts on this page are 41 today, and a reader who meets
            # the second one takes it for a back-reference to the heading.
            + (f' It is also a different set from the {c.counts["ranking"]} species named in '
               f'the panel heading above, which happens to be the same size.'
               if c.counts["ranking"] == len(c.eligible) else '')
            + f' The error rate '
            f'above is measured on the {len(c.test_recs):,} frames held back from that. So '
            f'no rule is graded on the frames that chose it.</p>')
    return panel(f"Which frames can wait: {best['n']:,} of the {len(c.test_recs):,} frames "
                 f"held back for grading, undone at the next model change",
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
             f'of the {len(c.test_recs):,} held-out frames. No rarely-labelled frame can be '
             f'pushed down the queue by a rule that also asks for labelled frames: that '
             f'second condition leaves them out.</p>')
    return panel("How the five candidate rules compare, with and without the "
                 "labelled-frames condition",
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
            + '<p class="note">Over all frames at once the confidence score is trustworthy: '
              'when the model is sure it is almost always right. That is what makes queue '
              'ordering possible at all.</p>'
              '<p class="note"><strong>It is not trustworthy on rarely-labelled '
              'species.</strong> Ordering the queue on confidence alone would push exactly '
              'the species you care about to the bottom:</p>'
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


def p_labels(c):
    buckets = c.buckets
    body = (svg_hbar([(BAND_SHORT[lab], buckets[lab]["c1"] / buckets[lab]["n_crowns"],
                       f'{pctf(buckets[lab]["c1"] / buckets[lab]["n_crowns"])}  ·  '
                       f'{buckets[lab]["n_species"]} spp, {buckets[lab]["n_crowns"]:,} '
                       f'frames', "#1565c0")
                      for lab in hc.BUCKET_ORDER
                      if buckets.get(lab) and buckets[lab]["n_crowns"]],
                     title="how often the first guess is right, by how many frames that "
                           "species has")
            + '<div class="warn"><strong>Read this as how common the species is, not as '
              'training data.</strong> These predictions come from a frozen Pl@ntNet '
              'regional model that has never seen a single BCI label, so labelling a species '
              'does not make Pl@ntNet better at it. What this axis really tracks is how '
              'common a species is on the plot, and common species also have more reference '
              'photos inside Pl@ntNet. What extra labels buy is knowledge: below about '
              f'{WAIT_SUPPORT_MIN} frames a per-species accuracy jumps around too much to '
              f'act on, and above it the species can enter the queue-ordering rule.</div>')
    return panel("Does accuracy rise with more labels? It rises with abundance, and the "
                 "model is frozen",
                 "<b>Use this to see where the measurement is solid enough to act on.</b> "
                 "Do not use it to argue that labelling raises accuracy.", body,
                 anchor="accuracy-and-labels")


def p_species(c):
    sp_rows, attrs = [], []
    for d in sorted(c.per_species, key=lambda x: (-x["n_labelled_crowns"], x["species"])):
        sp, st = d["species"], c.status[d["species"]]
        sp_rows.append([
            f'<span class="sp" data-sort="{esc(sp)}">{esc(cap(sp))}</span>',
            f'<span data-sort="{d["n_labelled_crowns"]}">{d["n_labelled_crowns"]:,}</span>',
            f'<span data-sort="{d["top1_accuracy"]:.6f}">{pctf(d["top1_accuracy"])}</span>',
            f'<span data-sort="{d["top5_accuracy"]:.6f}">{pctf(d["top5_accuracy"])}</span>',
            f'<span data-sort="{d["mean_top1_confidence"]:.6f}">'
            f'{d["mean_top1_confidence"]:.2f}</span>',
            status_tag(st, STATUS[st][0])])
        attrs.append(f' data-species="{esc(sp)}" data-status="{st}"')
    body = (status_legend([(st, STATUS[st][0], STATUS_REASON[st]) for st in STATUS])
            + '<p class="note"><b>Model&rsquo;s confidence</b> is Pl@ntNet&rsquo;s own score '
              'for its first guess, averaged over that species&rsquo; frames. Pl@ntNet '
              'splits one whole unit of confidence across every species it knows. So 0.86 '
              'means it put nearly all of that on one name, and 0.32 means it was spread '
              'thin.</p>'
            + filterable_table(
        [("Species", False), ("Labelled frames", True),
         ("First guess right", True), ("Right name in the list", True),
         ("Model's confidence", True), ("Status", False)],
        sp_rows,
        options=[(k, v[0]) for k, v in STATUS.items()],
        row_attrs=attrs,
    ))
    return panel(f"Look up one species: all {c.n_sp}, sortable and filterable",
                 "<b>Find a species you care about and read its status.</b> Click any "
                 "heading to sort, type to filter. " + status_precedence_note(),
                 body, open_=True)


def p_ceiling(c):
    n, gn = c.n, c.gn
    body = (f'<p class="note"><strong>{len(c.never)} species ({c.never_crowns} of the {n:,} '
            f'evaluated frames) never appear in any answer the model gave us.</strong> '
            f'Leaving them out raises the per-frame rate from {pctf(c.c1 / n)} to '
            f'{pctf(c.reach1)} on {len(c.reach):,} centre crops. A wider population: every '
            f'one of the {len(c.h.gt_rows):,} frames carrying a botanist label, genus-only '
            f'frames and the few with no cached answer included. Counted that way, '
            f'{c.never_all} frames carry a name the model never returned to us.</p>'
            f'<div class="warn"><strong>This is a limit of the question we asked, not proof '
            f'the model has never heard of these species.</strong> The only test we can run '
            f'offline is whether a species name turns up somewhere in the cached answers, and '
            f'we asked Pl@ntNet for its best five candidates per photo. A species Pl@ntNet '
            f'knows perfectly well, but which never made anyone\'s top five on a BCI photo, '
            f'is indistinguishable here from one it truly cannot return. The five-candidate '
            f'cap is what hides the difference. It did not bite everywhere: on '
            f'{c.short5:,} of the {c.n_pred:,} frames with a cached answer '
            f'({pctf(c.short5 / c.n_pred)}) fewer than five candidates came back, so nothing '
            f'was cut off. On the other {c.n_pred - c.short5:,} the list was full, and '
            f'anything the model would have ranked sixth or lower is invisible to us. The way '
            f'to find out is to re-run the predictions asking for more candidates per photo. '
            f'More name cleaning will not help, because names are already matched as well as '
            f'they can be.</div>'
            + table([("Species", False), ("Labelled frames", True)],
                    [[f'<span class="sp">{esc(cap(d["species"]))}</span>',
                      f'{d["n_labelled_crowns"]:,}'] for d in c.never])
            + f'<p class="note"><strong>Spelling and renamed species are not costing us '
              f'anything.</strong> Labels and predictions are put into the same standard form '
              f'before they are compared, and old names are resolved to current ones. Scoring '
              f'the raw names instead would give {pctf(c.strict1 / n)} rather than '
              f'{pctf(c.c1 / n)} on the centre crop, so that matching is worth '
              f'{100 * (c.c1 - c.strict1) / n:+.2f} points, or {c.c1 - c.strict1} frames. '
              f'Treat it as a gain already banked, not as a source of error.</p>'
              f'<p class="note"><strong>{gn:,} further frames carry only a genus '
              f'name</strong> and are left out of every species number above. Scored at '
              f'genus level they reach {pctf(c.gg1 / gn) if gn else "n/a"}. Of them, '
              f'{c.gen_any:,} have at least one candidate in the right genus among the five, '
              f'and <strong>{c.gen_one:,} have exactly one</strong>. That turns the question '
              f'into a yes or no rather than an identification. Whether taking them down to '
              f'species is worth expert time is a prioritisation question, not a model '
              f'question.</p>'
              f'<p class="note">A further {c.fam_n} frames are labelled to '
              f'{c.fam_names} <em>families</em> rather than genera. They are left out of '
              f'the genus rate above, and offline we cannot score them at all. A family name '
              f'can never match a predicted species name. Rolling the predictions up to '
              f'family would need a list of which family every Pl@ntNet name belongs to, and '
              f'we do not have one here. Counting them in would have reported '
              f'{pctf(c.gg1 / (gn + c.fam_n))} instead of {pctf(c.gg1 / gn)}.</p>')
    return panel(f"What labelling cannot fix: {len(c.never)} species, {c.never_crowns} frames "
                 f"the model never named, and why the five-candidate cap may be the cause",
                 "<b>Do not spend expert time renaming or relabelling these.</b> Either "
                 "the model cannot return the species, or we never asked for enough "
                 "candidates to find out. Only re-running the predictions can tell the two "
                 "apart.", body)


# Quoted, not summarised, from bci-dashboard-docs/hypothesis.md. Both
# amendments say in their own text that the writeup must carry these words
# rather than a paraphrase, so they are stored as literals and rendered whole.
# If either changes there, change it here in the same session.
A2_PRIOR_EXPOSURE = (
    "<p>What that does and does not undermine:</p><ul>"
    "<li><strong>The tiles arm is blind.</strong> Condition 4 excludes every frame with a "
    "quadrat result, so no frame in this sample has ever been scored in that arm.</li>"
    "<li><strong>The frame-level aggregation is new.</strong> The area-weighted crown vote "
    "defined above has never been computed on any sample. What was reported earlier was a "
    "per-crown top-1 accuracy of 85.4% over the whole corpus, on a different unit and a "
    "different population.</li>"
    "<li><strong>The sample is new.</strong> These 300 frames were not chosen by looking at "
    "crown results.</li>"
    "<li><strong>But the number was not generated blind.</strong> An operator has seen "
    "crown-arm accuracy, at another unit and on a wider population, before this freeze.</li>"
    "</ul><p>The writeup must say this in those words. The crown arm's own accuracy "
    "carries a prior-exposure caveat. The paired comparison and the tiles arm do not.</p>")

A4_WHAT_THIS_COSTS = (
    "<p><strong>What this costs, stated plainly.</strong> The arm was dropped after its "
    "interim number had been seen, and no amount of reasoning removes that ordering. The two "
    "reasons above are structural and were both knowable on 2026-08-26, before A3. They were "
    "not acted on then. A reader is entitled to weigh that, and the writeup must carry this "
    "paragraph, not a summary of it.</p>")


def p_confirmatory(c):
    """The frozen read behind the headline: what was measured, and on what.

    Separate from the method panel because nothing here comes from the snapshot:
    it is a one-time read of frames fixed before the data existed, and a reader
    who mixes it with the whole-corpus numbers will report a rate on a set of
    frames that was never measured. Closed, like the two panels beside it: a
    reader arrives to look something up, not to read a method, and an open
    method panel put a paragraph about resampling between them and the page.
    What the reader must not miss is the line above the band, which says to
    carry the warnings, and the summary of the panel that holds them.
    """
    cf = c.cf
    if cf is None:
        raise SystemExit("p_confirmatory needs the frozen result; see confirmatory_hero")
    body = (
        f'<p class="note"><strong>What we did to each frame.</strong> For the top number we '
        f'sent Pl@ntNet every tree crown a botanist had outlined, one at a time. Then we '
        f'combined the answers into a single name for the frame. Each crown got a say in '
        f'proportion to how much of the frame it covered. So the number says what naming '
        f'costs once someone has already found the trees. It is not what a fully automatic '
        f'pipeline would score. For the second number we sent one fixed square from the '
        f'middle of the frame, {CROP_SIZE} px across, which is {CROP_SHARE} of the '
        f'frame&rsquo;s area.</p>'
        f'<p class="note"><strong>Which frames, and how many.</strong> '
        f'{int(cf["n_frames"])} frames from {int(cf["n_sites"])} sites and '
        f'{int(cf["n_days"])} flight days, set aside before any of these numbers existed. '
        f'Both ways of asking were run on every one of them: {int(cf["crown_n"])} frames '
        f'each. The two rates therefore come from the same frames and can be compared '
        f'directly.</p>'
        f'<p class="note"><strong>Where the range comes from.</strong> Frames shot at the '
        f'same site look alike, so treating them as {int(cf["n_frames"])} independent tries '
        f'would make us look surer than we are. Instead we re-ran the whole count '
        f'{int(cf["bootstrap_draws"]):,} times. Each time we drew {int(cf["n_sites"])} whole '
        f'sites at random, allowing repeats, and kept the middle 95% of the answers. That '
        f'is the range on each card above.</p>')
    return panel(
        'Where these two numbers come from, and what we did to each frame',
        "<b>Do not quote the top number without the warning below it.</b> It is a real "
        "number, measured on frames that were fixed before anyone looked. But someone on "
        "the team had already seen a result from that method, elsewhere, before the frames "
        "were fixed.", body,
        # The id is linked to from the four-rate panel and pinned by a test, so it
        # outlives the wording of the summary above it.
        anchor="where-the-headline-comes-from")


def p_caveats(c):
    """The two caveats the design requires, quoted, plus what the rate is not.

    Split out of ``p_confirmatory`` so the open panel above stays one screen. The
    two amendment blocks are reproduced character-for-character from
    ``hypothesis.md``, which requires the words rather than a summary.
    """
    cf = c.cf
    if cf is None:
        raise SystemExit("p_caveats needs the frozen result; see confirmatory_hero")
    d, lo, hi = (cf["crown_minus_photo"], cf["crown_minus_photo_site_lo"],
                 cf["crown_minus_photo_site_hi"])
    body = (
        f'<p class="note"><strong>The gap between the two numbers is the finding, not '
        f'either number on its own.</strong> Outlining the trees first is worth '
        f'{100 * d:+.1f} points over sending the middle of the frame. We are 95% sure the '
        f'true gain is between {100 * lo:+.1f} and {100 * hi:+.1f} points. On '
        f'{int(cf["crown_only_hits"])} frames outlining got the name right where the centre '
        f'crop got it wrong; on {int(cf["photo_only_hits"])} it went the other way. A gap '
        f'that lopsided almost never happens by chance, so we are confident it is real.</p>'
        f'<p class="note">For the record, the two tests the plan named. The site-aware '
        f'resampling test, the one described above, gives '
        f'p {pfmt(cf["p_cluster_bootstrap"], cf["bootstrap_draws"])}. A <b>p</b> is the '
        f'chance of seeing a gap at least this big if outlining made no difference at all. '
        f'A smaller p means a result less easily explained by luck. The other test named '
        f'in the plan, an exact McNemar test, '
        f'gives p = {cf["p_mcnemar_exact"]:.5f}. McNemar assumes every frame is independent '
        f'of every other, and frames from one site are not. So the plan named the resampling '
        f'test as the answer where the two disagree. For contrast, the ordinary textbook '
        f'range for the top number would read '
        f'{pctf(cf["crown_top1_wilson_lo"])} to {pctf(cf["crown_top1_wilson_hi"])}. It '
        f'assumes every frame is independent, so it is narrower than the data supports. '
        f'The two cards at the top of the page carry the site-resampled range instead.</p>'
        f'<div class="warn"><p><strong>The top number was not produced blind.</strong> '
        f'Before these frames were set aside, someone on the team had already seen how well '
        f'the outline-first method scored, on a different set of photos. That does not make '
        f'the number wrong and it does not touch the gap above, but the number has to travel '
        f'with this warning. The plan&rsquo;s own wording is below in full, from amendment '
        f'A2 of <code>hypothesis.md</code>. '
        f'Two of its words are the plan&rsquo;s, not this page&rsquo;s: <b>tiles</b> is the '
        f'third way of asking, the one that was cut, and a <b>quadrat</b> is a marked-out '
        f'ground plot. The 85.4% it names is a per-crown rate over every labelled photo. '
        f'Do not read it against the {pctf(cf["crown_top1"])} at the top, which scores a '
        f'whole frame on this fixed sample.</p>'
        f'{A2_PRIOR_EXPOSURE}</div>'
        f'<div class="warn"><p><strong>A third way of asking was dropped after we had seen '
        f'how it was doing.</strong> The study planned to test a third method, tiles, and '
        f'cut it partway through. Dropping a method after glimpsing its result is the kind '
        f'of choice that can flatter the methods that survive. Amendment A4, in full:</p>'
        f'{A4_WHAT_THIS_COSTS}</div>'
        f'<div class="warn"><p><strong>What this rate is not.</strong></p><ul>'
        f'<li><strong>It does not measure a fully automatic pipeline.</strong> The '
        f'outline-first method is handed the botanist&rsquo;s outlines and asked only to '
        f'name what is inside them. The method that would have answered the question with no '
        f'outlines at all, tiles, is the one that was dropped. Read '
        f'{pctf(cf["crown_top1"])} as the cost of naming once the trees have been found.</li>'
        f'<li><strong>It is per frame, not per species.</strong> The sample carries '
        f'{int(cf["n_species"])} species, and the two commonest species are '
        f'{pctf(cf["top2_species_share"])} of its {int(cf["n_frames"])} frames. So this '
        f'rate is weighted '
        f'towards the species the model already knows best. That is the same objection this '
        f'page makes to the {pctf(c.now["micro_top1"])} figure below, and it applies here '
        f'too. No per-species average for this sample was written into the plan, so none is '
        f'published.</li>'
        f'<li><strong>It is one camera, and not every site.</strong> Every frame '
        f'was shot with {cam_phrase(cf["cameras"])}, at {int(cf["n_sites"])} of '
        f'the 17 field sites. The drone carries a second camera, and no mission in '
        f'this design flies both, so nothing here says how the model reads that one.'
        f'</li></ul></div>'
        f'<p class="note">Every rule behind these numbers was written down in '
        f'<code>bci-dashboard-docs/hypothesis.md</code> before the data existed. That means '
        f'which frames, which test, what counts as right, and when we were allowed to look. '
        f'The '
        f'plan allows one look at the finished set, so this page prints the result the '
        f'scorer wrote that once and never recomputes it.</p>')
    return panel(
        'Two warnings that must travel with the top number, and what it does not measure',
        "<b>Quoted, not summarised.</b> The grey blocks are the plan&rsquo;s own words, "
        "copied rather than reworded.", body,
        anchor="two-warnings")


def p_terms(c):
    """The vocabulary every number on the page rests on.

    A panel rather than a paragraph under the headline: it is definitional, so a
    reader who already has the vocabulary should not have to read past it, and a
    reader who does not can open it once.
    """
    return panel(
        'What the words mean: frame, label, crown, centre crop',
        "<b>Four words do all the work on this page.</b> Which part of a "
        "photo was scored, and against which label, is the whole of the difference "
        "between the two numbers above.",
        f'<p>{hero_terms(c.n_cand)}</p>')


def p_candidates(c):
    return candidates_panel(recs=c.sp_recs + c.h.genus_recs, n_scored=c.n,
                            gen_n=c.gn, gen_none=c.gen_none)


def p_weighting(c):
    # The four corpus rates and everything that qualifies them, moved off the head of
    # the page into the one panel that explains them. The grid reuses the headline
    # card markup, so a reader meets the same shape twice and no new CSS exists.
    corpus = (
        hero([(averaged, pctf(c.now[metric]), question.format(k=c.n_cand),
               note.format(n_sp=c.n_sp, k=c.n_cand))
              for metric, question, averaged, note in HEADLINES])
        + f'<p class="caveat">{hero_region(c)}</p>'
        + f'<p class="note">{HERO_READING}</p>'
        # One sentence, not the full caveat: the ceiling panel states the same numbers
        # with the reasoning, and twice made this the second dense paragraph up top.
        + f'<p class="note"><strong>{c.unscoreable:,} of these frames belong to '
          f'{len(c.never)} species the model never names in five candidates, so they are '
          f'counted wrong however the score is cut.</strong> Without them the per-frame rate is '
          f'{pctf(c.reach1)}. <a href="#what-this-cannot-tell-you">What this cannot tell '
          f'you</a> says why that is a limit of the question we asked, not proof the '
          f'model has never heard of them.</p>')
    return weighting_panel(per_species=c.per_species, sp_recs=c.sp_recs, support=c.support,
                           buckets=c.buckets, now=c.now, n=c.n, n_sp=c.n_sp,
                           corpus_block=corpus)


def p_method(c):
    if c.checks is None:
        raise SystemExit("the method panel reports the build's own verification lines, so "
                         "the page must run verify_snapshot and set ctx.checks before "
                         "rendering it.")
    return method_panel(tag=c.tag, n=c.n, n_sp=c.n_sp, n_cand=c.n_cand, checks=c.checks)


# ---------------------------------------------------------------------------
# The registry: which section a panel belongs to, and which page carries it.
# ---------------------------------------------------------------------------

# section key -> (heading, the one orienting line under it).
SECTIONS = {
    # The headline band has no heading of its own: it sits directly under the cards
    # and belongs to them. render() emits its panels bare when the title is None.
    "headline": (None, None),
    "label-first": (
        "What to label first",
        "Which frames to send, which can wait, and the evidence behind the wait rule."),
    "model-health": (
        "How Pl@ntNet is doing against the labels",
        # No live figure in a lede: SECTIONS is a constant, so a number written
        # here would not move with the snapshot and nothing would catch it.
        "Which species it handles well, and which labels look worth a second look. "
        "Also why two fair ways of averaging the same frames disagree."),
    "limits": (
        "What this cannot tell you",
        "The ceilings on every number above."),
}

# panel id -> (section key, builder). A panel belongs to the goal it serves, so
# the confidence evidence sits with the queue rule it justifies and the species
# lookup sits with the scores it reports.
PANELS = {
    "confirmatory": ("headline", p_confirmatory),
    "caveats": ("headline", p_caveats),
    "terms": ("headline", p_terms),
    "todo": ("label-first", p_todo),
    "send": ("label-first", p_send),
    "wait": ("label-first", p_wait),
    "rules": ("label-first", p_rules),
    "conf": ("label-first", p_conf),
    "weighting": ("model-health", p_weighting),
    "labels": ("model-health", p_labels),
    "species": ("model-health", p_species),
    "review": ("model-health", p_review),
    "candidates": ("limits", p_candidates),
    "ceiling": ("limits", p_ceiling),
    "method": ("limits", p_method),
}

# The 2026-08-27 split. Internal is the labelling team's tool and stays thin;
# its real deliverable is send_batches.csv. External is what leaves the lab, and
# the confident disagreements go with it so they can be worked in Labelbox.
INTERNAL_PANELS = ("todo", "send", "wait", "rules", "conf")
# Order inside a section is the order these ids are listed in. A reader arrives to
# look up a species, so the lookup comes before the averaging argument.
# "terms" leads: frame, crown, label and centre crop are load-bearing from the
# first card down, and a reader who met them third had already been through two
# sections that used them.
EXTERNAL_PANELS = ("terms", "confirmatory", "caveats", "species", "review",
                   "weighting", "labels", "candidates", "ceiling", "method")

if set(INTERNAL_PANELS) | set(EXTERNAL_PANELS) != set(PANELS):
    raise SystemExit(f"every panel belongs to a page: "
                     f"{sorted(set(PANELS) - set(INTERNAL_PANELS) - set(EXTERNAL_PANELS))} "
                     f"belongs to neither")


def render(c, ids) -> str:
    """The chosen panels, grouped into their sections, in SECTIONS order.

    A section with no chosen panel is not emitted at all, so a page never shows
    a heading and a jump list over nothing.
    """
    unknown = [i for i in ids if i not in PANELS]
    if unknown:
        raise SystemExit(f"no such panel: {unknown}. Known: {sorted(PANELS)}")
    out = []
    for key, (title, lede) in SECTIONS.items():
        chosen = [PANELS[i][1](c) for i in ids if PANELS[i][0] == key]
        if not chosen:
            continue
        body = "\n".join(chosen)
        # A titleless section is the headline band: its panels belong to the cards
        # above them, so wrapping them in a heading would announce a second subject.
        out.append(body if title is None else section(title, lede, body))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The bits of a page that are not a panel: the command line, the document
# wrapper, and writing the file. Both pages do these identically, and a second
# copy is a second place for the verify flags to drift.
# ---------------------------------------------------------------------------

def parse_args(doc: str, default_out: str):
    """The builder command line. Same flags on both pages, different --out."""
    import argparse

    ap = argparse.ArgumentParser(description=doc)
    ap.add_argument("--gt", default=hc.GT_CSV)
    ap.add_argument("--splits", default=hc.SPLITS_CSV)
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument("--verify-against", default=None,
                    help="directory holding the committed measurement CSVs to cross-check; "
                         "defaults to the newest model-health-<date>/ folder")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "build", default_out))
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    return ap.parse_args()


def document(title: str, body: str) -> str:
    """One self-contained file: every style and script inlined, nothing fetched.

    No footer: the subtitle already carries the build date, the snapshot and the
    model tag, and a second copy at the foot said nothing new.
    """
    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title>"
            f"<style>{CSS}</style></head><body>" + body
            + f"<script>{JS}</script></body></html>")


def write_page(page: str, checks, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # Encoded here so the reported size is the size on disk: accented species names
    # cost more than a byte each, and len(page) undercounts by ten.
    blob = page.encode("utf-8")
    with open(out, "wb") as f:
        f.write(blob)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {out}  ({len(blob):,} bytes)")
