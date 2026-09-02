"""The model-health page's panels: one function per collapsible block.

Every function here takes the figure namespace and returns HTML. A panel reads
a figure, it never computes one -- the arithmetic is in ``figures.py``, the
shared status vocabulary in ``status_words.py``, the queue page's own panels in
``queue_panels.py``, and which page carries which panel in ``page.py``.
"""

from __future__ import annotations

import core as hc
from assets import (cap, esc, filterable_table, hero, num_cell, panel, pctf,
                    status_legend, status_tag, table)
from crop_overlap import CROP_SIZE, FRAME_H, FRAME_W
from explain import (CONFIDENCE_IS_SHARED, candidates_panel, method_panel,
                     weighting_panel)
from figures import (CONFIRMATORY_CSV, conf, top1)
from status_words import STATUS, STATUS_REASON, status_precedence_note

# The second-look list is read, not worked through, so it is shorter than the
# send preview (which belongs to the queue page, in queue_panels.py).
REVIEW_PREVIEW = 15



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
    "Read down a column, not across. Both rates are right, and they answer different "
    "questions."
)

# The two questions, one paragraph of their own: the sentence above says how to
# read the grid, and these say which rate answers which question. Which one to
# quote is said once, in the four-rates panel, and not here: saying it twice put
# "quote per frame for a photo off the drive" on the same page as "cite the
# per-species rate, never the per-frame one".
HERO_WHICH_RATE = (
    "<b>Per species</b> asks how many kinds of tree the model can name, "
    "which is what a labelling programme moves. <b>Per frame</b> asks how often it is "
    "right on a photo picked at random, which the commonest species decide."
)

# Why the two differ, kept out of the two above so the instruction and the
# explanation are separate paragraphs: a reader who only needs to know which
# rate to quote can stop before it.
HERO_WHY_DIFFER = (
    "Per frame is the higher of the two because the species with many frames "
    "are the ones Pl@ntNet already knows."
)

# The centre crop as a share of the frame, derived and formatted once so it cannot
# be printed at two different roundings.
CROP_SHARE = f"{100 * CROP_SIZE ** 2 / (FRAME_W * FRAME_H):.1f}%"

# What a reader has to know before any number on the page means anything. The
# crown sentence is here rather than beside the headline because the headline is
# the first thing on the page and a term defined under it is defined too late.
def hero_terms(k):
    """The four words, and the request setting, in the wording the page uses.

    A list, not a paragraph: six definitions run together made the first panel
    the densest block on the page, and looking up one word meant reading all
    six. A function, not a constant, because the number of names we ask for is
    a setting, and a setting frozen into prose stops being true unnoticed.
    """
    items = [
        f"A <b>frame</b> is one {FRAME_W}&times;{FRAME_H} drone photo.",
        "A <b>crown</b> is one tree canopy a botanist outlined inside a frame.",
        "A frame's <b>label</b> is the species whose outlined crowns cover the most "
        "area in the <i>whole</i> frame.",
        f"The <b>centre crop</b> is the fixed {CROP_SIZE}&times;{CROP_SIZE} square from "
        f"the middle of a frame, which is {CROP_SHARE} of the frame&rsquo;s area. Every "
        f"number below that covers all the labelled frames was scored on that square. "
        f"We ask Pl@ntNet for {k} "
        f"names per photo (<code>nb-results={k}</code>). That is our request setting, "
        f"not a limit of the model.",
        "The <b>first guess</b> is the top-ranked of those names, and <b>right</b> "
        "means it matches the frame's label.",
        "<b>Outlining the trees first</b> means something else. We ask Pl@ntNet about "
        "each crown on its own. Then we combine the answers into one name for the "
        "frame, weighted by how much of the frame each crown covers. That is the same "
        "rule the label itself is built from, which is why it is the fairer of the two "
        "numbers at the top.",
    ]
    return ('<ul class="terms">'
            + "".join(f"<li>{t}</li>" for t in items) + "</ul>")


# The two regions above are not the same region, and the numbers below compare
# across them. Stated here rather than in a footnote because every figure on
# this page inherits the mismatch.
def crop_mismatch(c):
    """The one sentence that says how far the crop and the label disagree.

    Two panels need it: the four corpus rates and the species table. It was
    written out twice, in different words, with the same two counts. Once here,
    so the two panels cannot drift apart and a reader who opens both is not
    told the same thing twice in two voices.

    Counted, never a module constant. It was a constant once, with the counts
    in the prose; they went stale and were measured over the wrong population,
    which is the failure the rest of this file avoids by recomputing every
    figure at build time.
    """
    return (f"The two are not always looking at the same tree. On {c.crop_half:,} of "
            f"{len(c.sp_recs):,} scored frames the labelled species covers less than half "
            f"the crop, and on {c.crop_none:,} it covers none of it.")


def hero_region(c):
    """The crop-versus-label mismatch, worded for the four corpus rates."""
    return (
        "<p><strong>These four numbers judge a centre crop against a label for the whole "
        f"frame.</strong> {crop_mismatch(c)} A wrong answer here is therefore not "
        "always a wrong identification.</p>"
        # The mismatch, then what to do about it, kept as two paragraphs rather than
        # one.
        "<p>Read these four as a record of what the centre-crop "
        "path did, not as the model's accuracy.</p>"
    )



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



def p_review(c):
    pair_rows = sorted(c.review_pairs.items(), key=lambda kv: -len(kv[1]))[:10]
    # What a row on either table means comes first, before the tables themselves,
    # so a reader is not left guessing what put a frame here.
    shown = sum(len(cs) for _, cs in pair_rows)
    # "Each row is a frame" was wrong for the pairs table, whose rows are pairs and
    # whose frames column reads 3, 2, 2, 1 -- and the ten rows shown cover 14 of the
    # 51 frames, so a reader who added the column went looking for the other 37.
    body = (f'<p class="note">Every frame counted here is a labelled frame where the '
            f'model is at least {hc.REVIEW_CONF:.1f} confident in a <em>different</em> '
            f'species. A first guess this confident is right {pctf(c.confident_ok)} of '
            f'the time in bulk ({c.confident_hits:,} of {len(c.confident):,}).</p>'
            f'<p class="note">A wrong label found this way is the cheapest label fix '
            f'available.</p>'
            f'<p class="note">The {c.review_counts[0]} frames fall into '
            f'{len(c.review_pairs)} label-and-guess pairs. The '
            f'{len(pair_rows)} commonest are first, and they cover {shown} of the '
            f'{c.review_counts[0]} frames. Then come the '
            f'{REVIEW_PREVIEW} individual frames the model is surest about, some of '
            f'which are also single-frame pairs above. All '
            f'{c.review_counts[0]} are in <code>label_review_queue.csv</code> in the '
            f'snapshot folder, most confident first.</p>'
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
    body += (f'<h3 class="sub">The {len(top_review)} most confident disagreements</h3>'
             f'<p class="note">A frame name links to its row in Labelbox where we know the '
             f'link: {linked} of {len(c.review)} frames here. We know it for the ones that '
             f'came in on an export these labels were merged from. The rest are listed '
             f'without a link rather than sent to a guessed address.</p>')
    body += table([("frame", False), ("botanist label", False),
                   ("Pl@ntNet's first guess", False), ("confidence", True)],
                  [[(f'<a href="{esc(urls[r["global_key"]])}" target="_blank" '
                     f'rel="noopener">{esc(r["global_key"])}</a>'
                     if r["global_key"] in urls else esc(r["global_key"])),
                    f'<span class="sp">{esc(cap(r["gt"]))}</span>',
                    f'<span class="sp">{esc(cap(top1(r)))}</span>',
                    f"{conf(r):.2f}"]
                   for r in top_review])
    # "label-and-guess pair" everywhere: the table above is introduced with that
    # phrase, and "confusion pair" was the same thing under a second name.
    body += ('<p class="note">Not urgent: work this list after the send-first queues. A '
             'label-and-guess pair that keeps recurring is a signal about the species, '
             'not just the photo.</p>')
    if c.n_adjudicated:
        body += (f'<p class="note">{c.n_adjudicated} further frame'
                 f'{"" if c.n_adjudicated == 1 else "s"} disagree at this confidence and are '
                 f'not listed: a botanist has confirmed the label, so the model is simply '
                 f'wrong there and the frame would return here on every build. They still '
                 f'count against the {pctf(c.confident_ok)} above.</p>')
    return panel(f"Labels worth a second look: {c.review_counts[0]} frames where Pl@ntNet "
                 f"confidently disagrees",
                 # No cross-page pointer here: this panel is on the model-health page,
                 # and the send queues are on the other one.
                 f"<b>Put these {c.review_counts[0]} frames in front of a botanist.</b> "
                 f"Either the label is wrong or the model is, and one look settles "
                 f"which. They are the disagreements most worth an expert's minute.", body)




# The rows that start hidden are exactly the ones the page already calls "too
# few labels to judge", so this is hc.WELL_SAMPLED_MIN_N and not a second
# threshold of its own: a table hiding rows at 5 while the status beside them
# switches at 10 makes a reader hunt for a rule that was never there. Those
# rows are not deleted -- a botanist looks up their own species by name -- they
# start hidden so the table opens on the rows that can be read.
THIN_MIN_FRAMES = hc.WELL_SAMPLED_MIN_N


def _starts_hidden(d, status):
    """A row starts hidden when its rate is too thin to read.

    "Never returned on any BCI photo" is exempt: it is the page's most actionable
    status, it does not depend on the rate being readable, and all but one of the
    species carrying it fall under the frame cut-off. Hiding them left the legend
    describing a status no visible row had.
    """
    return status != "unreachable" and d["n_labelled_crowns"] < THIN_MIN_FRAMES


def p_species(c):
    sp_rows, attrs = [], []
    for d in c.per_species:
        sp, st = d["species"], c.status[d["species"]]
        sp_rows.append([
            esc(cap(sp)),
            num_cell(d["n_labelled_crowns"], f'{d["n_labelled_crowns"]:,}'),
            num_cell(f'{d["top1_accuracy"]:.6f}', pctf(d["top1_accuracy"])),
            num_cell(f'{d["top5_accuracy"]:.6f}', pctf(d["top5_accuracy"])),
            num_cell(f'{d["mean_top1_confidence"]:.6f}',
                     f'{d["mean_top1_confidence"]:.2f}'),
            status_tag(st, STATUS[st][0])])
        attrs.append(f' data-status="{st}"'
                     + (' data-thin="1"' if _starts_hidden(d, st) else ""))
    n_thin = sum(1 for d in c.per_species
                 if _starts_hidden(d, c.status[d["species"]]))
    # Three things a reader needs before the table, kept as separate paragraphs:
    # how to work the table, how a status is chosen, and what the rates are
    # scored on.
    body = (f'<p class="note"><b>Every rate here is scored on the fixed centre square, '
            f'not on outlined crowns.</b> {crop_mismatch(c)}</p>'
            f'<p class="note">So a low rate can mean the crop missed the tree rather '
            f'than that the model missed the name. Read a row as a flag for a second look, '
            f'not as that species&rsquo; identification accuracy.</p>'
            + status_legend([(st, STATUS[st][0], STATUS_REASON[st]) for st in STATUS])
            + f'<p class="note">{status_precedence_note()}</p>'
            + f'<p class="note"><b>{n_thin} of these {c.n_sp} species start hidden.</b> '
              f'They carry fewer than {THIN_MIN_FRAMES} labelled frames each, the same '
              f'cut-off as the &ldquo;too few labels to judge&rdquo; status. On that few '
              f'frames a rate can only land on a handful of values, so it says little '
              f'about the model. Species the model never returned on any BCI photo stay '
              f'on screen however few frames they carry.</p>'
            + f'<p class="note">Hidden rows are still reachable: type a name, or pick a '
              f'status, and they appear. Tick <i>show all {c.n_sp}</i> to keep them all '
              f'on screen.</p>'
            + f'<p class="note"><b>Model&rsquo;s confidence</b> is Pl@ntNet&rsquo;s own '
              f'score for its first guess, averaged over that species&rsquo; frames. '
              f'{CONFIDENCE_IS_SHARED} So 0.86 means it put nearly all of that on one '
              f'name, and 0.32 means it was spread thin.</p>'
            + filterable_table(
        [("Species", False), ("Labelled frames", True),
         ("First guess right", True), ("Right name in the list", True),
         ("Model's confidence", True), ("Status", False)],
        sp_rows,
        options=[(k, v[0]) for k, v in STATUS.items()],
        row_attrs=attrs,
        thin_label=f"show all {c.n_sp}",
    ))
    # "all 186" read as a promise the open table breaks: rows start hidden.
    # "any of" is what stays true, since a typed name reaches a hidden row. The
    # colon stays: slug() cuts there, so the anchor keeps its old value.
    # Closed, unlike the two panels the queue page opens. Those are that page's
    # deliverable; this one is a lookup tool, and open it is 40% of the page's
    # words sitting fourth of nine, so the five panels below it were a long
    # scroll away. Closed, every heading is readable at once.
    return panel(f"Look up one species: any of the {c.n_sp}, sortable and filterable",
                 "<b>Find a species you care about and read its status.</b> Click any "
                 "heading to sort, type to filter.",
                 body)


def p_ceiling(c):
    n, gn = c.n, c.gn
    body = (f'<p class="note"><strong>{len(c.never)} species ({c.never_crowns} of the {n:,} '
            f'evaluated frames) never appear in any answer the model gave us.</strong> '
            f'Leaving them out raises the per-frame rate from {pctf(c.c1 / n)} to '
            f'{pctf(c.reach1)} on {len(c.reach):,} centre crops.</p>'
            f'<p class="note">A wider count uses every one of the {len(c.h.gt_rows):,} '
            f'frames carrying a botanist label, genus-only frames and the few with no '
            f'cached answer included. On that set {c.never_all} frames carry a name the '
            f'model never returned to us.</p>'
            f'<div class="warn"><strong>This is a limit of the question we asked, not proof '
            f'the model has never heard of these species.</strong> Offline we can only check '
            f'whether a name turns up in the cached answers, and we asked for five candidates '
            f'per photo. A species Pl@ntNet knows well, but which never made a top five on a '
            f'BCI photo, looks exactly like one it cannot return. The cap did not bite '
            f'everywhere: on {c.short5:,} of the {c.n_pred:,} frames with a cached answer '
            f'({pctf(c.short5 / c.n_pred)}) fewer than five came back, so nothing was cut '
            f'off. On the other {c.n_pred - c.short5:,} anything ranked sixth or lower is '
            f'invisible to us. More name cleaning will not help.</div>'
            + table([("Species", False), ("Labelled frames", True)],
                    [[f'<span class="sp">{esc(cap(d["species"]))}</span>',
                      f'{d["n_labelled_crowns"]:,}'] for d in c.never])
            + f'<p class="note"><strong>Spelling and renamed species do not cost us any '
              f'frames.</strong> Labels and predictions are put into the same standard form '
              f'before comparison, and old names are resolved to current ones. Raw names '
              f'would score {pctf(c.strict1 / n)} on the centre crop rather than '
              f'{pctf(c.c1 / n)}, so the matching wins {c.c1 - c.strict1} frames. Those '
              f'{c.c1 - c.strict1} are already inside every rate on this page.</p>'
              f'<p class="note"><strong>{gn:,} further frames carry only a genus '
              f'name</strong> and are left out of every species number above. Scored at '
              f'genus level they reach {pctf(c.gg1 / gn) if gn else "n/a"}.</p>'
              f'<p class="note">Of them, {c.gen_any:,} have at least one candidate in the '
              f'right genus among the five, and <strong>{c.gen_one:,} have exactly '
              f'one</strong>. That turns the question into a yes or no. Whether taking them '
              f'down to species is worth expert time is a prioritisation question, not a '
              f'model question.</p>'
              f'<p class="note">A further {c.fam_n} frames are labelled to {c.fam_names} '
              f'<em>families</em> rather than genera, and are left out of the genus rate. A '
              f'family name can never match a predicted species name, and rolling the '
              f'predictions up to family needs a list we do not have here. Counting them in '
              f'would have reported {pctf(c.gg1 / (gn + c.fam_n))} instead of '
              f'{pctf(c.gg1 / gn)}.</p>')
    # The cap clause is not on this title: the ask below already says the cap is
    # one of the two explanations, so the title only says what the panel is about.
    return panel(f"What labelling cannot fix: {len(c.never)} species, {c.never_crowns} frames "
                 f"the model never named",
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

    Separate from the method panel because nothing here comes from the
    snapshot: it is a one-time read of frames fixed before the data existed,
    and mixing it with the corpus numbers reports a rate on frames nobody
    measured. Closed, like its neighbours -- a reader arrives to look something
    up, not to read a method. What they must not miss is the line above the
    band telling them to carry the warnings.
    """
    cf = c.cf
    if cf is None:
        raise SystemExit("p_confirmatory needs the frozen result; see confirmatory_hero")
    body = (
        f'<p class="note"><strong>What we did for the top number.</strong> Every crown a '
        f'botanist had outlined, sent one at a time and combined into one name for the '
        f'frame, each crown weighted by how much of the frame it covered. So the number '
        f'says what naming '
        f'costs once someone has found the trees, not what a fully automatic pipeline '
        f'would score.</p>'
        f'<p class="note"><strong>What we did for the second number.</strong> We sent one '
        f'fixed square from the middle of the frame, {CROP_SIZE} px across, which is '
        f'{CROP_SHARE} of the frame&rsquo;s area. Nothing chose that square; it lands where '
        f'it lands.</p>'
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
        # A pointer, not a second copy of the warning: the next panel gives the
        # mechanism in full, and stating it twice made the pointer read as the
        # whole story.
        "<b>The top number is real but it was not produced blind.</b> It was measured on "
        "frames that were fixed before anyone looked.", body,
        # The id is linked to from the four-rate panel and pinned by a test, so it
        # outlives the wording of the summary above it.
        anchor="where-the-headline-comes-from")


def p_caveats(c):
    """The two caveats the design requires, quoted, plus what the rate is not.

    The amendment blocks are reproduced character-for-character from
    ``hypothesis.md``, which requires the words rather than a summary.
    """
    cf = c.cf
    if cf is None:
        raise SystemExit("p_caveats needs the frozen result; see confirmatory_hero")
    lo, hi = cf["crown_minus_photo_site_lo"], cf["crown_minus_photo_site_hi"]
    body = (
        # The gap itself is stated in the always-visible note above this panel.
        # Repeating it here said the same number twice within fifteen words, and
        # said it with a different name for the centre crop each time. This panel
        # adds the range, which is the part the note leaves out.
        f'<p class="note"><strong>The gap between the two numbers is the finding, not '
        f'either number on its own.</strong> We are 95% sure the true gain is between '
        f'{100 * lo:+.1f} and {100 * hi:+.1f} points.</p>'
        f'<p class="note">On '
        f'{int(cf["crown_only_hits"])} frames outlining got the name right where the centre '
        f'crop got it wrong; on {int(cf["photo_only_hits"])} it went the other way. A gap '
        f'that lopsided almost never happens by chance, so we are confident it is real.</p>'
        # "site-aware resampling" and "site-resampled" were the page's own words,
        # not the plan's, and nothing on the page said what they meant. Said as
        # what the test does instead.
        f'<p class="note">The plan named two tests. Re-drawing whole sites at random, '
        f'rather than single frames, gives p '
        f'{pfmt(cf["p_cluster_bootstrap"], cf["bootstrap_draws"])}; an exact McNemar test '
        f'gives p = {cf["p_mcnemar_exact"]:.5f}. A <b>p</b> is the chance of a gap at '
        f'least this big if outlining made no difference. Smaller means harder to explain '
        f'by luck. McNemar treats every frame as its own independent draw, and frames from '
        f'one site are not. So the plan named the re-drawing test as the answer where the '
        f'two disagree.</p>'
        # Its own paragraph: the range is a different claim from the two p-values,
        # not the same one restated.
        f'<p class="note">The ordinary textbook range for the top number would read '
        f'{pctf(cf["crown_top1_wilson_lo"])} to {pctf(cf["crown_top1_wilson_hi"])}. It '
        f'treats every frame as its own independent draw too, so it is narrower than the '
        f'data supports. The two cards at the top carry the whole-site range instead.</p>'
        f'<div class="warn"><p><strong>The top number was not produced blind.</strong> '
        f'Before these frames were set aside, someone on the team had already seen how well '
        f'the outline-first method scored, on a different set of photos. That does not make '
        f'the number wrong and it does not touch the gap above, but the number has to travel '
        f'with this warning.</p>'
        # The warning comes first, then the glossary key, then the quoted text --
        # kept in that order rather than run together.
        f'<p>Below in full is amendment A2 of <code>hypothesis.md</code>, in the '
        f'plan&rsquo;s words. Two of them are not this page&rsquo;s: <b>tiles</b> is a third '
        f'way of asking, cut partway through, and a <b>quadrat</b> is a marked-out ground '
        f'plot.</p>'
        # The plan's own "top-1" is left unglossed on purpose: the sentence below
        # says what its 85.4% counts, and repeating the term would put it in this
        # page's prose, which says "first guess" everywhere.
        f'<p>The 85.4% it names counts only a first guess, per crown, over every '
        f'labelled photo. '
        f'Do not read it against the {pctf(cf["crown_top1"])} at the top, which scores a '
        f'whole frame on this fixed sample.</p>'
        f'{A2_PRIOR_EXPOSURE}</div>'
        f'<div class="warn"><p><strong>Tiles, the third way of asking, was dropped after '
        f'we had seen how it was doing.</strong> Dropping a method after glimpsing its '
        f'result is the kind of choice that can flatter the methods that survive. The '
        f'plan&rsquo;s own wording, amendment A4, follows.</p>'
        f'{A4_WHAT_THIS_COSTS}</div>'
        f'<div class="warn"><p><strong>What this rate is not.</strong></p><ul>'
        f'<li><strong>It does not measure a fully automatic pipeline.</strong> The method '
        f'is handed the botanist&rsquo;s outlines and asked only to name what is inside '
        f'them. Tiles, which would have answered with no outlines at all, is the one that '
        f'was dropped. Read {pctf(cf["crown_top1"])} as the cost of naming trees already '
        f'found.</li>'
        f'<li><strong>It is per frame, not per species.</strong> The sample carries '
        f'{int(cf["n_species"])} species, and the two commonest are '
        f'{pctf(cf["top2_species_share"])} of its {int(cf["n_frames"])} frames. So the rate '
        f'leans towards what the model already knows best. That is this page&rsquo;s own '
        f'objection to the {pctf(c.now["micro_top1"])} figure below. The plan asked for no '
        f'per-species average here, so none is published.</li>'
        f'<li><strong>It is one camera, and not every site.</strong> Every frame '
        f'was shot with {cam_phrase(cf["cameras"])}, at {int(cf["n_sites"])} of '
        f'the 17 field sites. The drone carries a second camera, and no mission in '
        f'this design flies both, so nothing here says how the model reads that one.'
        f'</li></ul></div>'
        f'<p class="note">Every rule behind these numbers predates the data, written down '
        f'in <code>bci-dashboard-docs/hypothesis.md</code>. That is which frames, which '
        f'test, what counts as right, and when we were allowed to look. The plan allows one '
        f'look, so this page prints what the scorer wrote that once and never '
        f'recomputes it.</p>')
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
        hero_terms(c.n_cand))


def p_candidates(c):
    return candidates_panel(recs=c.sp_recs + c.h.genus_recs, n_scored=c.n,
                            gen_n=c.gn, gen_none=c.gen_none)


def p_weighting(c):
    # The four corpus rates and everything that qualifies them, in the one panel
    # that explains them. The grid reuses the headline card markup, so a reader
    # meets the same shape twice and no new CSS exists.
    corpus = (
        hero([(averaged, pctf(c.now[metric]), question.format(k=c.n_cand),
               note.format(n_sp=c.n_sp, k=c.n_cand))
              for metric, question, averaged, note in HEADLINES])
        + f'<div class="caveat">{hero_region(c)}</div>'
        + f'<p class="note">{HERO_READING}</p>'
        + f'<p class="note">{HERO_WHICH_RATE}</p>'
        + f'<p class="note">{HERO_WHY_DIFFER}</p>')
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


def p_counts(c):
    """Why the page prints three different frame counts.

    Was always-visible prose under the hero cards, and at 89 words it was a
    fifth of everything a reader saw before clicking. It answers a question
    nobody has yet on landing: it is what you want when you have met 3,277 in
    one panel and 3,749 in another and cannot tell whether the page contradicts
    itself. Closed, with the three numbers in the summary, it is there the
    moment that happens and costs nothing until then.
    """
    return panel(
        f"Why three different frame counts: {c.n:,}, {c.n_pred:,} and {c.n_gt:,}",
        "<b>They do not contradict each other.</b> Each counts a different thing.",
        f'<p class="note"><b>{c.n:,}</b> frames carry a label naming a species. Every '
        f'accuracy rate on this page is measured on those.</p>'
        f'<p class="note"><b>{c.n_pred:,}</b> frames have a cached Pl@ntNet answer: the '
        f'{c.n:,} above, plus {c.gn:,} labelled only to a genus and {c.fam_n:,} labelled '
        f'only to a family.</p>'
        f'<p class="note"><b>{c.n_gt:,}</b> frames a botanist has labelled at all, the '
        f'{c.n_gt - c.n_pred} with no cached answer included.</p>'
        f'<p class="note">Each number on this page says which of the three it is '
        f'using.</p>')
