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
import re

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
.hero{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:6px}
.hero .metric{
  flex:1 1 220px;background:#fff;border:1px solid #e0e0e0;border-radius:8px;
  padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
.hero .metric.first{border-color:#90caf9;background:#f3f9ff}
.hero .metric .v{font-size:2rem;font-weight:700;color:#212121;line-height:1.1}
.hero .metric .l{font-size:0.8rem;color:#616161;margin-top:6px}
.hero .metric .n{font-size:0.72rem;color:#9e9e9e;margin-top:4px}
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
th.sortable:after{content:" \\2195";color:#bdbdbd;font-size:0.75rem}
th.sortable.asc:after{content:" \\2191";color:#1565c0}
th.sortable.desc:after{content:" \\2193";color:#1565c0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.sp{font-style:italic}
svg.spark{display:inline-block;margin:0;vertical-align:middle}
.nospark{font-size:0.72rem;color:#bdbdbd}
.tag{
  display:inline-block;padding:2px 8px;border-radius:4px;
  font-size:0.74rem;font-weight:700;white-space:nowrap;
}
.tag.reliable{background:#e8f5e9;color:#2e7d32}
.tag.adequate{background:#e3f2fd;color:#1565c0}
.tag.ranking{background:#ede7f6;color:#5e35b1}
.tag.unmeasured{background:#fff3e0;color:#e65100}
.tag.hard{background:#ffebee;color:#c62828}
.tag.unreachable{background:#eceff1;color:#455a64}
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
"""

CSS = _BASE_CSS + _EXTRA_CSS

# Client-side sort + filter for the per-species table. Vanilla, no library.
JS = """\
(function(){
  var table=document.getElementById('species-table');
  if(!table) return;
  var tbody=table.tBodies[0];
  var rows=Array.prototype.slice.call(tbody.rows);
  var q=document.getElementById('species-filter');
  var sel=document.getElementById('status-filter');
  var count=document.getElementById('species-count');

  function apply(){
    var needle=(q.value||'').trim().toLowerCase();
    var want=sel.value;
    var shown=0;
    rows.forEach(function(r){
      var ok=(!needle||(r.getAttribute('data-species')||'').indexOf(needle)>=0)&&
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
"""


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


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------
def panel(summary, ask, body, *, open_=False):
    """A collapsible panel. ``summary`` must stand alone on a closed page and
    ``ask`` is the one sentence saying what to do with what is inside."""
    return (f'<details class="panel"{" open" if open_ else ""}>'
            f"<summary>{summary}</summary>"
            f'<div class="pbody"><p class="ask">{ask}</p>{body}</div></details>')


def section(title, lede, panels):
    """A named group of panels: a heading band, one orienting line, then the panels.

    ``panels`` is already-rendered panel HTML. The band is what makes a long page
    scannable when closed, so it carries the group's question, not a label.
    """
    return (f'<section class="grp"><h2>{title}</h2>'
            f'<p class="lede">{lede}</p>\n{panels}</section>')


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
    return "\n".join(out)


# ---------------------------------------------------------------------------
# inline SVG (hand-written in labelfirst's report idiom: no library, no CDN)
# ---------------------------------------------------------------------------
def svg_hbar(rows, *, width=620, row_h=30, label_w=112, right_w=140, title=""):
    """Horizontal bars. ``rows`` = [(label, frac, right_text, color)]."""
    if not rows:
        return ""
    top = 26 if title else 8
    bar_w = width - label_w - right_w
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
        out.append(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 4}" '
                   f'stroke="#bdbdbd"/>'
                   f'<text x="{x:.1f}" y="{axis_y + 17}" font-size="10.5" fill="#9e9e9e" '
                   f'text-anchor="middle">{t}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def svg_weight_pair(rows, *, label_a, label_b, width=620, bar_h=28, pad_l=168):
    """Two full-width bars over the same bands, each split by a different weight.

    ``rows`` = ``[(band, share_a, share_b, note, colour)]``, each set of shares
    summing to 1. The point is the comparison: the same bands in the same
    colours, so the reader sees the weight move from one bar to the other
    without doing any arithmetic.

    Both columns have to sum to 1 or the bars stop being comparable, and a
    wrong denominator would draw a short bar rather than a wrong number, which
    no recompute-and-compare check can see. So it is asserted here.
    """
    if not rows:
        return ""
    for key in (1, 2):
        total = sum(float(r[key]) for r in rows)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weight column {key} sums to {total}, not 1; "
                             "the shares are against the wrong denominator")
    bar_w = width - pad_l - 10
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


def svg_spark(values, marks=(), *, width=88, height=24, empty="no trend yet", span=0.0):
    """Sparkline. ``marks`` = indices where the model iteration changed; those
    points get a hollow ring so a model jump never reads as label drift. With
    fewer than two snapshots there is nothing to draw, so say so rather than
    render a flat line; ``empty=""`` suppresses even that, for table cells that
    would otherwise repeat the same sentence on every row."""
    if len(values) < 2:
        return f'<span class="nospark">{empty}</span>' if empty else ""
    xs = [3 + i * (width - 6) / (len(values) - 1) for i in range(len(values))]
    ys = _scale(values, height - 4, 4, span)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    dots = "".join(
        f'<circle cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="3.2" fill="#fff" '
        f'stroke="#c62828" stroke-width="1.8"/>' for i in marks if 0 <= i < len(values))
    # A <title> child is the browser's own tooltip. These lines are drawn beside the
    # headline numbers and in every species row, so most readers meet one long before
    # the panel that explains them; hovering has to be enough.
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
                   a_fmt, b_fmt, width=620, height=210, a_span=0.0):
    """Two series on two independent scales, sharing the snapshot dates.

    A dashed vertical rule at every index in ``marks`` says the Pl@ntNet model
    iteration changed there. Each series is scaled to its own min and max, no
    narrower than ``a_span`` for the first one, so the shapes are comparable
    but the pixel heights are not; the end labels carry the actual values.
    """
    if len(dates) < 2:
        return ""
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
                                      (yb, "#00897b", "5 3", b_vals, b_fmt)):
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
        o.append(f'<text x="{xs[i]:.1f}" y="{height - pad_b + 15}" font-size="10" '
                 f'fill="#9e9e9e" text-anchor="middle">{esc(d)}</text>')
    o.append(f'<text x="{pad_l}" y="{height - 6}" font-size="10.5" fill="#1565c0">'
             f'&#9473; {esc(a_name)}</text>'
             f'<text x="{pad_l + 210}" y="{height - 6}" font-size="10.5" fill="#00897b">'
             f'&#9476; {esc(b_name)}</text>'
             + (f'<text x="{width - pad_r}" y="{height - 6}" font-size="10.5" '
                f'fill="#c62828" text-anchor="end">&#9711; new Pl@ntNet model</text>'
                if marks else ""))
    o.append("</svg>")
    return "\n".join(o)
