"""The HTML builders: panels, tables, hero cards, inline SVG.

Every function returns a string of HTML built from its arguments alone. The
stylesheet, the script, and the element ids they share with
``filterable_table`` are in ``style.py``.

Why one module, when sixteen of its seventeen functions are leaf renderers that
never call each other: they share a stylesheet, a status vocabulary, and
``_text_w``, the font metric the SVG geometry sizes against. Splitting them by
kind of output, tables here, SVG there, layout and escaping elsewhere, hands
four import lists to every caller and describes the same implementation with a
wider interface. Leaf renderers over one stylesheet is what a rendering module
looks like when it is working. The stylesheet itself did leave, to ``style.py``,
under a condition: ``tests/test_style.py`` checks both directions of the class
coupling that used to be held together only by living in one file.
"""

from __future__ import annotations

import html
import math
import re
from typing import NamedTuple

from style import COUNT_ID, INPUT_ID, SELECT_ID, TABLE_ID, THIN_ID

def esc(s: object) -> str:
    """HTML-escape any value (same role as labelfirst's ``_esc``)."""
    return html.escape(str(s))


def cap(s: str) -> str:
    """Capitalise a scientific name for display. CSV keys are lowercased for
    the GBIF/WCVP join; a binomial displays with the genus capitalised."""
    return s[:1].upper() + s[1:]


def pctf(x, nd=1):
    return "n/a" if x is None else f"{100.0 * x:.{nd}f}%"


# --- structure ---
def slug(text: str) -> str:
    """A stable id from display text, so an anchor cannot drift from its heading.
    Text before the first colon, lowercased, non-alphanumerics to hyphens, first
    eight words. The colon split matters: summaries carry live numbers ("...: 412
    frames") that change every snapshot, so ``panel`` rejects a digit-bearing id."""
    head = re.sub(r"<[^>]+>", "", str(text)).split(":")[0]
    words = re.sub(r"[^a-z0-9]+", " ", head.lower()).split()
    return "-".join(words[:8])


def panel(summary, ask, body, *, open_=False, anchor=None):
    """A collapsible panel. ``summary`` must stand alone closed; ``ask`` says
    what to do with what's inside. ``anchor`` overrides the derived id, and is
    required when ``summary`` carries a live number."""
    pid = anchor or slug(summary)
    if not anchor and any(c.isdigit() for c in pid):
        raise SystemExit(
            f"panel id {pid!r} carries a number from its summary, so a link to it "
            f"breaks on the next snapshot. Pass anchor= at this call site.")
    return (f'<details class="panel" id="{pid}"{" open" if open_ else ""}>'
            f"<summary>{summary}</summary>"
            f'<div class="pbody"><p class="ask">{ask}</p>{body}</div></details>')


def section(title, lede, panels):
    """A named group of panels: heading band, one orienting line, panels.
    ``panels`` is already-rendered HTML. The band carries the group's question,
    not a label: that is what makes a closed page scannable."""
    return (f'<section class="grp" id="{slug(title)}"><h2>{title}</h2>'
            f'<p class="lede">{lede}</p>\n{panels}</section>')


def hero(cards):
    """The band of big numbers a page opens with, leading card first.

    ``cards`` is ``[(eyebrow, value, label, note), ...]``, and the grid CSS is
    written against the metric card markup.

    A card may carry a fifth item, the CSV the number is read off. It renders as
    a link beside the figure, so the reader who wants the rows behind the
    headline can take them from the card rather than hunting the panel that
    names the file. Link only a file the card's own number comes out of: the
    link reads as provenance, and pointing it at a near-enough file makes the
    card lie. ``page.copy_linked_csvs`` then carries the file with the page and
    aborts the build if it is missing, so a linked card cannot ship a 404.
    """
    out = ['<div class="hero">']
    for i, card in enumerate(cards):
        # A range check, not membership of a two-length tuple: written that way
        # it reads to test_health's literal guard as a candidate-list length
        # passed as a literal, and that guard is worth more than the tuple.
        if not 4 <= len(card) <= 5:
            raise SystemExit(
                f"hero card {i} has {len(card)} items: it takes (eyebrow, value, "
                f"label, note) and an optional source CSV.")
        eyebrow, value, label, note = card[:4]
        source = card[4] if len(card) > 4 else ""
        src = f'<a class="src" href="{source}">{source}</a>' if source else ""
        out.append(f'<div class="metric{" first" if i == 0 else ""}">'
                   f'<div class="e">{eyebrow}</div>'
                   f'<div class="row"><div class="v">{value}</div>{src}</div>'
                   f'<div class="l">{label}</div>'
                   f'<div class="n">{note}</div></div>')
    out.append("</div>")
    return "".join(out)


class Cell(NamedTuple):
    """Cell text plus the attributes its own ``<td>`` should carry.
    Rows stay plain strings wherever a cell needs no attribute."""

    html: str
    attrs: str = ""

    def __str__(self) -> str:
        return self.html


def source_note(source) -> str:
    """The line under a table naming the file its rows are in, or "" for none.

    Reuses ``.note``, the caption style the panels already write under a figure:
    a download affordance of its own would be a rule and a colour for a line
    that says what every other footnote on the page says. Written once here
    because ``_review_table`` builds its own markup and would otherwise word
    this differently from every table that goes through ``table``.
    """
    return (f'<p class="note">This table as data: <a href="{source}">{source}</a>, '
            f'with the columns it does not show.</p>') if source else ""


def table(headers, rows, *, tid=None, sortable_from=None, row_attrs=None, source=None):
    """headers = [(text, is_numeric)]; rows = [[cell_html, ...]].

    ``source`` names the CSV the rows were counted off, and renders as one line
    under the table. A reader looking at a table wants the rows, and the rows
    were on disk all along, named halfway through a paragraph above the table if
    they were named at all. ``page.copy_linked_csvs`` then carries the file
    beside the page and aborts the build if it is absent, so a named table
    cannot ship a 404. Point it only at the file the rows actually come from:
    the line reads as provenance, and a near-enough file makes the table lie.
    """
    # A table with an id says "these columns are numbers" once, rather than
    # class="num" on every cell of the 187-row species table. A table with no id
    # has no selector, and is short enough not to need one.
    num_cols = [i + 1 for i, (_, num) in enumerate(headers) if num]
    by_column = bool(tid) and bool(num_cols)
    rule = ("<style>"
            + ",".join(f"#{tid} td:nth-child({i})" for i in num_cols)
            + "{text-align:right;font-variant-numeric:tabular-nums}</style>"
            ) if by_column else ""

    out = [f'<table{f" id={tid!r}" if tid else ""}>', "<thead><tr>"]
    for i, (text, num) in enumerate(headers):
        cls = ["num"] if num else []
        if sortable_from is not None and i >= sortable_from:
            cls.append("sortable")
        c = f' class="{" ".join(cls)}"' if cls else ""
        out.append(f"<th{c}>{text}</th>")
    out.append("</tr></thead><tbody>")
    for j, r in enumerate(rows):
        out.append(f"<tr{row_attrs[j] if row_attrs else ''}>")
        for i, cell in enumerate(r):
            c = ' class="num"' if headers[i][1] and not by_column else ""
            out.append(f"<td{c}{getattr(cell, 'attrs', '')}>{cell}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    # Scrolls in its own box, or the 7-column table sets page width on a phone.
    return (rule + '<div class="tscroll">' + "\n".join(out) + "</div>"
            + source_note(source))


def filterable_table(headers, rows, *, options, row_attrs=None, thin_label=None,
                     source=None):
    """A search/filter strip followed by a sortable table. The page has exactly
    one; element ids use the ``TABLE_ID`` constants, not literals."""
    # No options means no status to filter on, so no select: one holding nothing
    # but "every status" cannot change the table, which is what the JS assumes.
    if options:
        opts = "".join(
            f'<option value="{esc(value)}">{esc(label)}</option>' for value, label in options
        )
        select = (f'<select id="{SELECT_ID}" aria-label="filter by status">'
                  f'<option value="all">every status</option>{opts}</select>')
    else:
        select = ""
    # ``thin_label`` turns on the show-everything checkbox; the caller marks the
    # rows it hides with ``data-thin="1"`` in ``row_attrs``. No label, no checkbox.
    if thin_label:
        toggle = (f'<label class="showall"><input type="checkbox" id="{THIN_ID}"> '
                  f'{thin_label}</label>')
    else:
        toggle = ""
    controls = (
        '<div class="controls">'
        f'<input id="{INPUT_ID}" type="search" placeholder="filter species&hellip;" size="28" '
        f'aria-label="filter species">'
        f"{select}{toggle}<span class=\"count\" id=\"{COUNT_ID}\"></span></div>"
    )
    # Every caller puts the species name in the first column and the filter
    # matches on it, so italics are a column rule, not a span on all 187 rows.
    return (f'<style>#{TABLE_ID} td:nth-child(1){{font-style:italic}}</style>'
            + controls + table(headers, rows, tid=TABLE_ID, sortable_from=0,
                               row_attrs=row_attrs, source=source))


def funnel_list(steps: list[tuple[int, str]]) -> str:
    """A count-then-label list: ``steps`` is ``[(count, label), ...]``, outermost
    first. Reuses the to-do-list markup (``.todo``/``.n``), so a photo-to-frame
    funnel needs no CSS of its own."""
    rows = "".join(f'<li><span class="n">{count:,}</span> {esc(label)}</li>'
                   for count, label in steps)
    return f'<ul class="todo">{rows}</ul>'


def sort_key(value) -> str:
    """The number as the sort reads it: full precision, no idle characters.
    A rate is carried to six decimals, finer than any cell shows and enough that
    two species never tie by rounding. Trailing zeros carry none of that:
    "0.000000" and "0" sort alike, and the longer one costs 1.5KB of a 100KB
    page. Formatted here rather than at each call site."""
    v = f"{value:.6f}" if isinstance(value, float) else str(value)
    if "." in v:
        v = v.rstrip("0").rstrip(".") or "0"
    return v


def num_cell(value, shown: str) -> str:
    """A table cell, carrying the number to sort on only when it differs.
    The sort reads ``data-sort`` and falls back to the cell's own text, so a
    plain integer needs no attribute: "392" already sorts as 392. A rounded
    percentage does ("92.9%" hides 0.928571), and so does any figure written
    with thousands separators, since JavaScript reads "1,204" as 1."""
    v = sort_key(value)
    try:
        redundant = "," not in shown and float(shown) == float(v)
    except ValueError:
        redundant = False
    return Cell(shown) if redundant else Cell(shown, f' data-sort="{v}"')


def status_tag(cls: str, label: str) -> str:
    """Render a status tag. The explanation is not repeated per row: a hover-icon
    ``title=`` shipped once here, ~40KB of duplicated markup across a 186-row
    table. Callers render each sentence once via ``status_legend`` instead."""
    return f'<span class="tag {esc(cls)}">{esc(label)}</span>'


def strip_comments(text: str) -> str:
    """CSS and JS with maintainer comments stripped, for the built page.
    Uncut they ship 3.6 KB of notes to every reader. JS only drops lines
    *starting* with ``//``, so ``//`` inside a string survives."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^[ \t]*//.*$", "", text, flags=re.M)
    return re.sub(r"\n{2,}", "\n", text).strip()


def css_for(css: str, page: str) -> str:
    """The stylesheet minus the rules for classes this page never renders.

    A rule survives unless every one of its selectors names a class the page
    never uses, so anything selecting an element, an id or a state stays
    untouched. ``page`` is the built HTML, script included: the script writes
    classes of its own (``hidden``, ``asc``, ``desc``), so every quoted word
    counts as a class."""
    used = set()
    for group in re.findall(r'class="([^"]+)"', page):
        used |= set(group.split())
    used |= set(re.findall(r"'([A-Za-z][\w-]*)'", page))

    def unused(selector: str) -> bool:
        named = re.findall(r"\.([A-Za-z][\w-]*)", selector)
        return bool(named) and not set(named) <= used

    kept, i = [], 0
    while (brace := css.find("{", i)) >= 0:
        depth, end = 1, brace + 1
        while depth and end < len(css):
            depth += (css[end] == "{") - (css[end] == "}")
            end += 1
        selector = css[i:brace].strip()
        # An @media block's own selector names no class, so it is kept whole.
        if selector.startswith("@") or not all(
                unused(part) for part in selector.split(",")):
            kept.append(css[i:end])
        i = end
    return "".join(kept).strip()


def status_legend(entries: list[tuple[str, str, str]]) -> str:
    """The status explanations, once, instead of per row.
    ``entries`` is ``[(css_class, label, reason), ...]``, in read order."""
    items = "".join(
        f'<li><span class="tag {esc(cls)}">{esc(label)}</span> {esc(reason)}</li>'
        for cls, label, reason in entries
    )
    return f'<ul class="status-legend">{items}</ul>'


# --- inline SVG (hand-written in labelfirst's report idiom) ---
_NARROW = set(" .,;:'!|iljtfr()[]·")
_WIDE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw%@")


def _text_w(text: str, font_px: float) -> float:
    """Upper bound on the rendered width of ``text`` at ``font_px``.

    The width has to be estimated: ``system-ui`` varies by machine, and the page
    ships as one file. Three character classes plus 0.26em per string for side bearings,
    times 1.06, calibrated against ``getComputedTextLength`` on 14 of this page's
    labels under SF NS (Segoe UI/Roboto run narrower). 1.06 is not measured
    headroom, only 14 of 59 labels were checked; it leans high because a clipped
    label ships silently: five once read "1,856 cr" while passing every numeric
    check."""
    em = 0.26 + sum(0.28 if c in _NARROW else 0.72 if c in _WIDE else 0.60 for c in text)
    return 1.06 * em * font_px


def _axis_num(value: float) -> str:
    """An axis tick a reader can take in at a glance.

    Whole counts get a thousands separator; a fraction under one gets two
    decimals, which is as fine as any distance on this page is ever read.
    """
    if abs(value) >= 10:
        return f"{round(value):,}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def svg_hbar(rows, *, title=""):
    """Horizontal bars. ``rows`` = [(label, frac, right_text, color)].
    ``right_w`` grows to fit the longest value label rather than truncating
    (SVG clips, no CSS can rescue it). Geometry is fixed, not parameterised."""
    if not rows:
        return ""
    width, row_h, label_w, right_w = 620, 30, 112, 140
    top = 26 if title else 8
    bar_w = width - label_w - right_w
    right_w = max(right_w, math.ceil(8 + max(_text_w(r[2], 11.5) for r in rows) + 6))
    width = label_w + bar_w + right_w
    height = top + len(rows) * row_h + 26
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'role="img" aria-label="{esc(title or "bar chart")}">']
    if title:
        out.append(f'<text x="{label_w}" y="16" font-size="12" fill="#616161">'
                   f'{esc(title)}</text>')
    for i, (label, frac, right, color) in enumerate(rows):
        y = top + i * row_h
        frac = max(0.0, min(1.0, float(frac)))
        out.append(f'<text x="{label_w - 8}" y="{y + 15}" font-size="12" fill="#424242" '
                   f'text-anchor="end">{esc(label)}</text>'
                   f'<rect x="{label_w}" y="{y + 4}" width="{bar_w}" height="16" '
                   f'fill="#f1f3f4" rx="3"/>'
                   f'<rect x="{label_w}" y="{y + 4}" width="{max(1, round(bar_w * frac))}" '
                   f'height="16" fill="{color}" rx="3"/>'
                   f'<text x="{label_w + bar_w + 8}" y="{y + 16}" font-size="11.5" '
                   f'fill="#616161">{esc(right)}</text>')
    axis_y = top + len(rows) * row_h + 4
    out.append(f'<line x1="{label_w}" y1="{axis_y}" x2="{label_w + bar_w}" y2="{axis_y}" '
               f'stroke="#e0e0e0"/>')
    for t in (0, 25, 50, 75, 100):
        x = label_w + bar_w * t / 100.0
        # The tick carries nothing, every value being printed at its bar end, so
        # it stays faint at 1.88:1 on the white panel. The number under it is
        # read, so it clears 4.5:1 and is set at 11px.
        out.append(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 4}" '
                   f'stroke="#bdbdbd"/>'
                   f'<text x="{x:.1f}" y="{axis_y + 17}" font-size="11" fill="#6d6d6d" '
                   f'text-anchor="middle">{t}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def svg_weight_pair(rows, *, label_a, label_b):
    """Two full-width bars over the same bands, split by a different weight each.
    ``rows`` = ``[(band, share_a, share_b, note, colour)]``, shares summing to 1
    per column, so the reader sees the weight move without arithmetic. Each
    column asserts that sum: a wrong denominator draws a short bar, not a wrong
    number, which no recompute check would catch. ``pad_l`` fits the longer row
    label; labels are right-anchored, so an overlong one silently loses its
    first character off the viewBox."""
    if not rows:
        return ""
    width, bar_h, pad_l = 620, 28, 168
    for key in (1, 2):
        total = sum(float(r[key]) for r in rows)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weight column {key} sums to {total}, not 1; "
                             "the shares are against the wrong denominator")
    bar_w = width - pad_l - 10
    pad_l = max(pad_l, math.ceil(2 + max(_text_w(label_a, 11.5), _text_w(label_b, 11.5)) + 10))
    width = pad_l + bar_w + 10
    leg_h, gap = 19, 12
    height = 8 + 2 * bar_h + gap + 16 + leg_h * len(rows)
    o = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
         f'role="img" aria-label="{esc(label_a)} against {esc(label_b)}">']
    for i, (label, key) in enumerate(((label_a, 1), (label_b, 2))):
        y = 8 + i * (bar_h + gap)
        o.append(f'<text x="{pad_l - 10}" y="{y + bar_h / 2 + 4:.0f}" font-size="11.5" '
                 f'fill="#424242" text-anchor="end">{esc(label)}</text>')
        x = pad_l
        for r in rows:
            w = bar_w * float(r[key])
            o.append(f'<rect x="{x:.1f}" y="{y}" width="{max(0.7, w):.1f}" '
                     f'height="{bar_h}" fill="{r[4]}"/>')
            # Below this a two-character percentage collides with the band edges.
            if w >= 25:
                o.append(f'<text x="{x + w / 2:.1f}" y="{y + bar_h / 2 + 4:.0f}" '
                         f'font-size="11" fill="#fff" text-anchor="middle">'
                         f'{100 * float(r[key]):.0f}%</text>')
            x += w
    y = 8 + 2 * bar_h + gap + 14
    for i, r in enumerate(rows):
        o.append(f'<rect x="{pad_l - 10}" y="{y + i * leg_h - 8}" width="10" height="10" '
                 f'fill="{r[4]}" rx="2"/>'
                 f'<text x="{pad_l + 6}" y="{y + i * leg_h}" font-size="11" fill="#616161">'
                 f'{esc(r[0])}: {esc(r[3])}</text>')
    o.append("</svg>")
    return "\n".join(o)


def svg_curve(series, *, title="", x_title="", y_title="", rules=(), marks=()):
    """Lines over a shared pair of axes. ``series`` = ``[(label, points, colour)]``
    with ``points`` = ``[(x, y), ...]`` in data units, read in x order.

    The first continuous chart on this page. Every other one here is categorical,
    because until now every published number was a share of a population. A curve
    earns its place only when the *shape* is the finding: where two lines separate,
    and where one of them flattens.

    ``rules`` = ``[(y, label)]`` draws a dashed horizontal line, for the level a
    reader is asked to compare against. ``marks`` = ``[(x, label)]`` drops a thin
    vertical at a named position. Both take their values in data units and neither
    is computed here: this function draws, it does not decide what is worth marking.

    Scaling starts at zero on both axes. A curve on a cropped axis exaggerates,
    and the whole point of the chart is that the gap between two lines is honest.
    """
    series = [s for s in series if s[1]]
    if not series:
        return ""
    width, height = 620, 250
    pad_l, pad_t, pad_b = 54, 26 if title else 10, 42
    pad_r = max(12, math.ceil(_text_w(max((s[0] for s in series), key=len), 11) + 16))
    x_max = max(float(x) for s in series for x, _ in s[1]) or 1.0
    y_max = max(float(y) for s in series for _, y in s[1])
    y_max = max(y_max, *(float(r[0]) for r in rules)) if rules else y_max
    y_max = y_max or 1.0
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b

    def px(x):
        return pad_l + plot_w * float(x) / x_max

    def py(y):
        return pad_t + plot_h * (1.0 - float(y) / y_max)

    o = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
         f'role="img" aria-label="{esc(title or "line chart")}">']
    if title:
        o.append(f'<text x="{pad_l}" y="16" font-size="12" fill="#616161">'
                 f'{esc(title)}</text>')
    # Frame first, so every line and label paints over it.
    o.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" '
             f'y2="{pad_t + plot_h}" stroke="#e0e0e0"/>'
             f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" '
             f'stroke="#e0e0e0"/>')
    for frac in (0.0, 0.5, 1.0):
        y = py(y_max * frac)
        o.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" font-size="11" fill="#6d6d6d" '
                 f'text-anchor="end">{_axis_num(y_max * frac)}</text>')
    for frac in (0.0, 0.5, 1.0):
        x = px(x_max * frac)
        anchor = "start" if frac == 0.0 else "end" if frac == 1.0 else "middle"
        o.append(f'<text x="{x:.1f}" y="{pad_t + plot_h + 16}" font-size="11" '
                 f'fill="#6d6d6d" text-anchor="{anchor}">{_axis_num(x_max * frac)}</text>')
    for y_val, label in rules:
        y = py(y_val)
        o.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
                 f'stroke="#bdbdbd" stroke-dasharray="3 3"/>'
                 # Right-anchored: a rule is drawn where a curve is heading, so
                 # the left of it is the busiest part of the plot.
                 f'<text x="{pad_l + plot_w - 4}" y="{y - 5:.1f}" font-size="11" '
                 f'fill="#6d6d6d" text-anchor="end">{esc(label)}</text>')
    for x_val, label in marks:
        x = px(x_val)
        o.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + plot_h}" '
                 f'stroke="#bdbdbd" stroke-dasharray="2 3"/>'
                 f'<text x="{x + 4:.1f}" y="{pad_t + 11}" font-size="11" fill="#6d6d6d">'
                 f'{esc(label)}</text>')
    # Two lines that finish at the same value would print their labels on top of
    # each other, which is exactly what happens when one order catches the other
    # up. Push them apart, in the order they end, before anything is drawn.
    ends = sorted(range(len(series)), key=lambda i: py(series[i][1][-1][1]))
    label_y, floor = {}, None
    for i in ends:
        y = py(series[i][1][-1][1]) + 4
        y = y if floor is None else max(y, floor + 13)
        label_y[i], floor = y, y
    for i, (label, points, colour) in enumerate(series):
        d = " ".join(f"{'M' if j == 0 else 'L'}{px(x):.1f},{py(y):.1f}"
                     for j, (x, y) in enumerate(points))
        o.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="2" '
                 f'stroke-linejoin="round"/>'
                 f'<text x="{px(points[-1][0]) + 6:.1f}" y="{label_y[i]:.1f}" '
                 f'font-size="11" fill="{colour}">{esc(label)}</text>')
    if x_title:
        o.append(f'<text x="{pad_l + plot_w / 2:.0f}" y="{height - 6}" font-size="11" '
                 f'fill="#616161" text-anchor="middle">{esc(x_title)}</text>')
    if y_title:
        o.append(f'<text x="12" y="{pad_t + plot_h / 2:.0f}" font-size="11" fill="#616161" '
                 f'text-anchor="middle" transform="rotate(-90 12 '
                 f'{pad_t + plot_h / 2:.0f})">{esc(y_title)}</text>')
    o.append("</svg>")
    return "\n".join(o)
