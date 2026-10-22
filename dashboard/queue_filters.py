"""The queue page's filter-and-download block: the send rows embedded as JSON,
a few client-side filters, and a button that downloads the filtered rows in
``send_batches.csv``'s own columns and order.

The rows are read back from the file the page links, not rebuilt, so with no
filter the download is that file byte for byte. Confidence is not a column of
that file, so it rides beside each row for filtering only and never reaches
the download. Vanilla JS, inline, like the other pages.
"""

from __future__ import annotations

import csv
import json
import os

from assets import esc

SEND_FILE = "send_batches.csv"
QUEUE_FILE = "send_first_queue.csv"

# Same quoting as Python's csv.writer: quote a cell holding a comma, a quote or
# a line break, double the quotes, end every line with CRLF. Standalone so the
# test can run it under node against the real file.
CSV_JS = """function cell(v){return /[",\\r\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v}
function toCsv(header,rows){return [header].concat(rows).map(function(r){
  return r.map(cell).join(',')}).join('\\r\\n')+'\\r\\n'}"""

_JS = """(function(){
var d=JSON.parse(document.getElementById('send-data').textContent);
var H=d.header,R=d.rows,C=d.conf;
var F={queue:H.indexOf('queue'),species:H.indexOf('species_group'),
  mission:H.indexOf('mission'),site:H.indexOf('site')};
var el=function(id){return document.getElementById(id)};
function pick(){var lo=parseFloat(el('f-lo').value),hi=parseFloat(el('f-hi').value);
  if(isNaN(lo))lo=0;if(isNaN(hi))hi=1;
  var q=el('f-queue').value,s=el('f-species').value,m=el('f-mission').value,
    t=el('f-site').value,out=[];
  for(var i=0;i<R.length;i++){var r=R[i];
    if(q&&r[F.queue]!==q)continue;if(s&&r[F.species]!==s)continue;
    if(m&&r[F.mission]!==m)continue;if(t&&r[F.site]!==t)continue;
    if(C[i]!==''&&(+C[i]<lo||+C[i]>hi))continue;out.push(r)}
  return out}
function show(){var rows=pick(),by={};
  el('f-count').textContent=rows.length.toLocaleString('en-US')+' of '+
    R.length.toLocaleString('en-US')+' photos';
  rows.forEach(function(r){var k=r[F.mission]||'(no mission recorded)';by[k]=(by[k]||0)+1});
  var tb=el('f-missions');tb.textContent='';
  Object.keys(by).sort().forEach(function(k){var tr=document.createElement('tr'),
    a=document.createElement('td'),b=document.createElement('td');
    a.textContent=k;b.textContent=by[k].toLocaleString('en-US');b.className='num';
    tr.appendChild(a);tr.appendChild(b);tb.appendChild(tr)})}
['f-queue','f-species','f-mission','f-site','f-lo','f-hi'].forEach(function(id){
  el(id).addEventListener('input',show)});
el('f-download').addEventListener('click',function(){
  var u=URL.createObjectURL(new Blob([toCsv(H,pick())],{type:'text/csv;charset=utf-8'})),
    a=document.createElement('a');a.href=u;a.download='send_batches_filtered.csv';
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(u)});
show()})();"""


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def send_data(verify_dir):
    """``{"header", "rows", "conf"}`` for the filter block, or None when the
    send file is absent. ``rows`` are the file's cells, as strings; ``conf[i]``
    is row i's confidence off the queue file, or "" for a frame it lacks."""
    path = os.path.join(verify_dir, SEND_FILE)
    if not os.path.exists(path):
        return None
    header, *rows = _read(path)
    conf_of = {}
    qpath = os.path.join(verify_dir, QUEUE_FILE)
    if os.path.exists(qpath):
        q_header, *q_rows = _read(qpath)
        k, v = q_header.index("global_key"), q_header.index("confidence")
        conf_of = {r[k]: r[v] for r in q_rows}
    key_at = header.index("global_key")
    return {"header": header, "rows": rows, "conf": [conf_of.get(r[key_at], "") for r in rows]}


def _select(id_, label, values):
    opts = "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)
    return (f'<label>{label} <select id="{id_}"><option value="">all</option>{opts}</select>'
            '</label>')


def send_filters(c):
    """The filter controls, the live count, and the download button."""
    verify_dir = getattr(c, "verify_dir", None)
    data = send_data(verify_dir) if verify_dir else None
    if not data or not data["rows"]:
        return ""
    h = data["header"]
    uniq = lambda col: sorted({r[h.index(col)] for r in data["rows"] if r[h.index(col)]})
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    n = len(data["rows"])
    return (
        '<h3 class="sub">Choose what to send</h3>'
        f'<p class="note">Filter the {n:,} photos in <a href="{SEND_FILE}">{SEND_FILE}</a>, '
        'then download exactly those rows in the same columns, ready for Labelbox. '
        'With no filter the download is that file. Confidence is the first guess, 0 to 1.</p>'
        '<div class="controls">'
        + _select("f-queue", "Queue", uniq("queue"))
        + _select("f-species", "Species", uniq("species_group"))
        + _select("f-mission", "Mission", uniq("mission"))
        + _select("f-site", "Site", uniq("site"))
        + '<label>Confidence from <input id="f-lo" type="number" min="0" max="1" '
          'step="0.01" value="0" style="width:5em"></label>'
        + '<label>to <input id="f-hi" type="number" min="0" max="1" step="0.01" '
          'value="1" style="width:5em"></label>'
        + '<span class="count" id="f-count" aria-live="polite"></span>'
        + '<button type="button" id="f-download">Download filtered CSV</button></div>'
        + '<table><thead><tr><th>mission</th><th class="num">photos chosen</th></tr></thead>'
          '<tbody id="f-missions"></tbody></table>'
        + f'<script type="application/json" id="send-data">{blob}</script>'
        + f'<script>{CSV_JS}\n{_JS}</script>')
