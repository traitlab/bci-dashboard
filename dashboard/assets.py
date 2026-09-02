"""Presentation layer: CSS, JS, inline SVG, tables. Stdlib only, no network,
no CDN, no data reads.

``_BASE_CSS`` is vendored (not imported, to avoid pulling numpy/scipy/pandas)
from labelfirst's report substrate
(``labelfirst/src/labelfirst/eval/report/_html.py``, ``_CSS``), extended by
``_EXTRA_CSS``. Strict subset: retained rules are byte-identical, unused ones
dropped, so an upstream change needs manual reapply, not copy-paste. ``_JS``
is not vendored: this page needs its own client-side sort/filter, not
labelfirst's chart tooltips.
"""

from __future__ import annotations

import html
import math
import re
from string import Template

# --- vendored from labelfirst.eval.report._html._CSS -----------------------
_BASE_CSS = """\
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:#1a1a1a;background:#f8f9fa;line-height:1.5;
  max-width:780px;margin:0 auto;padding:32px 24px 64px;
}
h1{font-size:1.6rem;font-weight:700;margin-bottom:4px;color:#212121}
.subtitle{font-size:0.85rem;color:#757575;margin-bottom:8px}
section{margin-bottom:32px}
section h2{font-size:1.05rem;font-weight:600;color:#424242;margin-bottom:12px;
  border-bottom:1px solid #e0e0e0;padding-bottom:4px}
table{
  width:100%;border-collapse:collapse;font-size:0.85rem;margin-bottom:8px;
}
th{
  text-align:left;padding:8px 10px;background:#f5f5f5;
  border-bottom:2px solid #e0e0e0;font-weight:600;color:#424242;
}
td{padding:7px 10px;border-bottom:1px solid #eeeeee}
tr:hover td{background:#f8f9fa}
svg{display:block;margin:0 auto 16px}
details{margin-top:8px}
summary{
  cursor:pointer;font-size:0.9rem;font-weight:600;color:#1565c0;
  padding:6px 0;
}
summary:hover{text-decoration:underline}
@media(max-width:640px){
  body{padding:16px 12px 40px}
  svg{width:100%!important;height:auto!important}
}
@media print{
  body{background:#fff;max-width:none;padding:0}
  summary{color:#333}
}
"""

# --- dashboard-specific additions -----------------------------------------
_EXTRA_CSS = """\
body{max-width:1120px}
h1{margin-bottom:2px}
.intro{font-size:0.95rem;color:#424242;margin:10px 0 22px}
/* Sits under the headline grid, not beside it: the region mismatch applies to
   all four numbers at once, so a per-metric footnote would repeat it four times
   and still read as optional. */
.caveat{font-size:0.85rem;color:#5d4037;background:#fbf3ec;border-left:3px solid #bf6a34;
  border-radius:0 4px 4px 0;padding:11px 14px;margin:14px 0 0}
.caveat strong{color:#3e2723}
/* Second paragraph needs its own top margin: the reset above zeroes p margins. */
.caveat p+p{margin-top:8px}
/* Two fixed columns, not a wrapping flex row: the four headline numbers are a
   2x2 grid of question x weighting, and a reader who sees them in one long row
   reads them as four unrelated figures. Collapses to one column under 640px. */
.hero{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:6px}
.hero .metric{
  background:#fff;border:1px solid #e0e0e0;border-radius:8px;
  padding:14px 18px 16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
.hero .metric.first{border-color:#90caf9;background:#f3f9ff}
.hero .metric .e{font-size:0.68rem;font-weight:700;letter-spacing:0.07em;
  text-transform:uppercase;color:#1565c0;margin-bottom:6px}
.hero .metric .v{font-size:2rem;font-weight:700;color:#212121;line-height:1.1}
.hero .metric .l{font-size:0.86rem;font-weight:600;color:#37474f;margin-top:6px}
/* #6d6d6d, not a lighter grey: this is the line that explains every headline
   number, and it sits on white and on the tinted first card. It clears 4.5:1 on
   both (5.17 and 4.88) and still reads a step quieter than the #616161 label. */
.hero .metric .n{font-size:0.72rem;color:#6d6d6d;margin-top:4px}
.hero .metric .row{display:flex;align-items:center;gap:10px;justify-content:space-between}
.note{font-size:0.82rem;color:#616161;margin-top:10px}
.note strong{color:#424242}
.ask{font-size:0.88rem;color:#37474f;margin-bottom:12px}
.ask b{color:#1a1a1a}
.warn{
  background:#fff8e1;border:1px solid #ffe082;border-radius:6px;
  padding:12px 16px;font-size:0.83rem;color:#5d4037;margin:12px 0;
}
.rec{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;
  padding:10px 14px;font-size:0.85rem;color:#1b5e20;margin-top:10px}
details.panel{
  background:#fff;border:1px solid #e0e0e0;border-radius:8px;
  margin:0 0 14px;padding:4px 20px 4px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
details.panel>summary{font-size:0.95rem;color:#0d47a1;padding:12px 0}
details.panel[open]>summary{border-bottom:1px solid #f0f0f0;margin-bottom:4px}
.pbody{padding:8px 0 16px}
.controls{display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.controls input,.controls select{
  font:inherit;font-size:0.85rem;padding:6px 10px;
  border:1px solid #cfd8dc;border-radius:6px;background:#fff;
}
.controls .count{font-size:0.8rem;color:#757575}
.controls .showall{font-size:0.85rem;color:#37474f;display:flex;align-items:center;gap:6px}
th.sortable{cursor:pointer;user-select:none;white-space:nowrap}
th.sortable:focus-visible{outline:2px solid #1565c0;outline-offset:-2px}
/* The arrow is the only thing telling the reader these headings sort, so it has
   to survive the #f5f5f5 header fill: 4.75:1 here against 1.72:1 before. */
th.sortable:after{content:" \\2195";color:#6d6d6d;font-size:0.75rem}
th.sortable.asc:after{content:" \\2191";color:#1565c0}
th.sortable.desc:after{content:" \\2193";color:#1565c0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.sp{font-style:italic}
.tag{
  display:inline-block;padding:2px 8px;border-radius:4px;
  font-size:0.74rem;font-weight:700;white-space:nowrap;
}
.tag.reliable{background:#e8f5e9;color:#2e7d32}
.tag.adequate{background:#e3f2fd;color:#1565c0}
.tag.ranking{background:#ede7f6;color:#5e35b1}
/* The most common badge on the page, so its contrast matters most; #e65100 on this fill was 3.46:1, #bf360c is 5.11:1. */
.tag.unmeasured{background:#fff3e0;color:#bf360c}
.tag.hard{background:#ffebee;color:#c62828}
.tag.unreachable{background:#eceff1;color:#455a64}
/* Sits directly above/below the table it explains, so a status stays legible
   without leaving the table. Text colour matches .todo li, already used on
   this card background elsewhere on the page. */
.status-legend{list-style:none;font-size:0.82rem;color:#424242;
  margin:8px 0 14px;display:flex;flex-direction:column;gap:5px}
.status-legend li{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
/* The vocabulary panel: one definition per row, so a reader looking up one
   word does not read the other five to find it. */
.terms{list-style:none;font-size:0.86rem;color:#424242}
.terms li{margin:8px 0;padding-left:12px;border-left:2px solid #e0e0e0}
.todo{list-style:none;font-size:0.86rem;color:#424242}
.todo li{margin:7px 0;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.todo .n{font-weight:700;color:#212121;font-variant-numeric:tabular-nums}
tr.hidden{display:none}
.prov{font-size:0.8rem;color:#616161}
.prov li{margin:5px 0 5px 18px}
.prov code{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.74rem;
  background:#f5f5f5;padding:1px 4px;border-radius:3px;
}
section.grp{margin:38px 0 34px}
section.grp>h2{
  font-size:1.15rem;font-weight:700;color:#212121;
  border-bottom:2px solid #d5dde5;padding-bottom:6px;margin-bottom:4px;
}
.lede{font-size:0.86rem;color:#546e7a;margin:0 0 14px}
/* Contrast override, not a restyle. #757575 on this background is 4.37:1, under the
   4.5:1 WCAG AA floor for text this size, and the subtitle is the only line on the
   page carrying the snapshot date and the model tag. The rule it overrides is inside
   the vendored block above, which stays byte-identical to labelfirst's. */
.subtitle{color:#6d6d6d}
/* A sub-heading inside a panel body, separating the count table from the photo
   table since they answer different questions. */
h3.sub{font-size:0.95rem;font-weight:700;color:#37474f;margin:22px 0 8px}
/* A photo key is long and only ever copied, never read as prose. */
code.key{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.72rem;
  color:#37474f;word-break:break-all}

.tscroll{overflow-x:auto}
/* Every panel carries an id, so a panel is linkable and has to be findable
   once the browser scrolls to it. */
details.panel:target>summary{background:#e3f2fd}

/* The 2x2 headline grid has no room for two columns on a phone. The vendored
   block's own 640px query stays byte-identical, so the override lives here. */
@media(max-width:640px){
  .hero{grid-template-columns:1fr}
}
"""

CSS = _BASE_CSS + _EXTRA_CSS

# Named once so the JS and the Python that renders the elements cannot drift.
_TABLE_ID = "species-table"
_INPUT_ID = "species-filter"
_SELECT_ID = "status-filter"
_COUNT_ID = "species-count"
_THIN_ID = "show-thin"

# Client-side sort + filter, vanilla. string.Template, not an f-string: the
# body is mostly JS braces an f-string would need escaped.
JS = Template("""\
(function(){
  var table=document.getElementById('$table_id');
  if(!table) return;
  var tbody=table.tBodies[0];
  var rows=Array.prototype.slice.call(tbody.rows);
  var q=document.getElementById('$input_id');
  var sel=document.getElementById('$select_id');
  var count=document.getElementById('$count_id');
  // Rows a caller marked data-thin start hidden. Any deliberate filter
  // overrides that -- a typed needle, or a chosen status. Otherwise picking
  // "too few labels to judge", the status those rows mostly carry, would empty
  // the table and read as a broken page. Absent checkbox means the caller
  // marked nothing, so everything shows; that is the older behaviour.
  var thin=document.getElementById('$thin_id');

  function apply(){
    var needle=(q.value||'').trim().toLowerCase();
    var want=sel?sel.value:'all';
    var showThin=thin?thin.checked:true;
    var shown=0;
    rows.forEach(function(r){
      // The needle is matched against the first cell, the species name as it
      // is shown. A row attribute repeating it shipped ~7KB of duplicate text.
      var hay=(r.cells[0]?r.cells[0].textContent:'').toLowerCase();
      var ok=(!needle||hay.indexOf(needle)>=0)&&
             (want==='all'||(r.getAttribute('data-status')||'')===want)&&
             (showThin||needle||want!=='all'||
              r.getAttribute('data-thin')!=='1');
      r.classList.toggle('hidden',!ok);
      if(ok) shown++;
    });
    // A bare "0 of 186" over an empty table leaves the reader wondering whether
    // the page broke. Say what happened instead.
    count.textContent=shown?(shown+' of '+rows.length+' species shown')
                           :'No species matches that filter.';
  }

  function key(cell){
    var v=cell.getAttribute('data-sort');
    if(v===null){
      var inner=cell.querySelector('[data-sort]');
      v=inner?inner.getAttribute('data-sort'):cell.textContent.trim();
    }
    return v;
  }

  var heads=Array.prototype.slice.call(table.tHead.rows[0].cells);
  heads.forEach(function(th,idx){
    if(!th.classList.contains('sortable')) return;
    // Headings need a tab stop and role="button" so keyboard and screen-reader
    // users can reach sort, which the page otherwise says to reach only by click.
    th.tabIndex=0;
    th.setAttribute('role','button');
    th.addEventListener('keydown',function(e){
      if(e.key==='Enter'||e.key===' '){ e.preventDefault(); th.click(); }
    });
    th.addEventListener('click',function(){
      var dir=th.classList.contains('desc')?'asc':'desc';
      heads.forEach(function(o){
        o.classList.remove('asc','desc');
        o.removeAttribute('aria-sort');
      });
      th.classList.add(dir);
      th.setAttribute('aria-sort',dir==='asc'?'ascending':'descending');
      rows.slice().sort(function(a,b){
        var x=key(a.cells[idx]),y=key(b.cells[idx]);
        var nx=parseFloat(x),ny=parseFloat(y);
        var c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:String(x).localeCompare(String(y));
        return dir==='asc'?c:-c;
      }).forEach(function(r){tbody.appendChild(r);});
    });
  });

  q.addEventListener('input',apply);
  if(sel) sel.addEventListener('change',apply);
  if(thin) thin.addEventListener('change',apply);
  apply();
})();

// Printing. Only two panels are open by default, so printing the page as it sits
// would hand someone a sheet of headings. Open everything for the print, then put
// it back, and keep this out of the block above, which returns early when there is
// no species table. A reader who prints from a browser without these events still
// gets whatever they had open, which is the old behaviour, not a worse one.
(function(){
  var forced=[];
  function expand(){
    forced=[];
    Array.prototype.forEach.call(document.querySelectorAll('details:not([open])'),
      function(d){ forced.push(d); d.open=true; });
  }
  function restore(){
    forced.forEach(function(d){ d.open=false; });
    forced=[];
  }
  window.addEventListener('beforeprint',expand);
  window.addEventListener('afterprint',restore);
  // Safari fires no print events; matchMedia is the path that works there.
  if(window.matchMedia){
    var mq=window.matchMedia('print');
    var onChange=function(e){ e.matches?expand():restore(); };
    if(mq.addEventListener) mq.addEventListener('change',onChange);
    else if(mq.addListener) mq.addListener(onChange);
  }
  // A jump link lands on a closed panel otherwise: :target styles it but the
  // body stays collapsed, so the reader arrives at a heading and nothing else.
  function openHash(){
    if(!location.hash) return;
    var el=null;
    try{ el=document.querySelector(location.hash); }catch(e){ return; }
    if(el&&el.tagName==='DETAILS'){ el.open=true; el.scrollIntoView(); }
  }
  window.addEventListener('hashchange',openHash);
  openHash();
})();
""").substitute(table_id=_TABLE_ID, input_id=_INPUT_ID, select_id=_SELECT_ID,
                count_id=_COUNT_ID, thin_id=_THIN_ID)


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
    """A stable id from display text: text before the first colon, lowercased,
    non-alphanumerics to hyphens, first eight words.

    Derived so an anchor cannot drift from its heading. Colon split matters:
    summaries carry live numbers ("...: 412 frames") that change every
    snapshot, so ``panel`` rejects a digit-bearing id and requires an
    explicit ``anchor``.
    """
    head = re.sub(r"<[^>]+>", "", str(text)).split(":")[0]
    words = re.sub(r"[^a-z0-9]+", " ", head.lower()).split()
    return "-".join(words[:8])


def panel(summary, ask, body, *, open_=False, anchor=None):
    """A collapsible panel. ``summary`` must stand alone closed; ``ask`` says
    what to do with what's inside. ``anchor`` overrides the derived id,
    required when ``summary`` carries a live number.
    """
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
    not a label: that is what makes a closed page scannable. No jump list, the
    summaries below are the contents.
    """
    return (f'<section class="grp" id="{slug(title)}"><h2>{title}</h2>'
            f'<p class="lede">{lede}</p>\n{panels}</section>')


def hero(cards):
    """The band of big numbers a page opens with. ``cards`` is
    ``[(eyebrow, value, label, note), ...]``, leading card first. Grid CSS is
    written against the ``.metric`` markup.
    """
    out = ['<div class="hero">']
    for i, (eyebrow, value, label, note) in enumerate(cards):
        out.append(f'<div class="metric{" first" if i == 0 else ""}">'
                   f'<div class="e">{eyebrow}</div>'
                   f'<div class="row"><div class="v">{value}</div></div>'
                   f'<div class="l">{label}</div>'
                   f'<div class="n">{note}</div></div>')
    out.append("</div>")
    return "".join(out)


def table(headers, rows, *, tid=None, sortable_from=None, row_attrs=None):
    """headers = [(text, is_numeric)]; rows = [[cell_html, ...]]."""
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
            c = ' class="num"' if headers[i][1] else ""
            out.append(f"<td{c}>{cell}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    # Scrolls inside its own box. Otherwise the 7-column table sets the page
    # width on a phone and every paragraph scrolls sideways with it.
    return '<div class="tscroll">' + "\n".join(out) + "</div>"


def filterable_table(headers, rows, *, options, row_attrs=None, thin_label=None):
    """A search/filter strip followed by a sortable table. The page has
    exactly one; element ids use the ``_TABLE_ID`` constants, not literals.
    """
    # No options means no status to filter on, so no select: rendering one
    # holding nothing but "every status" offers the reader a control that
    # cannot change what the table shows. The JS treats an absent select as
    # "every status", which is the only thing it could have said anyway.
    if options:
        opts = "".join(
            f'<option value="{esc(value)}">{esc(label)}</option>' for value, label in options
        )
        select = (f'<select id="{_SELECT_ID}" aria-label="filter by status">'
                  f'<option value="all">every status</option>{opts}</select>')
    else:
        select = ""
    # ``thin_label`` turns on the show-everything checkbox, and the caller marks
    # the rows it hides with ``data-thin="1"`` in ``row_attrs``. Without a label
    # no checkbox is rendered and no row is hidden, so a caller that marks
    # nothing gets the table it always got.
    if thin_label:
        toggle = (f'<label class="showall"><input type="checkbox" id="{_THIN_ID}"> '
                  f'{thin_label}</label>')
    else:
        toggle = ""
    controls = (
        '<div class="controls">'
        f'<input id="{_INPUT_ID}" type="search" placeholder="filter species&hellip;" size="28" '
        f'aria-label="filter species">'
        f"{select}{toggle}<span class=\"count\" id=\"{_COUNT_ID}\"></span></div>"
    )
    return controls + table(headers, rows, tid=_TABLE_ID, sortable_from=0,
                            row_attrs=row_attrs)


def funnel_list(steps: list[tuple[int, str]]) -> str:
    """A count-then-label list: ``steps`` is ``[(count, label), ...]``,
    outermost first. Reuses the to-do-list markup (``.todo``/``.n``) so a
    photo-to-frame funnel needs no CSS of its own.
    """
    rows = "".join(f'<li><span class="n">{count:,}</span> {esc(label)}</li>'
                   for count, label in steps)
    return f'<ul class="todo">{rows}</ul>'


def status_tag(cls: str, label: str) -> str:
    """Render a status tag. The explanation is not repeated per row: a
    former hover-icon ``title=`` duplicated ~40KB of markup across a
    186-row table. Callers render each sentence once via ``status_legend``
    instead."""
    return f'<span class="tag {esc(cls)}">{esc(label)}</span>'


def strip_comments(text: str) -> str:
    """CSS and JS with maintainer comments stripped, for the built page.
    Inlining them uncut shipped 3.6 KB of notes to every reader. JS only
    drops lines *starting* with ``//``, so ``//`` inside a string survives.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^[ \t]*//.*$", "", text, flags=re.M)
    return re.sub(r"\n{2,}", "\n", text).strip()


def status_legend(entries: list[tuple[str, str, str]]) -> str:
    """The status explanations, once, instead of per row. ``entries`` is
    ``[(css_class, label, reason), ...]``, in read order."""
    items = "".join(
        f'<li><span class="tag {esc(cls)}">{esc(label)}</span> {esc(reason)}</li>'
        for cls, label, reason in entries
    )
    return f'<ul class="status-legend">{items}</ul>'


# --- inline SVG (hand-written in labelfirst's report idiom: no library, no CDN) ---
_NARROW = set(" .,;:'!|iljtfr()[]·")
_WIDE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw%@")


def _text_w(text: str, font_px: float) -> float:
    """Upper bound on the rendered width of ``text`` at ``font_px``. No glyph
    measurement is possible: one file, no library, ``system-ui`` varies by
    machine. Three character classes plus 0.26em per string for side
    bearings, times 1.06, calibrated against ``getComputedTextLength`` on 14
    of this page's labels under SF NS (Segoe UI/Roboto run narrower).

    1.06 is not measured headroom, only 14 of 59 labels were checked. It
    leans high: undershooting clips silently, and a clipped label ships
    (five once read "1,856 cr" despite passing every numeric check).
    """
    em = 0.26 + sum(0.28 if c in _NARROW else 0.72 if c in _WIDE else 0.60 for c in text)
    return 1.06 * em * font_px


def svg_hbar(rows, *, title=""):
    """Horizontal bars. ``rows`` = [(label, frac, right_text, color)].
    ``right_w`` grows to fit the longest value label rather than truncating
    (SVG clips, no CSS can rescue it). Geometry is fixed, not parameterised.
    """
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
        # The tick carries nothing (every value is printed at its bar end), so it
        # stays faint at 1.72:1. The number under it is read, so 4.5:1 and 11px.
        out.append(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 4}" '
                   f'stroke="#bdbdbd"/>'
                   f'<text x="{x:.1f}" y="{axis_y + 17}" font-size="11" fill="#6d6d6d" '
                   f'text-anchor="middle">{t}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def svg_weight_pair(rows, *, label_a, label_b):
    """Two full-width bars over the same bands, split by a different weight
    each. ``rows`` = ``[(band, share_a, share_b, note, colour)]``, shares
    summing to 1 per column, so the reader sees the weight move without
    arithmetic.

    Each column asserts sum to 1: a wrong denominator draws a short bar, not
    a wrong number, which no recompute check would catch. ``pad_l`` fits the
    longer row label; labels are right-anchored, so an overlong one silently
    loses its first character off the viewBox.
    """
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
            # Below this a two-character percentage collides with the band edges,
            # so the number lives only in the key underneath.
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
