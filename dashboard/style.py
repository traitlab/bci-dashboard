"""The page's stylesheet and its one script, and nothing else.

``_BASE_CSS`` is vendored (not imported, to avoid pulling numpy/scipy/pandas)
from labelfirst's report substrate
(``labelfirst/src/labelfirst/eval/report/_html.py``, ``_CSS``), extended by
``_EXTRA_CSS``. Strict subset: retained rules are byte-identical, unused ones
dropped, so an upstream change needs manual reapply, not copy-paste. The JS is
not vendored: this page needs its own client-side sort/filter, not labelfirst's
chart tooltips.

The element ids live here too, because the script looks them up and
``assets.filterable_table`` writes them. One definition, so the two cannot
drift. The HTML builders that use them are in ``assets.py``.
"""

from __future__ import annotations

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
TABLE_ID = "species-table"
INPUT_ID = "species-filter"
SELECT_ID = "status-filter"
COUNT_ID = "species-count"
THIN_ID = "show-thin"

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
""").substitute(table_id=TABLE_ID, input_id=INPUT_ID, select_id=SELECT_ID,
                count_id=COUNT_ID, thin_id=THIN_ID)
