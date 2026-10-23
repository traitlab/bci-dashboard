"""The page's stylesheet and its one script, and nothing else.

``_BASE_CSS`` is vendored, not imported, to avoid pulling numpy/scipy/pandas in
from labelfirst's report substrate
(``labelfirst/src/labelfirst/eval/report/_html.py``, ``_CSS``), extended by
``_EXTRA_CSS``. Retained rules are byte-identical, so an upstream change needs a
manual reapply. The JS is this page's own: client-side sort/filter, not charts.

The element ids live here because the script looks them up and
``assets.filterable_table`` writes them, so the two cannot drift.

``tests/test_style.py`` holds both ends of the class coupling with
``assets.py``: every class a builder writes has a rule, and every rule matches
something.
"""

from __future__ import annotations

from string import Template
from site_navigation import CSS as NAVIGATION_CSS

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
   all four numbers at once. */
.caveat{font-size:0.85rem;color:#5d4037;background:#fbf3ec;border-left:3px solid #bf6a34;
  border-radius:0 4px 4px 0;padding:11px 14px;margin:14px 0 0}
.caveat strong{color:#3e2723}
/* Second paragraph needs its own top margin: the reset above zeroes p margins. */
.caveat p+p{margin-top:8px}
/* Two fixed columns, not a wrapping flex row: the four headline numbers are a
   2x2 grid of question x weighting. One column under 640px. */
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
/* #6d6d6d, not lighter: this line sits on white and on the tinted first card,
   clearing 4.5:1 on both (5.17 and 4.88), a step quieter than #616161. */
.hero .metric .n{font-size:0.72rem;color:#6d6d6d;margin-top:4px}
.hero .metric .row{display:flex;align-items:center;gap:10px;justify-content:space-between}
/* The CSV a card's figure comes off, on the right of the row the flex above
   already reserves. Same blue as the eyebrow, which is the one link colour
   already cleared against white and against the tinted first card. */
.hero .metric .src{font-size:0.72rem;font-weight:600;color:#1565c0;
  white-space:nowrap;text-align:right}
/* The landing grid: six cards, three across. */
.hero.wide{grid-template-columns:repeat(3,minmax(0,1fr))}
/* One button per status, each filtering the species table. */
.statusbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  font-size:0.82rem;color:#424242;margin:14px 0 6px}
.statusbar button{border:0;cursor:pointer;font-family:inherit}
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
.rec h2{font-size:1.15rem;margin:0 0 6px}
.rec button.primary,.controls button{font:inherit;font-weight:600;cursor:pointer;
  padding:8px 14px;border:0;border-radius:6px;background:#1565c0;color:#fff}
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
/* The headings wrap, so the table fits the page. Ten columns of headings on one
   line each made the widest thing on the page a row of words, and pushed the
   species name off the left edge of its own scroll box the moment a reader
   looked at the right-hand columns. The definitions moved into the tooltips, so
   what is left here is a label and it can take two lines. The abbr is an
   inline-block so the sort arrow sits beside the wrapped label rather than
   wrapping onto a line of its own. */
th.sortable{cursor:pointer;user-select:none}
th.sortable abbr{display:inline-block}
th.sortable:focus-visible{outline:2px solid #1565c0;outline-offset:-2px}
/* The arrow is the only thing telling the reader these headings sort, so it has
   to survive the #f5f5f5 header fill (4.75:1). */
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
/* The most common badge, so contrast matters most: #bf360c is 5.11:1 here,
   where #e65100 on this fill was 3.46:1. */
.tag.unmeasured{background:#fff3e0;color:#bf360c}
.tag.hard{background:#ffebee;color:#c62828}
.tag.unreachable{background:#eceff1;color:#455a64}
.tag.out_of_scope{background:#f5f5f5;color:#666}
/* Sits directly above/below the table it explains, so a status stays legible
   without leaving the table. Text colour matches .todo li. */
.status-legend{list-style:none;font-size:0.82rem;color:#424242;
  margin:8px 0 14px;display:flex;flex-direction:column;gap:5px}
.status-legend li{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
/* The vocabulary panel: one definition per row. */
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
/* Contrast override, not a restyle: #757575 here is 4.37:1, under the 4.5:1 WCAG
   AA floor, and the vendored rule it overrides stays byte-identical. */
.subtitle{color:#6d6d6d}
/* A sub-heading inside a panel body, count table apart from photo table. */
h3.sub{font-size:0.95rem;font-weight:700;color:#37474f;margin:22px 0 8px}
/* The contact sheet: the head of a queue as pictures. Columns fill the width the
   panel has, so a phone gets three and a desktop gets more, and the image fills
   its cell rather than overflowing it. */
/* The rule a queue selects on, under its heading. Everywhere else the two
   travel together. */
.qrule{font-size:0.85rem;color:#616161;margin:-4px 0 8px}
.sheet{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));
  gap:6px;margin:0 0 14px}
.sheet img{width:100%;height:auto;display:block;border-radius:3px;border:1px solid #e0e0e0}
/* A command meant to be copied whole, so it wraps rather than running off the
   right edge on a phone. */
pre.cmd{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.76rem;
  color:#37474f;background:#f5f5f5;padding:10px 12px;border-radius:4px;
  border-left:3px solid #b0bec5;white-space:pre-wrap;margin:8px 0}

/* A photo key is long and only ever copied, never read as prose. */
code.key{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.72rem;
  color:#37474f;word-break:break-all}

/* Sideways scroll only: a height cap hid rows below the fold with no cue. */
.tscroll{overflow-x:auto}
.tscroll:focus-visible{outline:3px solid #287752;outline-offset:-3px}
/* A recurring label-and-prediction pair is written once and spanned down its own
   frames, so the pair cells align to the first of them and the block that
   starts a new pair carries the rule between pairs. */
td.pair{vertical-align:top}
tr.pair>td{border-top:1px solid #cfd8dc}
.tally{font-size:0.74rem;color:#6d6d6d;white-space:nowrap;margin-left:6px}
/* A definition block for the reader who wants all of them at once. Closed, so
   the table it sits above starts on the first screen. */
details.more{margin:2px 0 12px}
details.more>summary{font-size:0.84rem;font-weight:600}
/* A column heading that carries its own definition in its title. The dotted
   underline is the long-standing "there is a definition here" mark; no
   cursor:help, because the heading is still a click target that sorts. */
th abbr{text-decoration:underline dotted;text-underline-offset:3px}
/* Every panel carries an id, so it must be findable once scrolled to. */
details.panel:target>summary{background:#e3f2fd}

/* Paper does not scroll, so a scroll box prints as a clipped table. */
@media print{
  .tscroll{overflow:visible}
}

/* No room for two columns on a phone; the vendored 640px query stays as it is. */
@media(max-width:640px){
  .hero,.hero.wide{grid-template-columns:1fr}
}
"""

CSS = _BASE_CSS + _EXTRA_CSS + NAVIGATION_CSS

TABLE_ID = "species-table"
INPUT_ID = "species-filter"
SELECT_ID = "status-filter"
COUNT_ID = "species-count"
THIN_ID = "show-thin"
FORM_ID = "form-filter"

# Client-side sort + filter, vanilla. string.Template, not an f-string: the body
# is mostly JS braces an f-string would need escaped. Table pages only.
TABLE_JS = Template("""\
(function(){
  var table=document.getElementById('$table_id');
  if(!table) return;
  var tbody=table.tBodies[0];
  var rows=Array.prototype.slice.call(tbody.rows);
  var q=document.getElementById('$input_id');
  var sel=document.getElementById('$select_id');
  var count=document.getElementById('$count_id');
  var fsel=document.getElementById('$form_id');
  // Rows a caller marked data-thin start hidden, unless a deliberate filter
  // overrides that: a typed needle, or a chosen status. Without the override,
  // picking "too few labels to judge" would empty the table and read as a
  // broken page. No checkbox means the caller marked nothing, so all rows show.
  var thin=document.getElementById('$thin_id');

  // A row's status is the class on its own status tag.
  function statusOf(r){
    var tag=r.querySelector('.tag');
    return tag?tag.className.replace('tag','').trim():'';
  }

  function apply(){
    var needle=(q.value||'').trim().toLowerCase();
    var want=sel?sel.value:'all';
    var form=fsel?fsel.value:'all';
    var showThin=thin?thin.checked:true;
    var shown=0;
    rows.forEach(function(r){
      // The needle is matched against the first cell, the species name as shown.
      var hay=(r.cells[0]?r.cells[0].textContent:'').toLowerCase();
      var ok=(!needle||hay.indexOf(needle)>=0)&&
             (want==='all'||statusOf(r)===want)&&
             (form==='all'||r.getAttribute('data-form')===form)&&
             (showThin||needle||want!=='all'||form!=='all'||
              r.getAttribute('data-thin')!=='1');
      r.classList.toggle('hidden',!ok);
      if(ok) shown++;
    });
    // A bare count over an empty table reads as a broken page. Say what happened.
    count.textContent=shown?(shown+' of '+rows.length+' species shown')
                           :'No species matches that filter.';
  }

  // A cell sorts on its own data-sort where it has one, and on what it shows
  // where it does not: "392" already sorts as 392.
  function key(cell){
    var v=cell.getAttribute('data-sort');
    return v===null?cell.textContent.trim():v;
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
  if(fsel) fsel.addEventListener('change',apply);
  if(thin) thin.addEventListener('change',apply);
  apply();
})();
""").substitute(table_id=TABLE_ID, input_id=INPUT_ID, select_id=SELECT_ID,
                count_id=COUNT_ID, thin_id=THIN_ID, form_id=FORM_ID)

# Printing and jump links, which every page needs, kept out of TABLE_JS.
EVERY_PAGE_JS = """\
// Printing. Either page as it sits would print as a sheet of headings, so open
// every panel for the print, then put it back. Keep this out of the block
// above, which returns early when there is no species table.
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
  // Otherwise a jump link lands on a panel :target styles but leaves collapsed.
  function openHash(){
    if(!location.hash) return;
    var el=null;
    try{ el=document.querySelector(location.hash); }catch(e){ return; }
    if(el&&el.tagName==='DETAILS'){ el.open=true; el.scrollIntoView(); }
  }
  window.addEventListener('hashchange',openHash);
  openHash();
})();
"""

JS = TABLE_JS + EVERY_PAGE_JS
