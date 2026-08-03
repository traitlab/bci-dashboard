"""Static CSS/JS for the model-health dashboard. Stdlib-only, no network.

``_BASE_CSS`` is vendored from labelfirst's report substrate
(``labelfirst/src/labelfirst/eval/report/_html.py``, ``_CSS``) so the two
reports look like one family, then extended by ``_EXTRA_CSS`` below for the
wide sortable per-species table this page needs. It is vendored rather than
imported because ``import labelfirst`` pulls numpy/scipy/scikit-learn/pandas,
and this page must render from the stdlib alone.

It is a *strict subset*, not a verbatim copy: every retained rule is
byte-identical, and 28 lines are dropped -- the verdict-bar, pass/refuted
badge, design-details, chart-grid and tooltip rules, for elements this page
has none of. A future upstream ``_CSS`` change therefore cannot be picked up
by plain copy-paste; the prune has to be reapplied.

``_JS`` is NOT vendored: labelfirst's script only drives tooltips for its
trajectory chart. This page needs client-side sort and filter over 169 species
rows instead.
"""

from __future__ import annotations

import html

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
.key-numbers{
  display:flex;gap:20px;flex-wrap:wrap;margin-bottom:24px;
  font-size:0.9rem;color:#424242;
}
.kn{
  padding:4px 12px;background:#fff;border:1px solid #e0e0e0;border-radius:6px;
  font-size:0.85rem;
}
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
.badge{
  display:inline-block;padding:2px 10px;border-radius:4px;
  font-size:0.78rem;font-weight:700;letter-spacing:0.3px;
}
svg{display:block;margin:0 auto 16px}
details{margin-top:8px}
summary{
  cursor:pointer;font-size:0.9rem;font-weight:600;color:#1565c0;
  padding:6px 0;
}
summary:hover{text-decoration:underline}
.detail-inner{padding:12px 0}
.detail-inner table{font-size:0.8rem}
.footer{
  margin-top:40px;padding-top:12px;border-top:1px solid #e0e0e0;
  font-size:0.75rem;color:#bdbdbd;text-align:center;
}
@media(max-width:640px){
  body{padding:16px 12px 40px}
  .key-numbers{gap:8px}
  svg{width:100%!important;height:auto!important}
}
@media print{
  body{background:#fff;max-width:none;padding:0}
  .card{box-shadow:none;border:1px solid #ccc;break-inside:avoid}
  .badge{print-color-adjust:exact;-webkit-print-color-adjust:exact}
  .footer{display:none}
  summary{color:#333}
}
"""

# --- dashboard-specific additions -----------------------------------------
_EXTRA_CSS = """\
body{max-width:1120px}
h1{margin-bottom:2px}
.lede{font-size:0.95rem;color:#424242;margin:10px 0 22px;max-width:70ch}
.hero{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:6px}
.hero .metric{
  flex:1 1 220px;background:#fff;border:1px solid #e0e0e0;border-radius:8px;
  padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
.hero .metric.lead{border-color:#90caf9;background:#f3f9ff}
.hero .metric .v{font-size:2rem;font-weight:700;color:#212121;line-height:1.1}
.hero .metric .l{font-size:0.8rem;color:#616161;margin-top:6px}
.hero .metric .n{font-size:0.72rem;color:#9e9e9e;margin-top:4px}
.note{font-size:0.82rem;color:#616161;margin-top:10px;max-width:78ch}
.note strong{color:#424242}
.warn{
  background:#fff8e1;border:1px solid #ffe082;border-radius:6px;
  padding:12px 16px;font-size:0.83rem;color:#5d4037;margin:12px 0;max-width:82ch;
}
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
.legend{font-size:0.8rem;color:#616161;margin-bottom:14px}
.legend li{margin:4px 0 4px 18px}
.rec{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;
  padding:10px 14px;font-size:0.85rem;color:#1b5e20;margin-top:10px}
tr.hidden{display:none}
.prov{font-size:0.78rem;color:#616161}
.prov li{margin:4px 0 4px 18px}
.prov code{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.74rem;
  background:#f5f5f5;padding:1px 4px;border-radius:3px;
}
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
      var name=r.getAttribute('data-species')||'';
      var st=r.getAttribute('data-status')||'';
      var ok=(!needle||name.indexOf(needle)>=0)&&(want==='all'||st===want);
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

  function sortBy(idx,dir){
    var sorted=rows.slice().sort(function(a,b){
      var x=key(a.cells[idx]),y=key(b.cells[idx]);
      var nx=parseFloat(x),ny=parseFloat(y);
      var c;
      if(!isNaN(nx)&&!isNaN(ny)) c=nx-ny;
      else c=String(x).localeCompare(String(y));
      return dir==='asc'?c:-c;
    });
    sorted.forEach(function(r){tbody.appendChild(r);});
  }

  Array.prototype.slice.call(table.tHead.rows[0].cells).forEach(function(th,idx){
    if(!th.classList.contains('sortable')) return;
    th.addEventListener('click',function(){
      var dir=th.classList.contains('desc')?'asc':'desc';
      Array.prototype.slice.call(table.tHead.rows[0].cells).forEach(function(o){
        o.classList.remove('asc','desc');
      });
      th.classList.add(dir);
      sortBy(idx,dir);
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
