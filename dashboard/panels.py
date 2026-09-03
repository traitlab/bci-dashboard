"""The model-health page's panels: one function per collapsible block.

Each takes the figure namespace and returns HTML. A panel reads a figure, it
never computes one: the arithmetic is in ``figures.py``, the status vocabulary
in ``status_words.py``, the other pages' panels in ``queue_panels.py`` and
``confirmatory_panels.py``, and which page carries which panel in ``page.py``.
"""

from __future__ import annotations

import core as hc
from assets import (cap, esc, filterable_table, hero, num_cell, panel, pctf,
                    status_legend, status_tag, table)
from crop_overlap import CROP_SIZE, FRAME_H, FRAME_W
from explain import method_panel, weighting_panel
from figures import conf, top1
from status_words import (STATUS, filter_options, legend_entries,
                          status_precedence_note)

# Read, not worked through, so shorter than the queue page's send preview.
REVIEW_PREVIEW = 15


# What each file naming is, as a noun phrase both pages drop into their own
# sentence. Both words read like camera settings and neither is one: the flight
# team confirmed one camera throughout, and the flights that produced
# <code>tele</code> names produced <code>zoom</code> ones too. A reader who does
# not know that reads a lens difference into every count split this way, so it
# is said outright, and said once.
NAMING_IS = {
    "zoom": "the earlier file naming <code>zoom</code>",
    "tele": "the later file naming <code>tele</code>",
}

# Where the two namings come from, said once on each page that splits a count by
# them. Kept out of NAMING_IS so a sentence can name a naming without carrying
# the whole explanation every time.
NAMING_NOTE = ("Both words read like camera settings and neither is one. The flight "
               "team confirmed the naming changed and nothing else did. Every "
               "<code>tele</code> frame comes from one of four flights that also "
               "produced <code>zoom</code> frames.")

# The species table's lede, shared by the internal pages and the export-only one.
SPECIES_LOOKUP_LEDE = ("<b>Find a species you care about and read its status.</b> "
                       "Click any heading to sort, type to filter.")

# A 2x2 grid: question asked (rows) by how it was averaged (columns), as
# (metric, question, averaged over, note). The rates move with the corpus, so
# they are rendered from here rather than named.
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

# Sits under the grid. Without it the two columns read as a contradiction.
HERO_READING = "Read down a column, not across. Both rates are right."

# Which rate answers which question, one paragraph of its own. Which one to
# quote is said once, in the four-rates panel, not here: said in both places the
# two wordings contradicted each other.
HERO_WHICH_RATE = (
    "<b>Per species</b> asks how many kinds of tree the model can name, "
    "which is what a labelling programme moves. <b>Per frame</b> asks how often it is "
    "right on a photo picked at random, which the commonest species decide."
)

# Why the two differ, its own paragraph so a reader who only needs to know which
# rate to quote can stop before it.
HERO_WHY_DIFFER = (
    "Per frame is the higher of the two because the species with many frames "
    "are the ones Pl@ntNet already knows."
)

# Derived and formatted once so it cannot be printed at two different roundings.
CROP_SHARE = f"{100 * CROP_SIZE ** 2 / (FRAME_W * FRAME_H):.1f}%"

# What the centre crop is, as a noun phrase both panels that need it drop into
# their own sentence, so the one square cannot be written two ways.
CENTRE_CROP_IS = (f"the fixed {CROP_SIZE}&times;{CROP_SIZE} square from the middle of "
                  f"a frame, {CROP_SHARE} of the frame&rsquo;s area")

# What a reader has to know before any number on the page means anything.
def hero_terms(k):
    """The four words, and the request setting, in the wording the page uses.

    A list, not a paragraph, so looking up one word does not mean reading six.
    A function, not a constant: the number of names we ask for is a setting, and
    a setting frozen into prose stops being true unnoticed.
    """
    items = [
        f"A <b>frame</b> is one {FRAME_W}&times;{FRAME_H} drone photo.",
        "A <b>crown</b> is one tree canopy a botanist outlined inside a frame.",
        "A frame's <b>label</b> is the species whose outlined crowns cover the most "
        "area in the <i>whole</i> frame.",
        f"The <b>centre crop</b> is {CENTRE_CROP_IS}. Every "
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


# The two regions above are not the same one, and every figure below inherits
# the mismatch, so it is stated here rather than in a footnote.
def crop_mismatch(c):
    """The one sentence that says how far the crop and the label disagree.

    The four corpus rates and the species table both need it, so it is written
    once. Counted at build time, never a module constant: a constant goes stale
    against the wrong population.
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
        "<p>Read these four as a record of what the centre-crop "
        "path did, not as the model's accuracy.</p>"
    )


# ---------------------------------------------------------------------------
# Panels. One function per panel, each reading only the prepared context, so a
# page is a list of panel ids rather than interleaved rendering.
# ---------------------------------------------------------------------------


def p_review(c):
    """Labelled frames worth a second look, by species and by confusable pair."""
    pair_rows = sorted(c.review_pairs.items(), key=lambda kv: -len(kv[1]))[:10]
    # What a row on either table means comes before the tables themselves. The
    # pairs table's rows are pairs, not frames, and the ten shown do not cover
    # every frame, so the prose says how many they do cover.
    shown = sum(len(cs) for _, cs in pair_rows)
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
            f'which are also single-frame pairs above.</p>'
            + table([("botanist label", False), ("Pl@ntNet's first guess", False),
                   ("frames", True), ("mean confidence", True)],
                  [[f'<span class="sp">{esc(cap(gt))}</span>',
                    f'<span class="sp">{esc(cap(pr))}</span>',
                    f"{len(cs):,}", f"{sum(cs) / len(cs):.2f}"]
                   for (gt, pr), cs in pair_rows])
            if pair_rows else '<p class="note">None at this confidence.</p>')
    # Most confident first, linked into Labelbox only where a merge recorded the
    # data row. Never guessed, never fetched.
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
    body += ('<p class="note">Not urgent: work this list after the queues on the label '
             'queue page. A '
             'label-and-guess pair that keeps recurring is a signal about the species, '
             'not just the photo.</p>')
    if c.n_adjudicated:
        body += (f'<p class="note">{c.n_adjudicated} further frame'
                 f'{"" if c.n_adjudicated == 1 else "s"} disagree at this confidence and are '
                 f'not listed: a botanist has confirmed the label, so the model is simply '
                 f'wrong there and the frame would return here on every build. They still '
                 f'count against the {pctf(c.confident_ok)} above.</p>')
    return panel(f"Labels worth a second look: {c.review_counts[0]} confident "
                 f"disagreements a botanist can settle",
                 f"<b>Put these {c.review_counts[0]} frames in front of a botanist.</b> "
                 f"Either the label is wrong or the model is, and one look settles "
                 f"which. They are the disagreements most worth an expert's minute. "
                 f"All of them are in "
                 f'<a href="label_review_queue.csv">label_review_queue.csv</a>, '
                 f"most confident first.", body)


# The rows that start hidden are exactly the ones the page already calls "too
# few labels to judge", so this is hc.WELL_SAMPLED_MIN_N and not a second
# threshold: hiding at 5 while the status beside it switches at 10 sends a reader
# hunting for a rule that was never there. Hidden, never deleted.
THIN_MIN_FRAMES = hc.WELL_SAMPLED_MIN_N


def _starts_hidden(d, status):
    """A row starts hidden when its rate is too thin to read.

    "Never returned on any BCI photo" is exempt: it is the page's most actionable
    status, it does not depend on the rate being readable, and hiding it would
    leave the legend describing a status no visible row carries.
    """
    return status != "unreachable" and d["n_labelled_frames"] < THIN_MIN_FRAMES


def p_species(c):
    """One row per species, so a reader can look up the tree they care about
    instead of taking the corpus average on trust."""
    sp_rows, attrs = [], []
    for d in c.per_species:
        sp, st = d["species"], c.status[d["species"]]
        sp_rows.append([
            esc(cap(sp)),
            num_cell(d["n_labelled_frames"], f'{d["n_labelled_frames"]:,}'),
            num_cell(d["top1_accuracy"], pctf(d["top1_accuracy"])),
            num_cell(d["top5_accuracy"], pctf(d["top5_accuracy"])),
            num_cell(d["mean_top1_confidence"],
                     f'{d["mean_top1_confidence"]:.2f}'),
            status_tag(st, STATUS[st][0])])
        # No data-status: the row's status tag carries it and the filter reads
        # it from there, rather than 4KB of markup saying it twice.
        attrs.append(' data-thin="1"' if _starts_hidden(d, st) else "")
    # Counted off the marks just made, so the prose below cannot name a
    # different number from the table.
    n_thin = sum(1 for a in attrs if a)
    # Three paragraphs before the table: how to work it, how a status is chosen,
    # and what the rates are scored on. The counts themselves stay in the head
    # panel, which says them once.
    body = ('<p class="note"><b>Every rate here is scored on the fixed centre square, '
            'not on outlined crowns.</b> So a low rate can mean the crop missed the tree '
            'rather than that the model missed the name. Read a row as a flag for a '
            'second look, not as that species&rsquo; identification accuracy.</p>'
            + status_legend(legend_entries())
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
            + '<p class="note"><b>Model&rsquo;s confidence</b> is Pl@ntNet&rsquo;s own '
              'score for its first guess, averaged over that species&rsquo; frames. '
              'Pl@ntNet spreads 100% of its confidence across every species it '
              'knows. So 0.86 means it put nearly all of that on one '
              'name, and 0.32 means it was spread thin.</p>'
            + filterable_table(
        [("Species", False), ("Labelled frames", True),
         ("First guess right", True), ("Right name in the list", True),
         ("Model's confidence", True), ("Status", False)],
        sp_rows,
        options=filter_options(),
        row_attrs=attrs,
        thin_label=f"show all {c.n_sp}",
    ))
    # The colon stays, since slug() cuts there and the anchor keeps its old value.
    # The species count was in this summary and is gone: a reader deciding whether
    # to open a lookup table does not need the size of the table, and the number
    # made the one header on this page that answers nothing change every snapshot.
    # Closed, because this is a lookup tool rather than the page's deliverable.
    return panel("Look up one species: sortable and filterable",
                 SPECIES_LOOKUP_LEDE, body)


def p_ceiling(c):
    """What the headline rate cannot reach: frames whose species never appeared
    in any answer the model gave us, counted three ways over three populations.

    Split in two when a checklist is on disk: species proven absent from
    Pl@ntNet's own list, and species that simply never ranked in a sample of
    ``c.n_cand``. Falls back to one table and today's framing when it is not.
    """
    n, gn = c.n, c.gn

    def sp_table(rows):
        return table([("Species", False), ("Labelled frames", True)],
                     [[f'<span class="sp">{esc(cap(d["species"]))}</span>',
                       f'{d["n_labelled_frames"]:,}'] for d in rows])

    if c.has_checklist:
        scope_html = (
            f'<div class="warn"><strong>{c.out_of_scope_frames} of those '
            f'{c.never_frames} frames, on {len(c.out_of_scope)} species, are proven '
            f'absent from Pl@ntNet’s own '
            f'species list for this project.</strong> No re-run can return a name the '
            f'project does not carry. Do not spend expert time renaming or relabelling '
            f'these.</div>'
            + sp_table(c.out_of_scope)
            + f'<p class="note"><strong>The other {c.unproven_absent_frames} frames, '
            f'on {len(c.unproven_absent)} species, are on the project’s list but never '
            f'ranked in a sample of {c.n_cand} candidates per photo.</strong> That is not '
            f'proof the model cannot return them, only that we never asked for enough '
            f'candidates to find out. Re-running with a larger candidate count could '
            f'still recover some of these.</p>'
            + sp_table(c.unproven_absent))
    else:
        scope_html = (
            f'<div class="warn"><strong>This is a limit of the question we asked, not proof '
            f'the model has never heard of these species.</strong> Offline we can only check '
            f'whether a name turns up in the cached answers, and we asked for '
            f'{c.n_cand} candidates per photo. A species Pl@ntNet knows well, but which '
            f'never made a list of {c.n_cand} on a BCI photo, looks exactly like one it '
            f'cannot return. Do not spend expert time renaming or relabelling these; only a '
            f'checklist from predict/fetch_checklist.py or a re-run can tell the two apart.'
            f'</div>'
            + sp_table(c.never))

    body = (f'<p class="note"><strong>Those {c.never_frames} frames are '
            f'{pctf(c.never_frames / n)} of the {n:,} evaluated, and no answer the model '
            f'gave us named their species.</strong> Leaving them out raises the per-frame rate from {pctf(c.c1 / n)} to '
            f'{pctf(c.reach1)} on {len(c.reach):,} centre crops.</p>'
            f'<p class="note">A wider count uses every one of the {len(c.h.gt_rows):,} '
            f'frames carrying a botanist label, genus-only frames and the few with no '
            f'cached answer included. On that set {c.never_all} frames carry a name the '
            f'model never returned to us.</p>'
            + scope_html
            + f'<p class="note">The cap did not bite everywhere. On {c.short5:,} of the '
            f'{c.n_pred:,} frames with a cached answer ({pctf(c.short5 / c.n_pred)}) fewer '
            f'than {c.n_cand} came back, so nothing was cut off. On the other '
            f'{c.n_pred - c.short5:,} anything ranked {c.n_cand + 1} or lower is invisible '
            f'to us.</p>'
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
              f'right genus among the {c.n_cand}, and <strong>{c.gen_one:,} have exactly '
              f'one</strong>. That turns the question into a yes or no. Whether taking them '
              f'down to species is worth expert time is a question for the label queue '
              f'page, not a model question.</p>'
              f'<p class="note">A further {c.fam_n} frames are labelled to {c.fam_names} '
              f'<em>families</em> rather than genera, and are left out of the genus rate. A '
              f'family name can never match a predicted species name, and rolling the '
              f'predictions up to family needs a list we do not have here. Counting them in '
              f'would have reported {pctf(c.gg1 / (gn + c.fam_n))} instead of '
              f'{pctf(c.gg1 / gn)}.</p>')
    return panel(f"What labelling cannot fix: {len(c.never)} species, {c.never_frames} frames "
                 f"the model never named",
                 "<b>Most of these are not proof the model cannot return the species.</b> "
                 "A checklist from predict/fetch_checklist.py, when on disk, tells a proven "
                 "absence apart from one we simply never asked enough candidates to find.",
                 body)


def p_terms(c):
    """The vocabulary every number on the page rests on.

    A panel, not a paragraph: definitional, so a reader who has the vocabulary
    can skip it and one who does not can open it once.
    """
    return panel(
        'What the words mean: frame, label, crown, centre crop',
        "<b>Four words do all the work on this page.</b> Which part of a "
        "photo was scored, and against which label, is the whole of the difference "
        "between the two numbers above.",
        hero_terms(c.n_cand))


def headline_hero(c):
    """The page's two leading cards: the first-guess rate, both ways of averaging.

    Built from ``HEADLINES`` rather than typed here, so the cards and the
    four-rate grid in ``p_weighting`` cannot end up calling one number two
    things. The right-name-in-the-list rates stay in the grid: they are a
    ceiling on our own request, not a statement about the model.
    """
    return hero([(averaged, pctf(c.now[metric]), question.format(k=c.n_cand),
                  note.format(n_sp=c.n_sp, k=c.n_cand))
                 for metric, question, averaged, note in HEADLINES[:2]])


def p_weighting(c):
    # The four corpus rates and their qualifiers, in the one panel that explains
    # them. The grid reuses the headline card markup, so no new CSS exists.
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
    return method_panel(tag=c.tag, n=c.n, n_sp=c.n_sp, n_cand=c.n_cand, checks=c.checks,
                        out_of_scope=c.out_of_scope, out_of_scope_in_world=c.out_of_scope_in_world)


def p_counts(c):
    """Why the page prints three different frame counts.

    Closed, with the three numbers in its summary: the question only arises
    after meeting one count in one panel and a larger one in another. The counts
    are rendered rather than named here, since they move with the corpus.
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
