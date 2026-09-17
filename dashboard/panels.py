"""The model-health page's panels: one function per collapsible block.

Each takes the figure namespace and returns HTML. A panel reads a figure, it
never computes one: the arithmetic is in ``figures.py``, the status vocabulary
in ``status_words.py``, the other pages' panels in ``queue_panels.py`` and
``confirmatory_panels.py``, and which page carries which panel in ``page.py``.
"""

from __future__ import annotations

import assess_panels as ap
import core as hc
from assets import (cap, esc, filterable_table, hero, more, num_cell, panel,
                    pctf, source_note, status_legend, status_tag, svg_hbar,
                    table)
from crop_overlap import CROP_SIZE, FRAME_H, FRAME_W
from explain import CONF_BAND_WORDS, method_panel, weighting_panel
from figures import WAIT_SUPPORT_MIN, conf, top1
from held_out import note as held_out_note
from snapshot_delta import note as delta_note
from status_words import (STATUS, filter_options, legend_entries,
                          status_precedence_note)

# What each file naming is, as a noun phrase both pages drop into their own
# sentence. Both words read like camera settings and neither is one: the flight
# team confirmed one camera throughout, and the flights that produced
# "tele" names produced "zoom" ones too. A reader who does not know that reads a
# lens difference into every count split this way, so it is said outright, and
# said once.
NAMING_IS = {
    "zoom": "the earlier file naming, zoom",
    "tele": "the later file naming, tele",
}

# Where the two namings come from, said once on each page that splits a count by
# them. Kept out of NAMING_IS so a sentence can name a naming without carrying
# the whole explanation every time.
NAMING_NOTE = ("Both words read like camera settings and neither is one. The flight "
               "team confirmed the naming changed and nothing else did. Every "
               "tele frame comes from one of four flights that also produced "
               "zoom frames.")

# The species table's lede, shared by the internal pages and the export-only one.
SPECIES_LOOKUP_LEDE = "Click a heading to sort. Type a name or pick a status to filter."

# Which rate answers which question. The cards that print the rates are on the
# first screen (landing.py); this is the one reading of them the explanations
# section opens with.
HERO_WHICH_RATE = (
    "<b>Per species</b> asks how many kinds of tree the model can name, "
    "which is what a labelling programme moves. <b>Per frame</b> asks how often it is "
    "right on a photo picked at random, which the commonest species decide."
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
        f"The <b>centre crop</b> is {CENTRE_CROP_IS}. Every rate over all the "
        f"labelled frames is scored on it. We ask Pl@ntNet for {k} names per photo, "
        f"a setting of ours and not a limit of the model.",
        "The <b>first guess</b> is the top-ranked of those names, and <b>right</b> "
        "means it matches the frame's label.",
        "<b>Outlining the trees first</b> means asking Pl@ntNet about each crown on "
        "its own. The answers are then weighted by how much of the frame each crown "
        "covers. The label is built the same way, so this is the fairer comparison.",
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
    """The crop-versus-label mismatch, worded for the corpus rates. It is what
    stops a reader taking a wrong answer here for a wrong identification."""
    return (
        "<p><strong>Every rate here scores a centre crop against a label for the whole "
        f"frame.</strong> {crop_mismatch(c)} So a wrong answer is not always a wrong "
        "identification.</p>"
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
# them. The first two are the pair, and a pair with several frames writes them
# once and spans them down its own rows.
REVIEW_COLUMNS = [("botanist label", False), ("Pl@ntNet's first guess", False),
                  ("confidence", True), ("frame", False)]


def _review_table(groups, urls):
    """One table, every review frame, a recurring pair written once over its rows.

    Not two tables: a pairs table capped at one number beside a frames table
    capped at another reads as two populations, and the pair a reader goes
    looking for is the one outside the first cap. The pair counts therefore stay
    inside the one table, without a second denominator.

    They stay as the row's own first two cells, spanned down the frames that
    share them, rather than as a full-width heading row above them. Most pairs
    here carry a single frame, so a heading row was a row restating the two
    names of the one row under it: double the height and the species name
    written twice. Spanned cells keep a recurring pair reading as one block and
    leave a one-frame pair as one line.
    """
    out = ["<table><thead><tr>"]
    for text, num in REVIEW_COLUMNS:
        cls = ' class="num"' if num else ""
        out.append(f"<th{cls}>{text}</th>")
    out.append("</tr></thead><tbody>")
    for (gt, pr), rows in groups:
        n = len(rows)
        # The count rides the pair it belongs to, and only where there is one to
        # make: "1 frame" beside a single row says nothing the row does not.
        span = f' rowspan="{n}"' if n > 1 else ""
        tally = f'<span class="tally">{n} frames</span>' if n > 1 else ""
        first = ' class="pair"'
        for i, r in enumerate(rows):
            key = r["global_key"]
            frame = (f'<a href="{esc(urls[key])}" target="_blank" rel="noopener">'
                     f'{esc(key)}</a>') if key in urls else esc(key)
            pair = (f'<td class="pair"{span}><span class="sp">{esc(cap(gt))}</span></td>'
                    f'<td class="pair"{span}><span class="sp">{esc(cap(pr))}</span>'
                    f'{tally}</td>') if i == 0 else ""
            out.append(f'<tr{first if i == 0 else ""}>{pair}'
                       f'<td class="num">{conf(r):.2f}</td>'
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
        out += (f' The other {here["n_unlinked"]} are not unlinkable: no file here '
                f'names both the project and the data row. An export of their project '
                f'would close it.')
    return (out + f' {wide["n_linked"]:,} of {wide["n_frames"]:,} labelled frames '
                  f'page-wide link ({pctf(wide["share"])}).</p>')


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
    body = (f'<p class="note">On each frame here the model is at least '
            f'{hc.REVIEW_CONF:.1f} confident in a <em>different</em> species from the '
            f'label. In bulk, a first guess this confident is right '
            f'{pctf(c.confident_ok)} of the time ({c.confident_hits:,} of '
            f'{len(c.confident):,}).</p>'
            f'<p class="note">All {n} frames, under {len(groups)} label-and-guess '
            f'pairs. The {len(recur)} pairs that recur come first and cover {covered} '
            f'frames. The other {len(groups) - len(recur)} are one frame each.</p>'
            + ap.mechanism_note(c.disagreement, c.review_mechanisms)
            # Which rows carry a link is read off the table itself, one link at a
            # time. The count and what closes the gap answer a question about the
            # join, which is not the question a botanist opened this panel with.
            + more("How many of these rows link to Labelbox",
                   _link_note(here, wide))
            + (_review_table(groups, urls) if groups
               else '<p class="note">None at this confidence.</p>')
            + '<p class="note">Work this list after the label queue. A pair that keeps '
              'recurring says something about the species, not just the photo.</p>')
    if c.n_adjudicated:
        body += (f'<p class="note">{c.n_adjudicated} further frame'
                 f'{"" if c.n_adjudicated == 1 else "s"} disagree at this confidence but '
                 f'are not listed: a botanist confirmed the label, so the model is wrong '
                 f'there. They still count against the {pctf(c.confident_ok)} above.</p>')
    return panel(f"Labels worth a second look: {n} confident "
                 f"disagreements a botanist can settle",
                 f"<b>Put these {n} frames in front of a botanist.</b> "
                 # The file is named under the table by `source_note`, and the
                 # first sentence already says what the list is for, so both the
                 # ask and the repeat came out of the lede.
                 f"Either the label or the model is wrong, and one look settles "
                 f"which.", body)


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
            f'top-1 accuracy.</p>'
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


def _hint(text, definition):
    """A column heading that carries its own definition, one hover away.

    ``abbr`` rather than a superscript marker: it is the element that means
    exactly this, it needs no markup inside the cell a reader clicks to sort,
    and a phone that cannot hover still has the block below. The same sentence
    appears in both places, written once here.
    """
    return f'<abbr title="{esc(definition)}">{esc(text)}</abbr>'


def _species_columns_note():
    """The column definitions, closed. Four paragraphs of them stood open above
    the table and pushed it off the first screen; a reader who already knows
    what precision is was paying for the reader who does not."""
    return ('<details class="more"><summary>What the columns mean</summary>'
            '<p class="note"><b>Top-1 accuracy on a species row is its recall</b>: of '
            'the frames labelled that species, the share the first guess got right. '
            '<b>Precision</b> is the reverse: of the frames the model gave that name, '
            'the share that were it, counted only where a botanist labelled the frame. '
            '<b>F1</b> is their harmonic mean, so a row scores well only when both '
            'do.</p>'
            '<p class="note"><b>Model&rsquo;s confidence</b> is Pl@ntNet&rsquo;s score '
            'for its first guess, averaged over the species&rsquo; frames. 0.86 means '
            'nearly all of it went on one name, and 0.32 means it was spread thin. '
            '<b>Middle half</b> is where the middle 50% of those frames fall, the 25th '
            'to the 75th percentile. A wide range is two behaviours averaged into one '
            'number, and the column sorts on the width.</p></details>')


def _species_status_note():
    """The status legend and its precedence rule, closed. The colours are on the
    rows either way; this is what a reader opens once and then does not need."""
    return ('<details class="more"><summary>What the statuses mean</summary>'
            + status_legend(legend_entries())
            + f'<p class="note">{status_precedence_note()}</p></details>')


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
            status_tag(st, STATUS[st][0]),
            ap.limit_cell(*c.limits[sp])])
        # No data-status: the row's status tag carries it and the filter reads
        # it from there, rather than 4KB of markup saying it twice.
        attrs.append(' data-thin="1"' if _starts_hidden(d, st) else "")
    # Counted off the marks just made, so the prose below cannot name a
    # different number from the table.
    n_thin = sum(1 for a in attrs if a)
    # The table is what this panel is for, so what stands above it is the one
    # caveat that changes how every number reads, the control, and the line
    # about the hidden rows. The definitions used to stand there too, four
    # paragraphs of them, and pushed the table off the first screen. They are
    # now a heading's own tooltip for the reader who stumbles on one column, and
    # a closed block for the reader who wants all of them.
    body = ('<p class="note"><b>Rates here score the centre crop, not outlined '
            'crowns.</b> Read a low row as a flag for a second look, not as that '
            'species&rsquo; accuracy.</p>'
            + _species_columns_note()
            + _species_status_note()
            # What more labels would buy is a reading of the table for someone
            # auditing us, not for someone looking up one species, so it waits
            # behind a summary line. The flight note below it stays open: it is
            # the guard that stops a reader reading one rate as the other's
            # population, and a guard nobody opens is not a guard.
            + more("What more labels would buy",
                   ap.limit_note(c.transductive, c.limits))
            + threshold_control(c)
            + f'<p class="note"><b>{n_thin} of these {c.n_sp} species start hidden.</b> '
              f'Each has fewer than {THIN_MIN_FRAMES} labelled frames, and '
              f'<i>show all {c.n_sp}</i> brings them back.</p>'
            + filterable_table(
        # "(recall)" is in the header, not only in the block below: a reader
        # scanning the columns found Precision and F1, no recall, and read that
        # as a missing column rather than as the one it shares a number with.
        # Every heading a reader can misread carries its own definition as a
        # tooltip, so the common case needs neither the block nor a scroll back.
        [("Species", False),
         (_hint("Labelled frames", "Frames a botanist labelled this species."), True),
         (_hint("Top-1 accuracy (recall)",
                "Of the frames a botanist labelled this species, the share the "
                "first guess got right."), True),
         (_hint(f"Top-{c.n_cand} accuracy",
                f"The share of those frames where the right name is among the "
                f"{c.n_cand} names requested."), True),
         (_hint("Frames guessed",
                "Labelled frames the model returned this name on, right or "
                "wrong. The population precision is scored over."), True),
         (_hint("Precision",
                "Of the frames the model guessed this name on, the share that "
                "really were it."), True),
         (_hint("F1", "The harmonic mean of precision and recall, so a row "
                      "scores well only when both do."), True),
         (_hint("Model's confidence",
                "Pl@ntNet's own score for its first guess, averaged over this "
                "species' frames."), True),
         (_hint("Middle half",
                "Where the middle 50% of this species' frames fall, the 25th to "
                "the 75th percentile. Sorts on the width, not the ends."), True),
         ("Status", False),
         (_hint("What would help", ap.LIMIT_HINT), False)],
        sp_rows,
        options=filter_options(),
        row_attrs=attrs,
        source="per_species_health.csv",
        thin_label=f"show all {c.n_sp}",
    )
            # Under the table, not above it, and open either way. It is the guard
            # that stops a reader taking the rate on the graded frames for the
            # rate a new flight would get, so it is read where the rates are,
            # and a reader who came to look up one species reaches the table
            # first. Behind a summary line it would be a guard nobody opens.
            + held_out_note(c.held_out, c.flight_holdout))
    # The colon stays, since slug() cuts there and the anchor keeps its old value.
    # The species count was in this summary and is gone: a reader deciding whether
    # to open a lookup table does not need the size of the table, and the number
    # made the one header on this page that answers nothing change every snapshot.
    # Open, because the status buttons on the first screen filter this table,
    # and a filter on a closed panel changes nothing a reader can see.
    return panel("Look up one species: sortable and filterable",
                 SPECIES_LOOKUP_LEDE, body, open_=True)


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
        "Is the confidence score worth anything: in bulk yes, on rare species no",
        "<b>How often the first guess is right at each confidence score.</b>",
        svg_hbar(rows, title="how often the first guess is right, "
                             "by the model's own confidence")
        # The bars round to one figure a band, so the file that carries the counts
        # is named beside the population rather than in a paragraph of its own:
        # it is the same sentence, and it was costing the panel an opening.
        + f'<p class="note">The counts behind every band, over all {graded:,} labelled '
          f'frames, are in '
          f'<a href="confidence_calibration.csv">confidence_calibration.csv</a>. Higher '
          f'bands are right more often, which is why ordering the label queue by '
          f'confidence works.</p>'
        f'<p class="note"><b>It is not a probability.</b> A band right '
        f'{pctf(c.bins_all[-1][2] / c.bins_all[-1][1]) if c.bins_all[-1][1] else "n/a"} '
        f'of the time is not a score of {c.bins_all[-1][0][1:4]}. And it holds in bulk '
        f'only: on species with few labelled frames a high score means much less, as the '
        f'label queue page shows.</p>'
        + ap.reject_table(c.reject_sweep))


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
            f'species list for this project.</strong> No re-run can return them. Do not '
            f'spend expert time relabelling these.</div>'
            + sp_table(c.out_of_scope)
            + f'<p class="note"><strong>The other {c.unproven_absent_frames} frames, '
            f'on {len(c.unproven_absent)} species, are on that list but never ranked in '
            f'the top {c.n_cand} for any photo.</strong> That shows we asked for too few '
            f'names, not that the model cannot return them. A re-run asking for more '
            f'could recover some.</p>'
            + sp_table(c.unproven_absent)
            + '<p class="note">Each linked file carries two flags. One says whether the '
              'species is on the project&rsquo;s own list, the other whether its name '
              'ever came back in a cached answer.</p>')
    else:
        scope_html = (
            f'<div class="warn"><strong>This is a limit of the question we asked, not proof '
            f'the model has never heard of these species.</strong> Offline we can only check '
            f'whether a name turns up in the cached answers, and we asked for '
            f'{c.n_cand} candidates per photo. A species Pl@ntNet knows well, but which '
            f'never made a list of {c.n_cand} on a BCI photo, looks exactly like one it '
            f'cannot return. Do not spend expert time renaming or relabelling these; only '
            f'Pl@ntNet&rsquo;s own list for this project, or a re-run, can tell the two '
            f'apart.'
            f'</div>'
            + sp_table(c.never))

    body = (f'<p class="note"><strong>Those {c.never_frames} frames are '
            f'{pctf(c.never_frames / n)} of the {n:,} evaluated, and no answer the model '
            f'gave us named their species.</strong> Leaving them out raises the per-frame rate from {pctf(c.c1 / n)} to '
            f'{pctf(c.reach1)} on {len(c.reach):,} centre crops.</p>'
            f'<p class="note">Counting all {len(c.h.gt_rows):,} frames with a botanist '
            f'label, genus-only and uncached ones included, {c.never_all} carry a name the '
            f'model never returned to us.</p>'
            + scope_html
            + f'<p class="note">The cap did not always bite. On {c.short5:,} of the '
            f'{c.n_pred:,} frames with a cached answer ({pctf(c.short5 / c.n_pred)}) fewer '
            f'than {c.n_cand} came back. On the other {c.n_pred - c.short5:,}, anything '
            f'ranked {c.n_cand + 1} or lower is invisible to us.</p>'
            + f'<p class="note"><strong>Spelling and renamed species cost no '
              f'frames.</strong> Labels and predictions are normalised and old names '
              f'resolved before comparison. Raw names would score {pctf(c.strict1 / n)} '
              f'rather than {pctf(c.c1 / n)}, so matching already adds '
              f'{c.c1 - c.strict1} frames to every rate here. Every label, what it '
              f'resolved to and how, is in '
              f'<a href="name_reconciliation.csv">name_reconciliation.csv</a>.</p>'
              f'<p class="note"><strong>{gn:,} further frames carry only a genus '
              f'name</strong> and are left out of every species number above. Scored at '
              f'genus level they reach {pctf(c.gg1 / gn) if gn else "n/a"}.</p>'
              f'<p class="note">Of them, {c.gen_any:,} have a candidate in the right genus '
              f'among the {c.n_cand}. <strong>{c.gen_one:,} have exactly one</strong>, '
              f'which makes the species a yes-or-no question. Whether that '
              f'is worth expert time is for the label queue page.</p>'
              f'<p class="note">A further {c.fam_n} frames are labelled to {c.fam_names} '
              f'<em>families</em>, not genera, and are left out of the genus rate. A family '
              f'never matches a predicted species, and rolling up to family needs a list '
              f'we lack here. Counting them would give {pctf(c.gg1 / (gn + c.fam_n))} '
              f'instead of {pctf(c.gg1 / gn)}.</p>')
    return panel(f"What labelling cannot fix: {len(c.never)} species, {c.never_frames} frames "
                 f"the model never named",
                 "<b>Most of these are not proof the model cannot return the species.</b> "
                 "Some are proven absent from the project's own list. The rest we never "
                 "asked for enough names to find.",
                 body)


def p_terms(c):
    """The vocabulary every number on the page rests on.

    A panel, not a paragraph: definitional, so a reader who has the vocabulary
    can skip it and one who does not can open it once.
    """
    return panel(
        'What the words mean: frame, label, crown, centre crop',
        "<b>Four words do all the work on this page.</b>",
        hero_terms(c.n_cand))


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
             f"averaged over the {c.n_sp} labelled species, each counting once",
             "per_species_health.csv"),
            ("Recall, per species", pctf(c.now["macro_recall"]),
             "Of the frames labelled a species, how often the first guess is right",
             "the same number as top-1 accuracy per species",
             "per_species_health.csv"),
            ("F1, per species", pctf(c.now["macro_f1"]),
             "Precision and recall balanced, species by species",
             "the average of each species&rsquo; own F1, not the F1 of the two "
             "averages", "per_species_health.csv"),
            ("Precision, recall and F1, per frame", pctf(c.now["micro_prf1"]),
             "One figure, because per frame all three are the same number",
             f"over all {c.n:,} labelled frames it is also the per-frame top-1 accuracy"),
        ])
        # Three notes on four cards. A reader reads the cards; these answer the
        # questions the cards raise, in the order they raise them, and they
        # raise them one reader in ten. So they sit behind their own line.
        + more("What these four are measured on",
               '<p class="note"><b>Why the per-frame figure is one number.</b> Each '
               'frame has one botanist label and one first guess. So a wrong guess is '
               'one miss for one species and one false alarm for another. Both '
               'denominators are '
               'the frame count, so precision, recall, F1 and top-1 accuracy come out '
               'identical.</p>'
               '<p class="note"><b>Precision is over the frames we scored.</b> A false '
               'alarm only shows where a botanist labelled the frame, so these are rates '
               f'over the frames we scored, not over the survey. The averages run over the {c.n_sp} labelled '
               'species only.</p>'
               '<p class="note"><b>A species the model never guesses scores 0% precision, '
               'not a blank</b>, so an empty list does not flatter the average. Rows on '
               f'few frames are noisy too, which is why a row under {THIN_MIN_FRAMES} '
               'labelled frames starts hidden in the species table.</p>'))


def p_weighting(c):
    # The four accuracy cards are on the first screen (landing.py), so this
    # panel carries what qualifies them: the crop caveat, which rate answers
    # which question, and precision, recall and F1 both ways.
    corpus = (f'<div class="caveat">{hero_region(c)}</div>'
              f'<p class="note">{HERO_WHICH_RATE}</p>'
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
          f'{lo["n_admitted"]:,} labelled frames.</strong> Each row asks two things of a '
          f'frame. The labelled species covers at least that much of the centre crop, '
          f'and it is the largest thing outlined there.</p>'
        + f'<div class="caveat"><p><strong>The per-species column climbs fastest for a '
          f'reason that is not the model.</strong> The bottom row keeps '
          f'{hi["n_species"]:,} of the top row&rsquo;s {lo["n_species"]:,} species. All '
          f'{drop["n"]:,} that leave have at most {drop["max"]:,} labelled frames (median '
          f'{drop["median"]:,.0f}), and they are the ones the model misses most. So read '
          f'that column as a rate over easier species, not as '
          f'{100 * (hi["macro_top1"] - lo["macro_top1"]):.1f} points waiting to be '
          f'collected.</p></div>'
        + f'<p class="note">{dropped:,} of the {c.n:,} scored frames are in no row. '
          f'Either no crown geometry was recorded for their crop, or its largest crown '
          f'is a different species from the label. The rates at the top of this page use no '
          f'bar, which is the top row.</p>'
)
    return panel(
        "What the rates become when the crop really shows the labelled tree",
        f"<b>Every rate above counts a frame whatever its crop shows.</b> Require the "
        f"labelled tree in the crop and the per-frame rate moves from "
        f"{pctf(lo['micro_top1'])} to {pctf(hi['micro_top1'])}, at the cost of "
        f"{lo['n_admitted'] - hi['n_admitted']:,} of {lo['n_admitted']:,} labelled "
        f"frames.", body,
        # Named rather than slugged: slug() cuts at eight words and this heading
        # would ship as "...when-the-crop-really", a phrase broken mid-clause.
        anchor="when-the-crop-shows-the-labelled-tree")


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
        + ap.richness_note(c.richness)
        # Then and now, beside the counts it is a change in.
        + delta_note(c.delta, floor=WAIT_SUPPORT_MIN))
