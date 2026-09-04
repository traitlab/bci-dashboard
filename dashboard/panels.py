"""The model-health page's panels: one function per collapsible block.

Each takes the figure namespace and returns HTML. A panel reads a figure, it
never computes one: the arithmetic is in ``figures.py``, the status vocabulary
in ``status_words.py``, the other pages' panels in ``queue_panels.py`` and
``confirmatory_panels.py``, and which page carries which panel in ``page.py``.
"""

from __future__ import annotations

import core as hc
from assets import (cap, esc, filterable_table, hero, num_cell, panel, pctf,
                    source_note, status_legend, status_tag, svg_hbar, table)
from crop_overlap import CROP_SIZE, FRAME_H, FRAME_W
from explain import CONF_BAND_WORDS, method_panel, weighting_panel
from figures import conf, top1
from status_words import (STATUS, filter_options, legend_entries,
                          status_precedence_note)

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
# (metric, name, question, averaged over, note). The rates move with the corpus,
# so they are rendered from here rather than named.
#
# The name is the metric's own name and the question is the plain-English gloss
# under it. Until 2026-09-03 there was no name and the gloss was the label:
# CONTEXT.md banned "top-1" and "top-5" on a page outright, out of the
# 2026-09-01 plain-English pass. The reviewer asked for the names back on the call
# ("maybe it's actually simpler, just name the metric") and the user confirmed
# the reversal, so the ban is gone and the gloss stayed under the name.
# A botanist still reads the sentence; a PI stops having to translate it.
HEADLINES = [
    ("macro_top1", "Top-1 accuracy", "The first guess is right", "per species",
     "each of the {n_sp} species counts once, however few frames it has"),
    ("micro_top1", "Top-1 accuracy", "The first guess is right", "per frame",
     "one vote per labelled frame, so common species dominate"),
    ("macro_top5", "Top-{k} accuracy", "The right name is among the {k} requested",
     "per species",
     "the best we could do if a botanist picked the right name out of the {k} every "
     "time, so a ceiling on our {k}-name request, not on the model"),
    ("micro_top5", "Top-{k} accuracy", "The right name is among the {k} requested",
     "per frame",
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


def _review_pairs(review):
    """The review frames grouped by label-and-guess pair, recurring pairs first.

    ``figures._review`` already counts the pairs; it keeps confidences, not
    records, and a row on this table is a frame. Same key, so the two cannot
    disagree about how many pairs there are. Order is frames per pair and then
    the pair itself, so the pairs worth working first come first and the order
    does not move between builds.
    """
    groups: dict[tuple, list] = {}
    for r in review:
        groups.setdefault((r["gt"], top1(r)), []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda r: -conf(r))
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def _project_split(cov):
    """Where a table's links go, as a clause the link sentence drops in.

    Several projects hold these frames, because a frame was labelled wherever
    its flight was labelled, and a reader told only the total cannot check one
    link of each kind. Empty when there is nothing to split: one project, or
    none linked at all.
    """
    counts = sorted(cov["by_project"].values(), reverse=True)
    if len(counts) < 2:
        return ""
    if len(counts) == 2:
        return f", {counts[0]} in one Labelbox project and {counts[1]} in the other"
    # Past two, the list of counts stops being readable and the number a reader
    # can act on is how many projects they have to open.
    return (f", spread across {len(counts)} projects, "
            f"the largest holding {counts[0]}")


# The columns of the one review table, numeric flag second, as ``table`` takes
# them. Written once so the group heading's colspan cannot drift from them.
REVIEW_COLUMNS = [("botanist label", False), ("Pl@ntNet's first guess", False),
                  ("confidence", True), ("split", False), ("frame", False)]


def _review_table(groups, urls):
    """One table, every review frame, each pair a heading over its own frames.

    Not two tables: a pairs table capped at one number beside a frames table
    capped at another reads as two populations, and the pair a reader goes
    looking for is the one outside the first cap. A heading row inside the one
    table keeps the pair counts without a second denominator.
    """
    out = ["<table><thead><tr>"]
    for text, num in REVIEW_COLUMNS:
        cls = ' class="num"' if num else ""
        out.append(f"<th{cls}>{text}</th>")
    out.append("</tr></thead><tbody>")
    for (gt, pr), rows in groups:
        out.append(f'<tr><th colspan="{len(REVIEW_COLUMNS)}">'
                   f'<span class="sp">{esc(cap(gt))}</span> labelled, '
                   f'<span class="sp">{esc(cap(pr))}</span> guessed: {len(rows)} '
                   f'frame{"" if len(rows) == 1 else "s"}</th></tr>')
        for r in rows:
            key = r["global_key"]
            frame = (f'<a href="{esc(urls[key])}" target="_blank" rel="noopener">'
                     f'{esc(key)}</a>') if key in urls else esc(key)
            out.append(f'<tr><td><span class="sp">{esc(cap(r["gt"]))}</span></td>'
                       f'<td><span class="sp">{esc(cap(top1(r)))}</span></td>'
                       f'<td class="num">{conf(r):.2f}</td>'
                       f'<td>{esc(r["split"] or "unassigned")}</td>'
                       f'<td>{frame}</td></tr>')
    out.append("</tbody></table>")
    return ('<div class="tscroll">' + "\n".join(out) + "</div>"
            + source_note("label_review_queue.csv"))


def _link_note(here, wide):
    """Where the table's links go, and why the rest of the rows carry none.

    Not a limitation and not a broken link: a link is only shipped where a file
    on this machine states both halves of it, the project and the data row.
    Two files can, a project export and the dataset inventory, and a frame
    neither one names carries no link. The page-wide figure sits beside the
    table's own so a reader can see whether the shortfall is local.
    """
    out = (f'<p class="note">{here["n_linked"]} of {here["n_frames"]} frames link to '
           f'their row in Labelbox{_project_split(here)}.')
    if here["n_unlinked"]:
        out += (f' The other {here["n_unlinked"]} are not unlinkable. No file here '
                f'names both the project and the data row for them, and a link needs '
                f'both. Either a read-only export of their project or a paged read of '
                f'the dataset they sit in closes it.')
    return (out + f' The same join reaches {wide["n_linked"]:,} of '
                  f'{wide["n_frames"]:,} labelled frames page-wide '
                  f'({pctf(wide["share"])}).</p>')


def p_review(c):
    """Every labelled frame worth a second look, grouped by confusable pair."""
    groups = _review_pairs(c.review)
    n = len(c.review)
    # The pairs that recur, counted off the grouping itself so the sentence and
    # the headings cannot name different numbers.
    recur = [(p, rows) for p, rows in groups if len(rows) > 1]
    covered = sum(len(rows) for _, rows in recur)
    # Linked only where a merge recorded the data row. Never guessed, never
    # fetched. The page-wide figure is the same join over every labelled frame,
    # which is what says whether this table's shortfall is local or general.
    urls = hc.labelbox_urls()
    here = hc.labelbox_link_coverage([r["global_key"] for r in c.review], urls)
    wide = hc.labelbox_link_coverage([r["global_key"] for r in c.h.gt_rows], urls)
    body = (f'<p class="note">Every frame here is a labelled frame where the model is '
            f'at least {hc.REVIEW_CONF:.1f} confident in a <em>different</em> species. '
            f'A first guess this confident is right {pctf(c.confident_ok)} of the time '
            f'in bulk ({c.confident_hits:,} of {len(c.confident):,}). A wrong label '
            f'found this way is the cheapest label fix available.</p>'
            f'<p class="note">All {n} frames are here, grouped under their '
            f'{len(groups)} label-and-guess pairs, the pairs that recur first. '
            f'{len(recur)} pairs carry more than one frame and cover {covered} of the '
            f'{n} frames; the other {len(groups) - len(recur)} carry one frame '
            f'each.</p>'
            + _link_note(here, wide)
            + (_review_table(groups, urls) if groups
               else '<p class="note">None at this confidence.</p>')
            + '<p class="note">Not urgent: work this list after the queues on the label '
              'queue page. A label-and-guess pair that keeps recurring is a signal about '
              'the species, not just the photo.</p>')
    if c.n_adjudicated:
        body += (f'<p class="note">{c.n_adjudicated} further frame'
                 f'{"" if c.n_adjudicated == 1 else "s"} disagree at this confidence and '
                 f'are not listed: a botanist has confirmed the label, so the model is '
                 f'simply wrong there and the frame would return here on every build. '
                 f'They still count against the {pctf(c.confident_ok)} above.</p>')
    return panel(f"Labels worth a second look: {n} confident "
                 f"disagreements a botanist can settle",
                 f"<b>Put these {n} frames in front of a botanist.</b> "
                 f"Either the label is wrong or the model is, and one look settles "
                 f"which. They are the disagreements most worth an expert's minute. "
                 f"The same {n} rows are in "
                 f'<a href="label_review_queue.csv">label_review_queue.csv</a>, '
                 f"most confident first.", body)


# The rows that start hidden are exactly the ones the page already calls "too
# few labels to judge", so this is hc.WELL_SAMPLED_MIN_N and not a second
# threshold: hiding at 5 while the status beside it switches at 10 sends a reader
# hunting for a rule that was never there. Hidden, never deleted.
THIN_MIN_FRAMES = hc.WELL_SAMPLED_MIN_N


# The bars the reader can pick between. The reviewer, sorting the table by hand and
# counting rows out loud: "it would be nice to see how many are above 85 or
# something". Round numbers around that. The default is RELIABLE_MIN_TOP1
# because at that bar, over species carrying THIN_MIN_FRAMES or more labelled
# frames, the count is the "usually right" row count by construction, which is
# the one number on this control a test can check against something else.
THRESHOLD_BARS = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)
THRESHOLD_DEFAULT = hc.RELIABLE_MIN_TOP1
if THRESHOLD_DEFAULT not in THRESHOLD_BARS:
    raise SystemExit(f"the default bar {THRESHOLD_DEFAULT} is not one of "
                     f"{THRESHOLD_BARS}, so the select would open on no option")

# The two ids the control's own script looks up. Local to this file, unlike the
# species table's, which the shared script in style.py reaches for.
BAR_ID = "accuracy-bar"
BAR_COUNT_ID = "accuracy-bar-count"


def _clearing(per_species, bar):
    """Species carrying THIN_MIN_FRAMES or more labelled frames that score
    ``bar`` or better on the first guess.

    The same tolerance as ``core.diagnose``, so at RELIABLE_MIN_TOP1 this is
    exactly the count of rows tagged "usually right" rather than one rounding
    step away from it.
    """
    return sum(1 for d in per_species
               if d["n_labelled_frames"] >= THIN_MIN_FRAMES
               and d["top1_accuracy"] >= bar - hc.RATE_EPS)


def threshold_control(c):
    """How many species clear a bar, with the bar as a control.

    Sorting the table answers "which ones" and not "how many", which is what
    was asked for. The exclusion is in the sentence and not in a footnote: two
    support buckets hold most of the species and almost none of the crowns, and
    a species with one labelled frame scores 0% or 100% and nothing else, so an
    unqualified count is a misleading headline.

    Every count is rendered into the page, one per option, so the control needs
    no measurement at read time and the page stays one file.
    """
    thick = sum(1 for d in c.per_species
                if d["n_labelled_frames"] >= THIN_MIN_FRAMES)
    counts = {bar: _clearing(c.per_species, bar) for bar in THRESHOLD_BARS}
    opts = "".join(
        f'<option value="{bar:.2f}" data-n="{counts[bar]}"'
        f'{" selected" if bar == THRESHOLD_DEFAULT else ""}>'
        f'{100 * bar:g}%</option>' for bar in THRESHOLD_BARS)
    return (f'<p class="note">{thick} of {c.n_sp} species carry {THIN_MIN_FRAMES} '
            f'or more labelled frames. <b><span id="{BAR_COUNT_ID}">'
            f'{counts[THRESHOLD_DEFAULT]}</span> of those {thick}</b> are at or above '
            f'<select id="{BAR_ID}" aria-label="top-1 accuracy bar">{opts}</select> '
            f'top-1 accuracy. The other {c.n_sp - thick} species carry fewer frames than '
            f'that. On that few a rate lands on a handful of values, so they are left '
            f'out of this count.</p>'
            f'<script>(function(){{'
            f'var s=document.getElementById("{BAR_ID}"),'
            f'n=document.getElementById("{BAR_COUNT_ID}");'
            f's.addEventListener("change",function(){{'
            f'n.textContent=s.options[s.selectedIndex].getAttribute("data-n");}});'
            f'}})();</script>')


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
            num_cell(d["n_guessed_frames"], f'{d["n_guessed_frames"]:,}'),
            num_cell(d["precision"], pctf(d["precision"])),
            num_cell(d["f1"], pctf(d["f1"])),
            num_cell(d["mean_top1_confidence"],
                     f'{d["mean_top1_confidence"]:.2f}'),
            # Sorted on the width, shown as the range: a reader scanning for
            # species whose confidence is all over the place wants the width,
            # and a reader reading one row wants the two ends.
            num_cell(d["iqr_top1_confidence"],
                     f'{d["p25_top1_confidence"]:.2f} to {d["p75_top1_confidence"]:.2f}'),
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
              f'frames a rate lands on a handful of values: F1 on one labelled frame can '
              f'only be 0% or 100%. Species the model never returned stay on screen '
              f'however few frames they carry. Type a name or pick a status to reach a '
              f'hidden row, or tick <i>show all {c.n_sp}</i>.</p>'
            + '<p class="note"><b>Top-1 accuracy on a species row is that species&rsquo; '
              'recall</b>: of the frames a botanist labelled it, the share the first '
              'guess got right. <b>Precision</b> asks the reverse, over the frames the '
              'model guessed that name on, and is only countable where a botanist has '
              'labelled the frame. So it is precision over the frames we scored, not '
              'over the survey. <b>F1</b> is their harmonic mean, so a row scores well '
              'only when both do.</p>'
            + '<p class="note"><b>Model&rsquo;s confidence</b> is Pl@ntNet&rsquo;s own '
              'score for its first guess, averaged over that species&rsquo; frames. '
              'Pl@ntNet spreads 100% of it across every species it knows. So 0.86 means '
              'nearly all of that went on one name, and 0.32 means it was spread thin. '
              '<b>Middle half</b> is where the middle 50% of that species&rsquo; frames '
              'fall, the 25th to the 75th percentile. A mean of 0.60 over a middle half '
              'of 0.55 to 0.65 is a steady score. The same mean over 0.20 to 0.95 is two '
              'behaviours averaged into one number, and the column sorts on that '
              'width.</p>'
            + threshold_control(c)
            + filterable_table(
        # "(recall)" is in the header, not only in the paragraph above: a reader
        # scanning the columns found Precision and F1, no recall, and read that
        # as a missing column rather than as the one it shares a number with.
        [("Species", False), ("Labelled frames", True),
         ("Top-1 accuracy (recall)", True), (f"Top-{c.n_cand} accuracy", True),
         ("Frames guessed", True), ("Precision", True), ("F1", True),
         ("Model's confidence", True), ("Middle half", True), ("Status", False)],
        sp_rows,
        options=filter_options(),
        row_attrs=attrs,
        source="per_species_health.csv",
        thin_label=f"show all {c.n_sp}",
    ))
    # The colon stays, since slug() cuts there and the anchor keeps its old value.
    # The species count was in this summary and is gone: a reader deciding whether
    # to open a lookup table does not need the size of the table, and the number
    # made the one header on this page that answers nothing change every snapshot.
    # Closed, because this is a lookup tool rather than the page's deliverable.
    return panel("Look up one species: sortable and filterable",
                 SPECIES_LOOKUP_LEDE + " Every row, and the columns this table "
                 "does not show, are in "
                 '<a href="per_species_health.csv">per_species_health.csv</a>.',
                 body)


def p_calibration(c):
    """How often the first guess is right at each confidence band.

    The measurement is already on disk and already verified against
    ``confidence_calibration.csv``; until now only the internal page drew it,
    so a reader of this page met "confidence" as a column with nothing behind
    it. The reviewer on 2026-09-03 asked for the confidence as a distribution rather
    than one number, and this is the corpus-wide half of that: the species
    table's middle-half column is the per-species half.
    """
    rows = [(CONF_BAND_WORDS[band], k / nn if nn else 0.0,
             f'{pctf(k / nn) if nn else "n/a"} of {nn:,} frames', "#1565c0")
            for band, nn, k in c.bins_all]
    graded = sum(nn for _, nn, _ in c.bins_all)
    return panel(
        "Is the confidence score worth anything: mostly yes",
        "<b>Read this before treating a confidence as a probability.</b> How often "
        "the first guess is right, band by band, over every labelled frame.",
        svg_hbar(rows, title="how often the first guess is right, "
                             "by the model's own confidence")
        + f'<p class="note">All {graded:,} labelled frames, one guess each. The bands '
          f'rise, so a higher score really does mean a likelier answer, which is what '
          f'makes ordering the label queue on confidence work at all.</p>'
        f'<p class="note"><b>It is not a probability.</b> A band reading '
        f'{pctf(c.bins_all[-1][2] / c.bins_all[-1][1]) if c.bins_all[-1][1] else "n/a"} '
        f'is not the same claim as a score of {c.bins_all[-1][0][1:4]}. And this holds in '
        f'bulk only: on species with few labelled frames a high score is much less '
        f'reliable, which the label-queue page measures band by band.</p>'
        # The bars round to one figure a band. The file carries the counts they
        # were drawn from, so a reader can check a band rather than trust a bar.
        f'<p class="note">Every band, with the frames and the right guesses behind '
        f'it, is in <a href="confidence_calibration.csv">confidence_calibration.csv'
        f'</a>.</p>')


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
                       f'{d["n_labelled_frames"]:,}'] for d in rows],
                     source="per_species_health.csv")

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
            + sp_table(c.unproven_absent)
            + '<p class="note">The two flags the lists are split on are the '
              '<code>in_project_checklist</code> and <code>in_corpus_vocabulary</code> '
              'columns of the file each table above links.</p>')
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
              f'{c.c1 - c.strict1} are already inside every rate on this page. Every '
              f'label the botanists wrote, what it was resolved to and how, is in '
              f'<a href="name_reconciliation.csv">name_reconciliation.csv</a>.</p>'
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
    things. The top-5 rates stay in the grid: they are a ceiling on our own
    request, not a statement about the model.

    The card's eyebrow carries the metric name and how it was averaged, since
    a top-1 accuracy without the averaging is two different numbers on this
    corpus. The plain-English sentence sits under the figure as the gloss.
    """
    return hero([(f"{name.format(k=c.n_cand)}, {averaged}", pctf(c.now[metric]),
                  question.format(k=c.n_cand),
                  note.format(n_sp=c.n_sp, k=c.n_cand))
                 for metric, name, question, averaged, note in HEADLINES[:2]])


def _prf_block(c):
    """Precision, recall and F1 for the whole corpus, both ways of averaging.

    Four cards, not six. Three of them average per species; the fourth is the
    per-frame figure, and there is only one of it because per frame the three
    rates are literally the same number. Every frame here carries exactly one
    botanist label and exactly one first guess, so one wrong guess is one miss
    for the labelled species and one false alarm for the guessed one. The two
    denominators are then both the frame count, and the three rates collapse.
    Printing that number three times under three headings would read as three
    findings, so it is printed once with the reason beside it.

    This panel is read after the species table now, so the per-species versus
    per-frame argument is named here rather than referred back to.
    """
    return (
        hero([
            # The three per-species cards each average one column of
            # per_species_health.csv, so they link it: a reader who wants to see
            # which species carry the average takes the file off the card. The
            # per-frame card is not an average of those rows and links nothing.
            ("Precision, per species", pctf(c.now["macro_precision"]),
             "When it offers a name, how often that name is right",
             f"averaged over the {c.n_sp} species a botanist labelled, each counting "
             f"once however few frames it has", "per_species_health.csv"),
            ("Recall, per species", pctf(c.now["macro_recall"]),
             "Of the frames labelled a species, how often the first guess is right",
             "the same number as top-1 accuracy per species above, under the name a "
             "confusion matrix gives it", "per_species_health.csv"),
            ("F1, per species", pctf(c.now["macro_f1"]),
             "The two above balanced against each other, species by species",
             "each species&rsquo; own F1 first, then the average of those. That is not "
             "the F1 of the two averages beside it, which is a different number",
             "per_species_health.csv"),
            ("Precision, recall and F1, per frame", pctf(c.now["micro_prf1"]),
             "One figure, because per frame all three are the same number",
             f"over all {c.n:,} labelled frames it is also the per-frame top-1 accuracy"),
        ])
        + '<p class="note"><b>Why the per-frame figure is one number and not three.</b> '
          'Every frame here carries one botanist label and one first guess. A wrong '
          'guess is one miss for the labelled species and one false alarm for the '
          'guessed one. Both denominators are then the frame count, and precision, '
          'recall, F1 and top-1 accuracy work out identical.</p>'
        + '<p class="note"><b>Precision is measured on the frames we scored.</b> A '
          'false alarm is only visible where a botanist has labelled the frame. So '
          'these are rates over the frames we scored, not over the survey. A species '
          'with no labelled frame has no row here at all: the per-species averages '
          f'run over the {c.n_sp} labelled species only.</p>'
        + '<p class="note"><b>A species the model never guesses scores 0% precision, '
          'not a blank.</b> It has no right guesses to divide, and reading that as '
          'perfect precision on an empty list would flatter the average. Rows on very '
          f'few frames are noisy the same way. Under {THIN_MIN_FRAMES} labelled '
          'frames a row starts hidden in the species table, and its F1 can only land '
          'on a couple of values.</p>')


def p_weighting(c):
    # The four corpus rates and their qualifiers, in the one panel that explains
    # them. The grid reuses the headline card markup, so no new CSS exists.
    corpus = (
        hero([(f"{name.format(k=c.n_cand)}, {averaged}", pctf(c.now[metric]),
               question.format(k=c.n_cand), note.format(n_sp=c.n_sp, k=c.n_cand))
              for metric, name, question, averaged, note in HEADLINES])
        + f'<div class="caveat">{hero_region(c)}</div>'
        + f'<p class="note">{HERO_READING}</p>'
        + f'<p class="note">{HERO_WHICH_RATE}</p>'
        + f'<p class="note">{HERO_WHY_DIFFER}</p>'
        + _prf_block(c))
    return weighting_panel(per_species=c.per_species, sp_recs=c.sp_recs, support=c.support,
                           buckets=c.buckets, now=c.now, n=c.n, n_sp=c.n_sp,
                           corpus_block=corpus)


def _coverage_words(min_coverage):
    """The bar, as the condition a reader can check a frame against.

    The lowest bar admits any recorded overlap at all, so it is worded as a
    presence test rather than as 0%, which reads like a bar nothing can clear.
    """
    return ("any of the crop" if min_coverage <= 0
            else f"{min_coverage:.0%} of the crop")


def p_coverage(c):
    """The four rates again, with the crop required to show the labelled species.

    The house rule is that a gated number travels beside its ungated twin, and
    until now only the ungated one was on the page while the sweep behind it was
    measured on every build and published nowhere. It explains the four rates
    rather than replacing them, so it sits with the explanations and the summary
    states the cost in the same breath as the gain.

    The per-species column is the one that misleads. It climbs fastest, and most
    of that climb is the species set shrinking rather than the model improving,
    so the species count is a column of its own and the closing note says so.
    """
    rows = c.coverage_sweep
    lo, hi = rows[0], rows[-1]
    drop = c.coverage_dropped
    dropped = c.n - lo["n_admitted"]
    body = (
        table([("The label must cover", False), ("Labelled frames", True),
               ("Right, per frame", True), ("Right, per species", True),
               ("Species", True)],
              [[_coverage_words(r["min_coverage"]), f'{r["n_admitted"]:,}',
                pctf(r["micro_top1"]), pctf(r["macro_top1"]), f'{r["n_species"]:,}']
               for r in rows], source="coverage_gate.csv")
        + f'<p class="note"><strong>Requiring the crop to show the labelled species '
          f'raises the per-frame rate by '
          f'{100 * (hi["micro_top1"] - lo["micro_top1"]):.1f} points and costs '
          f'{lo["n_admitted"] - hi["n_admitted"]:,} of the '
          f'{lo["n_admitted"]:,} labelled frames.</strong> Every row asks a frame for two '
          f'things. The labelled species covers at least that much of the centre crop. '
          f'And it is the largest thing outlined inside it.</p>'
        + f'<div class="caveat"><p><strong>The per-species column climbs fastest for a '
          f'reason that is not the model.</strong> It averages every species equally. The '
          f'bottom row carries {hi["n_species"]:,} species where the top row carries '
          f'{lo["n_species"]:,}. Every one of the {drop["n"]:,} that leave has at most '
          f'{drop["max"]:,} labelled frames, and the median among them is '
          f'{drop["median"]:,.0f}. Those are the species the model gets wrong most often. '
          f'So read that column as a rate over an easier set of species, not as '
          f'{100 * (hi["macro_top1"] - lo["macro_top1"]):.1f} points waiting to be '
          f'collected.</p></div>'
        + f'<p class="note">{dropped:,} of the {c.n:,} scored frames appear in no row at '
          f'all. Either no crown geometry was recorded for their crop, or the largest '
          f'crown inside it carries a different species from the label. '
          f'The headline rates at the top of this page use no bar, which is the top '
          f'row.</p>'
)
    return panel(
        "What the accuracy becomes if the crop has to show the labelled species",
        f"<b>The rates above use no such condition.</b> Imposing one moves the per-frame "
        f"rate from {pctf(lo['micro_top1'])} to {pctf(hi['micro_top1'])} and drops "
        f"{lo['n_admitted'] - hi['n_admitted']:,} of {lo['n_admitted']:,} labelled "
        f"frames. Both are published here because neither is the whole answer.", body)


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
