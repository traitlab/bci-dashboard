"""Crown map template. The page holds no crowns: they load from the link after # at view time."""

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Crown map</title>__FAVICON__
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" integrity="sha384-MinO0mNliZ3vwppuPOUnGa+iq619pfMhLVUXfC4LHwSCvF9H+6P/KO4Q7qBOYV5V" crossorigin="anonymous">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js" integrity="sha384-SYKAG6cglRMN0RVvhNeBY0r3FYKNOJtznwA0v7B5Vp9tr31xAHsZC0DqkQ/pZDmj" crossorigin="anonymous"></script>
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js" integrity="sha384-QfbOCebHNw8pQiPAOd2IFee2v2A5VYZxBk0+JGZ5H+3mfzVIp6zsQNkTsfGJot93" crossorigin="anonymous"></script>
<style>__SITE_CSS__
body{display:flex;flex-direction:column;height:100vh}
#main-content{flex:1;display:grid;grid-template-columns:minmax(0,1fr) 300px;min-height:0}
#mapwrap{position:relative;min-height:360px}#map{position:absolute;inset:0}
#mapwrap:has(canvas:focus-visible)::after{content:'';position:absolute;left:50%;top:50%;width:22px;height:22px;margin:-11px;pointer-events:none;background:linear-gradient(#fff,#fff) 50%/2px 100% no-repeat,linear-gradient(#fff,#fff) 50%/100% 2px no-repeat;filter:drop-shadow(0 0 2px #000)}
#notice{position:absolute;left:50%;top:16px;transform:translateX(-50%);margin:0;padding:8px 14px;max-width:min(420px,calc(100% - 32px));background:var(--paper);color:var(--ink);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 2px 10px rgba(33,62,51,.18);font-size:14px}
::selection{background:var(--pale);color:var(--ink)}
aside{overflow:auto;padding:20px 16px;border-left:1px solid var(--line);background:var(--paper);font-size:14px}
aside h1{font-size:20px;margin:0 0 6px}aside p{color:var(--slate);margin:0 0 12px;line-height:1.45}
.control{margin:16px 0 20px}.control label{display:flex;justify-content:space-between;font-weight:600;color:var(--ink);margin-bottom:6px}.control output{font-variant-numeric:tabular-nums;font-weight:600}.control input[type=range]{display:block;width:calc(90% + 16px);margin:0 0 0 -8px;accent-color:var(--green)}.control input::-webkit-slider-thumb{width:16px;height:16px}.control input::-moz-range-thumb{width:16px;height:16px}.control small{display:block;color:var(--slate);font-size:12px;margin-top:2px}
.legend-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;padding-top:16px;border-top:1px solid var(--line)}.legend-head h2{font-size:15px;margin:0}.legend-head button{border:0;background:none;padding:4px 2px;color:var(--green);font-size:13px;cursor:pointer;text-decoration:underline;text-underline-offset:3px}.legend-note{font-size:12px;margin:4px 0 8px!important}
#legend{margin-bottom:20px}#legend ul{list-style:none;margin:0;padding:0}#legend ul ul{padding-left:16px}
.tn{display:flex;align-items:center;gap:2px;min-height:30px}
.tw{flex:0 0 24px;height:28px;display:grid;place-items:center;padding:0;border:0;border-radius:var(--radius);background:none;color:var(--slate);cursor:pointer}.tw svg{width:12px;height:12px;transition:transform .18s cubic-bezier(.16,1,.3,1)}.tw[aria-expanded=true] svg{transform:rotate(90deg)}.tw:hover{background:var(--pale)}
.tl{flex:1;min-width:0;display:flex;align-items:center;gap:8px;padding:2px 6px;border:0;border-radius:6px;background:none;text-align:left;cursor:pointer;font-size:14px;color:var(--ink);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.tl:hover{background:var(--pale)}.tw:focus-visible,.tl:focus-visible,.legend-head button:focus-visible{outline:2px solid var(--focus);outline-offset:1px}.tl[aria-pressed=false]{color:var(--slate);text-decoration:line-through}.tl[aria-pressed=false] .swatch{opacity:.4}
.rank-clade>.tl{font-weight:650}
.swatch{width:14px;height:14px;border:3px solid;border-radius:3px;flex:none}
.tc{flex:0 0 56px;text-align:right;color:var(--slate);font-size:12px;font-variant-numeric:tabular-nums;padding-bottom:2px;background:linear-gradient(var(--c),var(--c)) no-repeat 100% 100%/var(--s,0) 3px}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px;margin:0 0 16px}.stats div{display:flex;flex-direction:column}.stats b{font-size:18px;color:var(--ink);font-variant-numeric:tabular-nums}.stats span{font-size:12px;color:var(--slate)}
.about{margin-top:20px;padding-top:16px;border-top:1px solid var(--line)}.about h2{font-size:15px;margin:0 0 8px}.about details{border-bottom:1px solid var(--line)}.about summary{cursor:pointer;padding:10px 0;font-weight:600;color:var(--ink)}.about summary:focus-visible{outline:2px solid var(--focus);outline-offset:2px}.about details p{font-size:13px}
.lede{color:var(--ink)!important;font-size:15px}.method{margin-top:20px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.method summary{cursor:pointer;padding:10px 0;font-weight:600;color:var(--ink)}.method summary:focus-visible{outline:2px solid var(--focus);outline-offset:2px}.method ol{margin:0;padding-left:20px;font-size:13px;color:var(--slate);line-height:1.45}.method li{margin:0 0 10px}.method li b{color:var(--ink)}
.dist{margin:0}.top h3{font-size:13px;margin:0 0 6px;color:var(--ink)}.bars{display:flex;align-items:flex-end;gap:2px;height:56px}.bars i{flex:1;background:var(--green);border-radius:2px 2px 0 0;min-height:1px}.bars i.off{background:none;border:1px dashed var(--slate);border-bottom:0}.axis{display:flex;justify-content:space-between;font-size:11px;color:var(--slate);font-variant-numeric:tabular-nums;margin-top:3px}
.top{margin:0 0 16px}.top ol{margin:0;padding-left:20px;font-size:13px;color:var(--slate)}.top button{display:flex;justify-content:space-between;gap:8px;width:100%;padding:3px 6px;border:0;border-radius:var(--radius);background:none;font-size:13px;color:var(--ink);cursor:pointer;text-align:left}.top button:hover{background:var(--pale)}.top button[aria-pressed=true]{background:var(--pale);font-weight:650}.top button span{color:var(--slate);font-variant-numeric:tabular-nums}.top em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.top small{display:block;color:var(--slate);font-size:12px;margin:4px 0 0}
.sprow{display:flex;align-items:center;gap:8px}#sp{flex:1;min-width:0;padding:6px 8px;border:1px solid var(--slate);font-size:14px;color:var(--ink);background:var(--paper)}#sp::placeholder{color:var(--slate)}#sp.on{border-color:var(--green);background:var(--pale);font-style:italic}.sprow button,.pop button{border:0;background:none;padding:4px 6px;color:var(--green);font-size:13px;cursor:pointer;text-decoration:underline;text-underline-offset:3px;white-space:nowrap}
.control .check{display:flex;justify-content:flex-start;align-items:center;gap:8px;margin:8px 0 0;font-size:13px;font-weight:400;color:var(--ink);cursor:pointer}.control .check[hidden]{display:none}.check input{width:16px;height:16px;margin:0;accent-color:var(--green)}
#empty{padding:24px;max-width:560px}
.maplibregl-popup-content{font:14px/1.4 "Avenir Next",Avenir,system-ui,sans-serif;color:var(--ink);padding:12px 14px;border-radius:var(--radius);box-shadow:0 4px 16px rgba(33,62,51,.22)}.maplibregl-popup-close-button{width:28px;height:28px;font-size:18px;color:var(--slate)}
.tip{pointer-events:none}.tip .maplibregl-popup-content{padding:3px 8px;font-size:13px;font-style:italic;box-shadow:0 2px 8px rgba(33,62,51,.22)}
.pop h2{font-size:15px;margin:0 20px 2px 0;font-style:italic}.pop p{margin:0 0 8px;font-size:12px;color:var(--slate)}.pop table{width:100%;border-collapse:collapse;font-size:13px}.pop td{padding:2px 0}.pop td+td{width:64px;padding-left:8px}.pop td:last-child{width:36px;text-align:right;font-variant-numeric:tabular-nums}.pop td i{display:block;height:6px;border-radius:3px;background:var(--green);min-width:1px}.pop tr+tr td i{background:#9ebca8}.pop tr.me td{font-weight:650}.pop button{margin:8px 0 0 -6px}
@media(prefers-reduced-motion:reduce){.tw svg{transition:none}}
@media(max-width:760px){body{height:auto}#main-content{grid-template-columns:1fr;grid-template-rows:minmax(360px,60vh) auto}aside{overflow:visible;border-left:0;border-top:1px solid var(--line)}}
</style></head>
<body>__SITE_NAV__
<main id="main-content" tabindex="-1"><div id="mapwrap"><div id="map"></div><p id="notice" role="status">Loading crowns</p></div>
<aside><h1>Crown map</h1><p id="lede" class="lede" hidden></p><p>Each shape is one tree crown, coloured by the family of the classifier's first species guess. Fainter crowns are less sure guesses. Zoom in for outlines and species names; point at a crown for its first guess, click or tap it for all five.</p>
<div class="control"><label for="minp">Hide guesses below <output id="minpv" for="minp">0%</output></label><div id="dist" class="dist" hidden></div><input type="range" id="minp" min="0" max="0.9" step="0.1" value="0"><small>The classifier's confidence in its first guess. The bars count crowns in each 10% step.</small></div>
<div class="control"><label for="sp">Show only one species</label><div class="sprow"><input id="sp" list="splist" aria-describedby="spnote" placeholder="Type a name" autocomplete="off" spellcheck="false"><button id="spclear" type="button" hidden>Show all</button></div><datalist id="splist"></datalist><label id="widerow" class="check" hidden><input type="checkbox" id="wide"> Also where it is a lower guess</label><small id="spnote" role="status"></small></div>
<div id="legend"></div>
<div id="stats" class="stats" hidden></div><div id="top" class="top" hidden></div>
<details class="method"><summary>How this map was made</summary><ol>
<li><b>Outlines.</b> A crown detection model (CanopyRS) traced every crown it could see on the 2025-06-16 drone mosaic of the whole island, at 3.8 cm per pixel. Two touching crowns can be one tree and one large tree can be two outlines; trees under the canopy do not show.</li>
<li><b>Labels.</b> The classifier learned 77 species from crowns that botanists identified in the forest plots. Test crowns were set aside and never used in training.</li>
<li id="m-photo"><b>Guesses inside the plots.</b> Where an outline overlaps a crown in the earlier, sharper drone photos of the plots (about 2 cm per pixel) by at least half, it takes that crown's guess.</li>
<li id="m-mosaic"><b>Guesses everywhere else.</b> Five copies of the classifier, retrained from different random starts on crowns cut from the 3.8 cm mosaic, each score the crown. The map shows their mean, rescaled so that the stated confidence better matches how often the first guess is right.</li>
<li id="m-acc"><b>Accuracy.</b> Measured on the held-out test crowns.</li>
<li><b>Limits.</b> The mosaic test crowns are ones whose outline matched a labelled tree well, and on the plot crowns the mosaic and photo first guesses agree for only about 30%, less than their test accuracy implies. Accuracy on typical crowns outside the plots is likely lower than stated. Treat each guess as a hypothesis to check in the field.</li>
</ol><p style="font-size:12px">Classifier run <span id="runid">bci-crown-20260611</span>. Summary numbers count every crown in the file; the legend counts only crowns in and near the view.</p></details>
<section class="about"><h2>How to read this map</h2>

<details><summary>What does the colour show?</summary><p>The colour shows the family of the classifier's first guess. Families in the same order or clade have similar colours. Grey means the family has no colour in the scheme.</p></details>
<details><summary>What is confidence?</summary><p>Confidence is the probability that the classifier gives to its first guess, from 0% to 100%. A fainter outline has a lower confidence. Confidence is the classifier's own score, not a measured accuracy: a high score can still be wrong. The slider sits under the chart: drag it to hide guesses below a level, and the bars that it hides turn grey.</p></details>
<details><summary>What are the five guesses?</summary><p>Click a crown to see the classifier's five highest-ranked species and their confidence. The button under them shows only the crowns with the same first guess. To find more candidates for a species, show only that species and then include the crowns where it is a lower guess: the right species is among the five more often than it is first.</p></details>
<details><summary>What do the chart and list show?</summary><p>The chart counts crowns in each 10% step of first-guess confidence. The list shows the species the classifier names first most often; a common first guess is not proof that a species is common.</p></details>
<details><summary>How can I use this map?</summary><p>Find where a species is likely: click a crown or a name in the list of common first guesses, then show only that species, or type its name in the species box. Find areas where the classifier is unsure: the fainter areas. The address of the page keeps the view, the confidence level and the species, so a copied address opens the same map.</p></details>
</section></aside></main>
<script>
'use strict';
const COLOURS=__COLOURS__,TREE=__TREE__,GREY='#8c8c8c';
const Q=new URLSearchParams(location.hash.slice(1)),src=Q.get('data'),$=id=>document.getElementById(id);
const hidden=new Set();
let min=0,only=null,wide=false,pop=null;
function read(){const q=new URLSearchParams(location.hash.slice(1));min=Math.min(.9,Math.max(0,Math.round(q.get('min')*10)/10))||0;only=q.get('only')||null;wide=q.get('any')==='1';}
read();
if(!src){document.getElementById('main-content').innerHTML='<div id="empty"><h1>Crown map</h1><p>This map needs a data link. The crowns are not published with the site; ask the team for the link.</p></div>';}
else{
const archive=new pmtiles.PMTiles(src),protocol=new pmtiles.Protocol();protocol.add(archive);maplibregl.addProtocol('pmtiles',protocol.tile);
const P=['coalesce',['get','top1_p'],.3],EMPTY={type:'FeatureCollection',features:[]};
const lookup=['coalesce',...['top1_family','top1_order','top1_clade'].map(k=>['get',['to-string',['get',k]],['literal',COLOURS]]),GREY];
const map=new maplibregl.Map({container:'map',hash:'view',maxZoom:21,center:[-79.85,9.155],zoom:15,style:{version:8,glyphs:'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf',
 sources:{imagery:{type:'raster',tileSize:256,maxzoom:18,attribution:'Imagery: Esri, Maxar, Earthstar Geographics',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}']},
 crowns:{type:'vector',url:'pmtiles://'+src},sel:{type:'geojson',data:EMPTY}},
 layers:[{id:'imagery',type:'raster',source:'imagery'},
 {id:'hit',type:'fill',source:'crowns','source-layer':'crowns',paint:{'fill-color':lookup,'fill-opacity':['interpolate',['linear'],['zoom'],14.5,['interpolate',['linear'],P,0,.3,1,.85],17,0]}},
 {id:'sel',type:'line',source:'sel',paint:{'line-color':'#fff','line-width':6,'line-opacity':.9}},
 {id:'crowns',type:'line',source:'crowns','source-layer':'crowns',paint:{'line-color':lookup,'line-width':['interpolate',['linear'],['zoom'],14,1,19,2.5],'line-opacity':['interpolate',['linear'],P,0,.35,1,1]}},
 {id:'names',type:'symbol',source:'crowns','source-layer':'crowns',minzoom:18.5,layout:{'text-field':['get','top1_name'],'text-font':['Noto Sans Regular'],'text-size':12,'text-max-width':8},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.75)','text-halo-width':1.5}}]}});
map.addControl(new maplibregl.NavigationControl(),'top-right');map.addControl(new maplibregl.ScaleControl(),'bottom-left');
function base(){const f=['all',['any',['!',['has','top1_p']],['>=',['get','top1_p'],min]]];if(only)f.push(wide?['in','|'+only+'|',['concat','|',['coalesce',['get','top5_names'],''],'|']]:['==',['get','top1_name'],only]);return f;}
const match=p=>!only||(wide?('|'+(p.top5_names||'')+'|').includes('|'+only+'|'):p.top1_name===only);
function filter(){pop?.remove();const f=[...base(),['!',['in',['get','top1_family'],['literal',[...hidden]]]]];for(const id of['hit','crowns','names'])map.setFilter(id,f);
 // rebuilt by hand: URLSearchParams would encode the slashes that MapLibre needs in view=
 const parts=location.hash.slice(1).split('&').filter(p=>p&&!/^(min|only|any)=/.test(p));if(min>0)parts.push('min='+min);if(only)parts.push('only='+encodeURIComponent(only));if(only&&wide)parts.push('any=1');history.replaceState(null,'','#'+parts.join('&'));
 $('sp').value=only||'';$('sp').removeAttribute('aria-invalid');$('sp').classList.toggle('on',!!only);$('spclear').hidden=$('widerow').hidden=!only;$('wide').checked=wide;$('spnote').textContent=only&&wide?'The confidence level and the colour still follow the first guess.':'';document.querySelectorAll('.top button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.only===only));}
function show(name){only=only===name?null:name;filter();}
$('spclear').onclick=()=>show(only);$('wide').onchange=e=>{wide=e.target.checked;filter();};
const species=new Set();
function offer(names){const n=species.size;for(const x of names)if(x)species.add(x);if(species.size>n)$('splist').replaceChildren(...[...species].sort().map(x=>new Option(x)));}
$('sp').onchange=e=>{const v=e.target.value.trim().toLowerCase(),hit=[...species].find(x=>x.toLowerCase()===v);
 if(hit||!v){only=hit||null;filter();}else{if(only)e.target.value=only;else e.target.setAttribute('aria-invalid','true');$('spnote').textContent='No crown seen so far has that first guess. Choose a name from the list.';}};
$('top').onclick=e=>{const b=e.target.closest('[data-only]');if(b)show(b.dataset.only);};
function slider(){$('minp').value=min;$('minpv').textContent=Math.round(min*100)+'%';}
slider();addEventListener('hashchange',()=>{read();slider();filter();shade();});
$('minp').oninput=e=>{min=+e.target.value;$('minpv').textContent=Math.round(min*100)+'%';filter();shade();};
let failed=false;const notice=t=>{$('notice').textContent=t;$('notice').hidden=!t;};
map.on('load',filter);map.on('error',e=>{if(e.sourceId==='crowns'&&!failed){failed=true;notice('Some crowns did not load. Load the page again. If that does not help, ask the team for a new data link.');}});map.once('idle',()=>failed||notice(''));
const hasView=Q.has('view');
archive.getHeader().then(h=>{if(!hasView)map.fitBounds([[h.minLon,h.minLat],[h.maxLon,h.maxLat]],{padding:24,animate:false});}).catch(()=>{failed=true;notice('The data link did not open. It may be out of date: ask the team for a new link.');});
const open=new Set();
function famsOf(node){return typeof node==='string'?[node]:node[1].flatMap(famsOf);}
function legend(){const a=document.activeElement,was=a&&$('legend').contains(a)&&(a.id?'#'+a.id:a.dataset.h?`[data-h="${a.dataset.h}"]`:`[data-o="${a.dataset.o}"]`);const seen={},names=new Set();for(const{properties:p}of map.querySourceFeatures('crowns',{sourceLayer:'crowns'})){names.add(p.top1_name);if(p.top1_p<min||!match(p))continue;const k=p.top1_family||'Unknown';seen[k]=(seen[k]||0)+1;}
 offer(names);
 const total=Object.values(seen).reduce((a,b)=>a+b,0)||1;
 const count=n=>famsOf(n).reduce((a,f)=>a+(seen[f]||0),0);
 const keep=n=>famsOf(n).some(f=>seen[f]||hidden.has(f));
 function row(n,rank){const name=typeof n==='string'?n:n[0],kids=typeof n==='string'?[]:n[1].filter(keep).sort((a,b)=>count(b)-count(a)),
  fams=famsOf(n),on=!fams.every(f=>hidden.has(f)),isOpen=kids.length&&open.has(name),c=count(n);
  let h=`<li><div class="tn rank-${rank}">`+(kids.length?`<button class="tw" data-o="${name}" aria-expanded="${!!isOpen}" aria-label="${isOpen?'Close':'Open'} ${name}"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`:'<span class="tw"></span>')
   +`<button class="tl" data-h="${name}" aria-pressed="${on}"><span class="swatch" style="border-color:${COLOURS[name]||GREY}"></span>${name}</button>`
   +`<span class="tc" style="--s:${c/total*100}%;--c:${COLOURS[name]||GREY}">${c.toLocaleString()}</span></div>`;
  if(isOpen)h+='<ul>'+kids.map(k=>row(k,rank==='clade'?'order':'family')).join('')+'</ul>';return h+'</li>';}
 const tops=TREE.filter(keep).sort((a,b)=>count(b)-count(a));
 document.getElementById('legend').innerHTML=tops.length?`<div class="legend-head"><h2>Crowns in view</h2><span><button id="showall">${hidden.size?'Show all':'Hide all'}</button> <button id="openall">${open.size?'Close all':'Open all'}</button></span></div><p class="legend-note">By clade, order and family. Counts are approximate: they include crowns near the edge of the view. Click a name to hide it on the map.</p><ul aria-label="Taxa in view">`+tops.map(t=>row(t,'clade')).join('')+'</ul>':'<div class="legend-head"><h2>Crowns in view</h2></div><p class="legend-note">'+(only||min?'No crown in view passes the confidence level and species that you set. Zoom out, lower the level or show all species.':'No species guesses here. Zoom out or pan to the coloured outlines.')+'</p>';if(was)$('legend').querySelector(was)?.focus();}
document.getElementById('legend').onclick=e=>{if(e.target.id==='showall'){if(hidden.size)hidden.clear();else TREE.flatMap(famsOf).forEach(f=>hidden.add(f));filter();legend();document.getElementById('showall').focus();return;}
 if(e.target.id==='openall'){if(open.size)open.clear();else TREE.forEach(([c,os])=>{open.add(c);os.forEach(([o])=>open.add(o));});legend();document.getElementById('openall').focus();return;}
 const o=e.target.closest('[data-o]'),h=e.target.closest('[data-h]');
 if(o){const k=o.dataset.o;open.has(k)?open.delete(k):open.add(k);legend();document.querySelector(`[data-o="${k}"]`)?.focus();return;}
 if(!h)return;const k=h.dataset.h,node=[...TREE,...TREE.flatMap(c=>c[1])].find(n=>n[0]===k),fams=node?famsOf(node):[k];
 const all=fams.every(f=>hidden.has(f));fams.forEach(f=>all?hidden.delete(f):hidden.add(f));filter();legend();document.querySelector(`[data-h="${k}"]`)?.focus();};
function shade(){document.querySelectorAll('.bars i').forEach((b,i)=>b.classList.toggle('off',(i+1)/10<=min+1e-9));const b=document.querySelector('.bars');if(b)b.setAttribute('aria-label',b.dataset.label+(min?`. Hidden below ${Math.round(min*100)}%`:''));}
map.on('idle',legend);
archive.getMetadata().then(m=>{const d=JSON.parse(m.description||'{}'),n=k=>Number(d[k]),fmt=k=>n(k).toLocaleString(),pct=k=>Math.round(n(k)*100)+'%';if(!(n('crowns')>0))return;
 const lede=document.getElementById('lede'),all=n('predicted')===n('crowns'),photo=n('from_photos')||0;
 lede.textContent=`${fmt('crowns')} crowns on Barro Colorado Island, Panama, ${all?'each':`${fmt('predicted')} of them`} with a species guess.`;lede.hidden=false;
 const el=document.getElementById('stats');
 el.innerHTML=[...(photo>0?[[photo.toLocaleString(),'guessed from plot photos'],[(n('predicted')-photo).toLocaleString(),'guessed from the mosaic']]:[]),[fmt('hectares')+' ha','of crown cover'],[n('species')+' / '+n('families'),'species / families named'],[pct('median_p'),'median confidence'],[pct('share_p80'),'at 80% or more']].map(([v,k])=>`<div><b>${v}</b><span>${k}</span></div>`).join('');el.hidden=false;
 const h=Array.isArray(d.hist)?d.hist.map(Number):[];if(h.length===10){const mx=Math.max(...h)||1,tot=h.reduce((a,b)=>a+b,0),dl=document.getElementById('dist');
  dl.innerHTML=`<div class="bars" role="img" data-label="Crowns by confidence, in steps of 10%: ${h.map((v,i)=>`${i*10} to ${i*10+10}%: ${v.toLocaleString()}`).join('; ')}">${h.map((v,i)=>`<i style="height:${v/mx*100}%" title="${i*10} to ${i*10+10}%: ${v.toLocaleString()} crowns (${Math.round(v/tot*100)}%)"></i>`).join('')}</div><div class="axis"><span>0%</span><span>Quartiles ${pct('q1_p')}, ${pct('median_p')}, ${pct('q3_p')}</span><span>100%</span></div>`;dl.hidden=false;shade();}
 const t=Array.isArray(d.top_species)?d.top_species.slice(0,5):[];if(t.length){offer((d.top_species).map(r=>String(r[0])));const tl=document.getElementById('top');tl.innerHTML='<h3>Most common first guesses</h3><ol></ol><small>Click a name to show only its crowns.</small>';
  for(const[nm,c]of t){const li=document.createElement('li'),b=document.createElement('button'),em=document.createElement('em'),sp=document.createElement('span');em.textContent=b.dataset.only=String(nm);sp.textContent=Number(c).toLocaleString();b.type='button';b.setAttribute('aria-pressed',String(nm)===only);b.append(em,sp);li.append(b);tl.querySelector('ol').append(li);}tl.hidden=false;}
 if(photo>0)document.getElementById('m-photo').append(` That covers ${photo.toLocaleString()} crowns.`);
 const acc=[];if(n('heldout_n')>0)acc.push(`Plot photos: first guess right for ${pct('heldout_top1')} of ${fmt('heldout_n')} test crowns, right species among the five for ${pct('heldout_top5')}.`);
 if(n('mosaic_heldout_n')>0)acc.push(`Mosaic: ${pct('mosaic_heldout_top1')} and ${pct('mosaic_heldout_top5')} on ${fmt('mosaic_heldout_n')} test crowns.`);
 if(acc.length)document.getElementById('m-acc').innerHTML='<b>Accuracy.</b> '+acc.join(' ')+' The map itself uses classifiers trained on all labelled crowns.';
 if(d.run)document.getElementById('runid').textContent=d.run;}).catch(()=>{});
function inspect(e){const f=map.queryRenderedFeatures(e.point,{layers:['hit']})[0];pop?.remove();tip.remove();if(!f)return;
 const p=f.properties,names=(p.top5_names||'').split('|'),ps=(p.top5_p||'').split(',').map(Number),first=p.top1_name||names[0];
 const esc=s=>String(s).replace(/[&<>"]/g,c=>'&#'+c.charCodeAt(0)+';');
 const about=[p.top1_family,p.area>0&&Math.round(p.area).toLocaleString()+' m²',p.src==='mosaic'?'guess from the whole-island mosaic':p.src&&'guess from the plot photos'].filter(Boolean).map(esc).join(', ');
 // shortcut: the outline is the clicked tile's piece of the crown, so it can stop at a tile edge; needs feature ids in the tiles to fix
 map.getSource('sel').setData({type:'Feature',geometry:f.geometry,properties:{}});
 const me=pop=new maplibregl.Popup({closeOnClick:false,focusAfterOpen:false,maxWidth:'300px'}).setLngLat(e.lngLat).setHTML(!p.top5_names?'<div class="pop"><p>No species guess for this crown.</p></div>':`<div class="pop"><h2>${esc(first)}</h2><p>${about}</p><table>${names.map((n,i)=>`<tr${n===only?' class="me"':''}><td>${esc(n)}</td><td><i style="width:${Math.round(ps[i]*100)}%"></i></td><td>${Math.round(ps[i]*100)}%</td></tr>`).join('')}</table><button type="button">${only===first?'Show all species':'Show only this species'}</button></div>`).addTo(map);
 me.on('close',()=>{if(pop===me){pop=null;map.getSource('sel').setData(EMPTY);}});
 me.getElement().querySelector('button:not(.maplibregl-popup-close-button)')?.addEventListener('click',()=>show(first));}
map.on('click',inspect);
map.getCanvas().addEventListener('keydown',e=>{if(e.key==='Enter'){const c=map.getCenter();inspect({point:map.project(c),lngLat:c});}});map.getCanvas().setAttribute('aria-label','Map of tree crowns. Arrow keys move the map, plus and minus zoom, Enter reads the crown at the centre.');
document.addEventListener('keydown',e=>{if(e.key==='Escape')pop?.remove();});
const tip=new maplibregl.Popup({closeButton:false,closeOnClick:false,focusAfterOpen:false,offset:12,className:'tip'});
map.on('mousemove','hit',e=>{const p=e.features[0].properties;map.getCanvas().style.cursor='pointer';if(pop||!p.top1_name)return tip.remove();tip.setLngLat(e.lngLat).setText(p.top1_name+(p.top1_p>=0?', '+Math.round(p.top1_p*100)+'%':'')).addTo(map);});
map.on('mouseleave','hit',()=>{map.getCanvas().style.cursor='';tip.remove();});
}
</script></body></html>
'''
