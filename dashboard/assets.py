"""Presentation layer for the model-health dashboard: CSS, JS, inline SVG, tables.

Nothing here reads data or computes a number. Stdlib only, no network, no CDN.

``_BASE_CSS`` is vendored from labelfirst's report substrate
(``labelfirst/src/labelfirst/eval/report/_html.py``, ``_CSS``) so the two
reports look like one family, then extended by ``_EXTRA_CSS`` below. It is
vendored rather than imported because ``import labelfirst`` pulls
numpy/scipy/scikit-learn/pandas, and this page must render from the stdlib
alone.

It is a *strict subset*, not a verbatim copy: every retained rule is
byte-identical, and the rules for elements this page has none of (verdict bar,
pass/refuted badge, design details, chart grid, tooltips, key-number chips) are
dropped. A future upstream ``_CSS`` change therefore cannot be picked up by
plain copy-paste; the prune has to be reapplied.

``_JS`` is NOT vendored: labelfirst's script only drives tooltips for its
trajectory chart. This page needs client-side sort and filter over the
per-species table instead.
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
.card{
  background:#fff;border:1px solid #e0e0e0;border-radius:8px;
  padding:20px 24px;margin-bottom:20px;
  box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
.card h2{
  font-size:1.05rem;font-weight:600;color:#424242;margin-bottom:12px;
  border-bottom:1px solid #f0f0f0;padding-bottom:6px;
}
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
.footer{
  margin-top:40px;padding-top:12px;border-top:1px solid #e0e0e0;
  font-size:0.75rem;color:#bdbdbd;text-align:center;
}
@media(max-width:640px){
  body{padding:16px 12px 40px}
  svg{width:100%!important;height:auto!important}
}
@media print{
  body{background:#fff;max-width:none;padding:0}
  .card{box-shadow:none;border:1px solid #ccc;break-inside:avoid}
  .footer{display:none}
  summary{color:#333}
}
"""

# --- dashboard-specific additions -----------------------------------------
_EXTRA_CSS = """\
body{max-width:1120px}
h1{margin-bottom:2px}
.intro{font-size:0.95rem;color:#424242;margin:10px 0 22px}
.terms{font-size:0.83rem;color:#546e7a;background:#f4f7f9;border-left:3px solid #b0bec5;
  border-radius:0 4px 4px 0;padding:10px 14px;margin:0 0 16px}
.terms b{color:#263238}
/* Sits under the headline grid, not beside it: the region mismatch applies to
   all four numbers at once, so a per-metric footnote would repeat it four times
   and still read as optional. */
.caveat{font-size:0.85rem;color:#5d4037;background:#fbf3ec;border-left:3px solid #bf6a34;
  border-radius:0 4px 4px 0;padding:11px 14px;margin:14px 0 0}
.caveat strong{color:#3e2723}
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
th.sortable{cursor:pointer;user-select:none;white-space:nowrap}
/* The arrow is the only thing telling the reader these headings sort, so it has
   to survive the #f5f5f5 header fill: 4.75:1 here against 1.72:1 before. */
th.sortable:after{content:" \\2195";color:#6d6d6d;font-size:0.75rem}
th.sortable.asc:after{content:" \\2191";color:#1565c0}
th.sortable.desc:after{content:" \\2193";color:#1565c0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.sp{font-style:italic}
svg.spark{display:inline-block;margin:0;vertical-align:middle}
.nospark{font-size:0.72rem;color:#6d6d6d}
.tag{
  display:inline-block;padding:2px 8px;border-radius:4px;
  font-size:0.74rem;font-weight:700;white-space:nowrap;
}
.info-tip{
  display:inline-flex;align-items:center;justify-content:center;
  width:1rem;height:1rem;border-radius:999px;
  background:#eceff1;color:#546e7a;font-size:0.66rem;
  font-weight:700;cursor:help;flex:0 0 auto;
}
.tag.reliable{background:#e8f5e9;color:#2e7d32}
.tag.adequate{background:#e3f2fd;color:#1565c0}
.tag.ranking{background:#ede7f6;color:#5e35b1}
/* 78 of the 169 species carry this badge, which makes it the most common one on
   the page; #e65100 on this fill was 3.46:1, #bf360c is 5.11:1. */
.tag.unmeasured{background:#fff3e0;color:#bf360c}
.tag.hard{background:#ffebee;color:#c62828}
.tag.unreachable{background:#eceff1;color:#455a64}
/* Sits directly above/below the table it explains, so the reader learns what
   a status means without leaving the table -- same job the per-row title=
   used to do, done once instead of 186 times. Text colour matches .todo li,
   already used on this same white card background elsewhere on the page. */
.status-legend{list-style:none;font-size:0.82rem;color:#424242;
  margin:8px 0 14px;display:flex;flex-direction:column;gap:5px}
.status-legend li{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.rule-card{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:10px 0 4px}
.chip{
  display:inline-flex;align-items:center;gap:6px;padding:4px 10px;
  border-radius:999px;font-size:0.78rem;font-weight:600;
  border:1px solid #cfd8dc;background:#eceff1;color:#546e7a;
}
.chip.on{background:#e8f5e9;border-color:#a5d6a7;color:#2e7d32}
.chip .dot{width:0.55rem;height:0.55rem;border-radius:999px;background:#90a4ae;flex:0 0 auto}
.chip.on .dot{background:#2e7d32}
.rule-badge{
  display:inline-block;padding:4px 12px;border-radius:6px;
  font-size:0.8rem;font-weight:700;
}
.rule-badge.wait{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7}
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
/* A sub-heading inside a panel body: the send-first panel now carries a table
   of counts and a table of photos, and they are answers to different questions. */
h3.sub{font-size:0.95rem;font-weight:700;color:#37474f;margin:22px 0 8px}
/* A photo key is long and only ever copied, never read as prose. */
code.key{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.72rem;
  color:#37474f;word-break:break-all}

/* Jump list under each section band: 17 panels over 3 sections is more than a
   reader will scroll blind, and the ids also make one panel linkable. */
.jump{list-style:none;display:flex;flex-wrap:wrap;gap:6px 14px;margin:8px 0 18px;padding:0}
.jump a{font-size:0.83rem;color:#1565c0;text-decoration:none;border-bottom:1px solid #bbdefb}
.jump a:hover,.jump a:focus{border-bottom-color:#1565c0}
.tscroll{overflow-x:auto}
/* An anchored panel has to be findable once the jump link scrolls to it. */
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

  function apply(){
    var needle=(q.value||'').trim().toLowerCase();
    var want=sel.value;
    var shown=0;
    rows.forEach(function(r){
      // Fall back to the first cell when a caller ships no data-species: an
      // absent attribute would otherwise make every needle a miss and blank the
      // table on the first keystroke.
      var hay=r.getAttribute('data-species');
      if(hay===null) hay=(r.cells[0]?r.cells[0].textContent:'').toLowerCase();
      var ok=(!needle||hay.indexOf(needle)>=0)&&
             (want==='all'||(r.getAttribute('data-status')||'')===want);
      r.classList.toggle('hidden',!ok);
      if(ok) shown++;
    });
    count.textContent=shown+' of '+rows.length+' species shown';
  }

  // Sort key: the cell's own data-sort, else a descendant's, else its text.
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
    th.addEventListener('click',function(){
      var dir=th.classList.contains('desc')?'asc':'desc';
      heads.forEach(function(o){o.classList.remove('asc','desc');});
      th.classList.add(dir);
      rows.slice().sort(function(a,b){
        var x=key(a.cells[idx]),y=key(b.cells[idx]);
        var nx=parseFloat(x),ny=parseFloat(y);
        var c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:String(x).localeCompare(String(y));
        return dir==='asc'?c:-c;
      }).forEach(function(r){tbody.appendChild(r);});
    });
  });

  q.addEventListener('input',apply);
  sel.addEventListener('change',apply);
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
                count_id=_COUNT_ID)


def esc(s: object) -> str:
    """HTML-escape any value (same role as labelfirst's ``_esc``)."""
    return html.escape(str(s))


def cap(s: str) -> str:
    """Capitalise a scientific name for display. The CSVs hold names lowercased
    because that is the join key against the GBIF and WCVP backbones, but a
    binomial is written with the genus capitalised, so every render site goes
    through here rather than printing the key."""
    return s[:1].upper() + s[1:]


def pctf(x, nd=1):
    return "n/a" if x is None else f"{100.0 * x:.{nd}f}%"


# --- structure ---
def slug(text: str) -> str:
    """A stable id from display text: the part before the first colon, lowercased,
    non-alphanumerics collapsed to hyphens, first eight words kept.

    Derived from the text rather than passed in at the call site because every
    summary and heading already stands alone as a label -- a hand-written id
    would be a second name for the same thing, free to drift from the first.
    The colon split keeps the id short: summaries read "What to send first:
    412 frames in the long tail", and the count changes every snapshot while
    the anchor must not.

    A summary whose live numbers sit before any colon cannot be slugged safely,
    so ``panel`` rejects a digit-bearing id and asks for an explicit ``anchor``.
    """
    head = re.sub(r"<[^>]+>", "", str(text)).split(":")[0]
    words = re.sub(r"[^a-z0-9]+", " ", head.lower()).split()
    return "-".join(words[:8])


def panel(summary, ask, body, *, open_=False, anchor=None):
    """A collapsible panel. ``summary`` must stand alone on a closed page and
    ``ask`` is the one sentence saying what to do with what is inside.

    ``anchor`` overrides the id derived from ``summary``, and is required when
    the summary states a live number before its first colon.
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
    """A named group of panels: a heading band, one orienting line, then the panels.

    ``panels`` is already-rendered panel HTML. The band is what makes a long page
    scannable when closed, so it carries the group's question, not a label.
    """
    # Read back out of the rendered panels, not passed in: a hand-kept list is
    # one more thing to forget when a panel is added.
    links = "".join(
        f'<li><a href="#{pid}">{esc(re.sub(r"<[^>]+>", "", summ).split(":")[0])}</a></li>'
        for pid, summ in re.findall(
            r'<details class="panel" id="([^"]+)"[^>]*><summary>(.*?)</summary>', panels)
    )
    nav = f'<ul class="jump">{links}</ul>' if links else ""
    return (f'<section class="grp" id="{slug(title)}"><h2>{title}</h2>'
            f'<p class="lede">{lede}</p>{nav}\n{panels}</section>')


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


def filterable_table(headers, rows, *, options, row_attrs=None):
    """A search/filter strip followed by a sortable table.

    ``table_id``/``input_id``/``select_id``/``count_id`` (the four element
    ids the JS above looks up), ``placeholder``, ``input_label``,
    ``select_label``, ``all_label`` and ``sortable_from`` used to be keyword
    params here, but no caller had ever overridden any of them -- the page
    has exactly one filterable table. Dropped and inlined; the four ids stay
    as the shared ``_TABLE_ID``/etc. constants above so the JS coupling is
    explicit rather than two copies of the same literal staying in sync by
    accident.
    """
    opts = "".join(
        f'<option value="{esc(value)}">{esc(label)}</option>' for value, label in options
    )
    controls = (
        '<div class="controls">'
        f'<input id="{_INPUT_ID}" type="search" placeholder="filter species&hellip;" size="28" '
        f'aria-label="filter species">'
        f'<select id="{_SELECT_ID}" aria-label="filter by status">'
        f'<option value="all">every status</option>'
        f"{opts}</select><span class=\"count\" id=\"{_COUNT_ID}\"></span></div>"
    )
    return controls + table(headers, rows, tid=_TABLE_ID, sortable_from=0,
                            row_attrs=row_attrs)


def info_tip(reason: str) -> str:
    """A standalone hover-explanation icon, for attaching a denominator or
    definition to a plain number or label."""
    reason = esc(reason)
    return f'<span class="info-tip" title="{reason}" aria-label="{reason}">i</span>'


def funnel_list(steps: list[tuple[int, str]]) -> str:
    """A count-then-label list, reusing the existing to-do-list markup
    (``.todo``/``.n``) already styled for 16b's per-species counts, so a
    photo-to-frame funnel gets no CSS of its own.

    ``steps`` is ``[(count, label), ...]``, outermost first.
    """
    rows = "".join(f'<li><span class="n">{count:,}</span> {esc(label)}</li>'
                   for count, label in steps)
    return f'<ul class="todo">{rows}</ul>'


def status_tag(cls: str, label: str, *, sort_key: str | None = None) -> str:
    """Render a status tag. The explanation for each status is not repeated
    here: it used to be a per-row ``title=`` (a hover icon via ``info_tip``),
    but that stamped one of only a handful of distinct sentences onto every
    row of a 186-row table -- ~40KB of duplicated markup per page. Callers
    render the distinct sentences once via ``status_legend`` instead, next to
    the table."""
    sort = esc(sort_key if sort_key is not None else label)
    return f'<span class="tag {esc(cls)}" data-sort="{sort}">{esc(label)}</span>'


def status_legend(entries: list[tuple[str, str, str]]) -> str:
    """The status explanations, once, instead of on every row. ``entries`` is
    ``[(css_class, label, reason), ...]`` -- one line per distinct situation
    a status tag can mean, in the same order the tags are meant to be read."""
    items = "".join(
        f'<li><span class="tag {esc(cls)}">{esc(label)}</span> {esc(reason)}</li>'
        for cls, label, reason in entries
    )
    return f'<ul class="status-legend">{items}</ul>'


def threshold_card(conf_thresh: float, support_thresh: int) -> str:
    """The 'why this threshold is safe' card: two chips plus a decision badge.

    Both chips are drawn "on" together, the only state the rule ever lets
    reach the "Can wait" badge: fail either one and review-now is always the
    answer, so a single worked example next to the two live chips is enough to
    make the AND explicit without a second, contradictory example to maintain.
    """
    chip_a = (f'<span class="chip on"><span class="dot"></span>'
              f'confidence &ge; {conf_thresh:.0%}</span>')
    chip_b = (f'<span class="chip on"><span class="dot"></span>'
              f'support &ge; {support_thresh} frames</span>')
    badge = '<span class="rule-badge wait">Can wait</span>'
    return (
        f'<p class="ask">We only auto-deprioritise a frame when the model is confident '
        f'({conf_thresh:.0%}+) and we already have enough examples for that species '
        f'({support_thresh}+ frames). If either condition fails, the frame stays in the '
        'review queues above.</p>'
        f'<div class="rule-card">{chip_a}{chip_b}<span>&rarr;</span>{badge}</div>'
        '<p class="note">&ldquo;Confidence&rdquo; is the model&rsquo;s certainty for its '
        'top guess. &ldquo;Support&rdquo; is how many labelled frames that species has in '
        'this snapshot. Both chips must be green (as drawn) for the frame to wait; one '
        'grey chip and the badge reads &ldquo;Review now&rdquo; instead. The rule is graded '
        'out of sample, not on the frames that set it: which species clear the support gate '
        'is decided from <b>train</b> frames only, and the resulting error rate is measured '
        'on <b>test</b> frames only. The full page compares it against four alternatives '
        'under &ldquo;How the five candidate rules compare&rdquo;.</p>'
    )


# --- inline SVG (hand-written in labelfirst's report idiom: no library, no CDN) ---
_NARROW = set(" .,;:'!|iljtfr()[]·")
_WIDE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw%@")


def _text_w(text: str, font_px: float) -> float:
    """Upper bound on the rendered width of ``text`` at ``font_px``.

    Nothing here can measure a glyph. The page ships as one file with no
    library, and ``system-ui`` resolves to whatever the reader's machine has, so
    the true width is unknowable at build time. Three character classes plus a
    per-string 0.26em for side bearings, calibrated against
    ``getComputedTextLength`` for 14 of this page's own labels under SF NS, with
    a 1.06 factor that keeps the estimate above all 14.

    Do not read that as a headroom figure for the page. The calibration set is 14
    labels, not the 59 the page draws, and the margin on the rest is unmeasured
    per label. Treat the factor as the thing that must not be spent, not as slack
    with a known size.

    The bound leans high on purpose. Overshooting spends whitespace,
    undershooting clips the text, and a clipped label is the failure that ships:
    every numeric check on this page passed while five of them read "1,856 cr".
    Segoe UI and Roboto are the other likely resolutions and both run narrower
    than SF NS at the same size, so the headroom covers them too.
    """
    em = 0.26 + sum(0.28 if c in _NARROW else 0.72 if c in _WIDE else 0.60 for c in text)
    return 1.06 * em * font_px


def svg_hbar(rows, *, title=""):
    """Horizontal bars. ``rows`` = [(label, frac, right_text, color)].

    ``right_w`` is the room reserved for the value label, and it grows to fit
    the longest one rather than truncating it. Text past the viewBox is clipped
    by the SVG viewport, no CSS reaches inside to rescue it, and every numeric
    check on this page still passes while a label reads "1,856 cr". The bars
    keep the length ``right_w`` asked for; only the chart gets wider.

    Geometry (``width``/``row_h``/``label_w``/``right_w`` as starting values)
    used to be keyword params; no caller has ever passed a non-default one,
    so they are fixed constants below instead of unused knobs.
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
    """Two full-width bars over the same bands, each split by a different weight.

    ``rows`` = ``[(band, share_a, share_b, note, colour)]``, each set of shares
    summing to 1. The point is the comparison: the same bands in the same
    colours, so the reader sees the weight move from one bar to the other
    without doing any arithmetic.

    Both columns have to sum to 1 or the bars stop being comparable, and a
    wrong denominator would draw a short bar rather than a wrong number, which
    no recompute-and-compare check can see. So it is asserted here.

    ``pad_l`` is the room for the row labels, and it grows to fit the longer of
    the two. The labels are right-anchored against the bars, so one that does
    not fit runs off the left edge of the viewBox and loses its first character
    with no warning from any check on this page. ``width``/``bar_h``/``pad_l``
    (starting values) used to be keyword params; no caller has ever passed a
    non-default one, so they are fixed constants below instead.
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


def _scale(values, lo_px, hi_px, span=0.0):
    """Map ``values`` onto a pixel range, flat series to the middle.

    ``lo_px`` is where the smallest value sits and ``hi_px`` where the largest
    does. SVG y grows downward, so callers pass ``lo_px`` larger than ``hi_px``
    and a rising series comes back with falling y.

    ``span`` is the smallest range the axis is allowed to show. Without it a
    series that wobbles by one point fills the whole plot and reads as a
    collapse, so rates pass their own floor and counts leave it at zero.
    """
    lo, hi = min(values), max(values)
    if hi - lo < span:
        mid = (lo + hi) / 2.0
        lo, hi = mid - span / 2.0, mid + span / 2.0
    if hi - lo < 1e-12:
        mid = (lo_px + hi_px) / 2.0
        return [mid] * len(values)
    return [lo_px + (v - lo) / (hi - lo) * (hi_px - lo_px) for v in values]


def orientation_ok() -> bool:
    """A rising series must be drawn with falling y, because SVG y grows down.

    Getting this backwards flips every chart on the page while leaving every
    number on it correct, so nothing else here would catch it.
    """
    ys = _scale([1.0, 2.0], 100.0, 0.0)
    return ys[0] > ys[1] and abs(ys[0] - 100.0) < 1e-9 and abs(ys[1]) < 1e-9


def weight_pair_ok() -> bool:
    """The bigger share must be drawn wider, and a band must keep its colour.

    Same blind spot as ``orientation_ok``: swapping the two share columns, or
    reading a share off the wrong denominator, changes the picture and no
    printed number with it.
    """
    rows = [("a", 0.25, 0.75, "", "#111111"), ("b", 0.75, 0.25, "", "#222222")]
    svg = svg_weight_pair(rows, label_a="A", label_b="B")
    got = re.findall(r'<rect x="([\d.]+)" y="(\d+)" width="([\d.]+)"[^>]*fill="(#\w+)"', svg)
    top = [g for g in got if g[1] == "8"]
    if len(top) != 2 or top[0][3] != "#111111" or top[1][3] != "#222222":
        return False
    return float(top[0][2]) < float(top[1][2]) and float(top[0][0]) < float(top[1][0])


def svg_spark(values, marks=(), *, empty="no trend yet", span=0.0):
    """Sparkline. ``marks`` = indices where the model iteration changed; those
    points get a hollow ring so a model jump never reads as label drift. With
    fewer than two snapshots there is nothing to draw, so say so rather than
    render a flat line; ``empty=""`` suppresses even that, for table cells that
    would otherwise repeat the same sentence on every row.

    ``width``/``height`` used to be keyword params; the one caller has never
    passed a non-default value, so they are fixed constants below instead."""
    if len(values) < 2:
        return f'<span class="nospark">{empty}</span>' if empty else ""
    width, height = 88, 24
    xs = [3 + i * (width - 6) / (len(values) - 1) for i in range(len(values))]
    ys = _scale(values, height - 4, 4, span)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    dots = "".join(
        f'<circle cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="3.2" fill="#fff" '
        f'stroke="#c62828" stroke-width="1.8"/>' for i in marks if 0 <= i < len(values))
    # A <title> child is the browser's own tooltip. Most readers meet one of these
    # lines long before the panel that explains them, so hovering has to be enough.
    tip = (f"Oldest snapshot on the left, newest on the right, {len(values)} points. "
           f"Scaled to its own range, so its steepness is not comparable with another "
           f"line's.")
    if marks:
        tip += " A hollow red ring is a snapshot where the Pl@ntNet model changed."
    return (f'<svg class="spark" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="trend across {len(values)} snapshots, '
            f'{len(marks)} model change(s)">'
            f"<title>{tip}</title>"
            f'<polyline points="{pts}" fill="none" stroke="#1565c0" stroke-width="1.6"/>'
            f'{dots}<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="2.2" fill="#1565c0"/>'
            f"</svg>")


def svg_two_series(dates, a_vals, b_vals, marks, *, a_name, b_name,
                   a_fmt, b_fmt, a_span=0.0):
    """Two series on two independent scales, sharing the snapshot dates.

    A dashed vertical rule at every index in ``marks`` says the Pl@ntNet model
    iteration changed there. Each series is scaled to its own min and max, no
    narrower than ``a_span`` for the first one, so the shapes are comparable
    but the pixel heights are not; the end labels carry the actual values.

    ``width``/``height`` used to be keyword params; the one caller has never
    passed a non-default value, so they are fixed constants below instead.
    """
    if len(dates) < 2:
        return ""
    width, height = 620, 210
    pad_l, pad_r, pad_t, pad_b = 52, 60, 22, 40
    xs = [pad_l + i * (width - pad_l - pad_r) / (len(dates) - 1) for i in range(len(dates))]
    ya = _scale(a_vals, height - pad_b, pad_t, a_span)
    yb = _scale(b_vals, height - pad_b, pad_t)
    o = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
         f'role="img" aria-label="{esc(a_name)} and {esc(b_name)} across '
         f'{len(dates)} snapshots">',
         f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" '
         f'y2="{height - pad_b}" stroke="#e0e0e0"/>']
    for i in marks:
        o.append(f'<line x1="{xs[i]:.1f}" y1="{pad_t - 6}" x2="{xs[i]:.1f}" '
                 f'y2="{height - pad_b}" stroke="#c62828" stroke-width="1.2" '
                 f'stroke-dasharray="4 3"/>'
                 f'<text x="{xs[i]:.1f}" y="{pad_t - 10}" font-size="10" fill="#c62828" '
                 f'text-anchor="middle">new model</text>')
    for ys, col, dash, vals, show in ((ya, "#1565c0", "", a_vals, a_fmt),
                                      (yb, "#00796b", "5 3", b_vals, b_fmt)):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"'
                 + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
        for i, (x, y) in enumerate(zip(xs, ys)):
            r = 4.0 if i in marks else 2.6
            fill = "#fff" if i in marks else col
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" '
                     f'stroke="{col}" stroke-width="1.8"/>')
        o.append(f'<text x="{xs[-1] + 8:.1f}" y="{ys[-1] + 4:.1f}" font-size="10.5" '
                 f'fill="{col}">{esc(show(vals[-1]))}</text>'
                 f'<text x="{xs[0] - 8:.1f}" y="{ys[0] + 4:.1f}" font-size="10.5" '
                 f'fill="{col}" text-anchor="end">{esc(show(vals[0]))}</text>')
    for i, d in enumerate(dates):
        o.append(f'<text x="{xs[i]:.1f}" y="{height - pad_b + 15}" font-size="11" '
                 f'fill="#6d6d6d" text-anchor="middle">{esc(d)}</text>')
    o.append(f'<text x="{pad_l}" y="{height - 6}" font-size="10.5" fill="#1565c0">'
             f'&#9473; {esc(a_name)}</text>'
             f'<text x="{pad_l + 210}" y="{height - 6}" font-size="10.5" fill="#00796b">'
             f'&#9476; {esc(b_name)}</text>'
             + (f'<text x="{width - pad_r}" y="{height - 6}" font-size="10.5" '
                f'fill="#c62828" text-anchor="end">&#9711; new Pl@ntNet model</text>'
                if marks else ""))
    o.append("</svg>")
    return "\n".join(o)
