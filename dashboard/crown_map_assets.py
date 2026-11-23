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
#map{min-height:360px}
aside{overflow:auto;padding:20px 16px;border-left:1px solid var(--line);background:var(--paper);font-size:14px}
aside h1{font-size:20px;margin:0 0 6px}aside p{color:var(--slate);margin:0 0 12px;line-height:1.45}
.control{margin:16px 0 20px}.control label{display:flex;justify-content:space-between;font-weight:600;color:var(--ink);margin-bottom:6px}.control output{font-variant-numeric:tabular-nums;font-weight:600}.control input{width:100%;accent-color:var(--green)}.control small{display:block;color:var(--slate);font-size:12px;margin-top:2px}
.legend-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;padding-top:16px;border-top:1px solid var(--line)}.legend-head h2{font-size:15px;margin:0}.legend-head button{border:0;background:none;padding:4px 2px;color:var(--green);font-size:13px;cursor:pointer;text-decoration:underline;text-underline-offset:3px}.legend-note{font-size:12px;margin:4px 0 8px!important}
#legend ul{list-style:none;margin:0;padding:0}#legend ul ul{padding-left:16px}
.tn{display:flex;align-items:center;gap:2px;min-height:30px}
.tw{flex:0 0 24px;height:28px;display:grid;place-items:center;padding:0;border:0;border-radius:var(--radius);background:none;color:var(--slate);cursor:pointer}.tw svg{width:12px;height:12px;transition:transform .18s cubic-bezier(.16,1,.3,1)}.tw[aria-expanded=true] svg{transform:rotate(90deg)}.tw:hover{background:var(--pale)}
.tl{flex:1;min-width:0;display:flex;align-items:center;gap:8px;padding:2px 6px;border:0;border-radius:6px;background:none;text-align:left;cursor:pointer;font-size:14px;color:var(--ink);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.tl:hover{background:var(--pale)}.tw:focus-visible,.tl:focus-visible,.legend-head button:focus-visible{outline:2px solid var(--focus);outline-offset:1px}.tl[aria-pressed=false]{opacity:.4;text-decoration:line-through}
.rank-clade>.tl{font-weight:650}
.swatch{width:14px;height:14px;border:3px solid;border-radius:3px;flex:none}
.tc{flex:0 0 56px;text-align:right;color:var(--slate);font-size:12px;font-variant-numeric:tabular-nums;padding-bottom:2px;background:linear-gradient(var(--c),var(--c)) no-repeat 100% 100%/var(--s,0) 3px}
#empty{padding:24px;max-width:560px}
.maplibregl-popup-content{font:14px/1.4 inherit}.maplibregl-popup-content td{padding:0 6px}
@media(max-width:760px){body{height:auto}#main-content{grid-template-columns:1fr;grid-template-rows:60vh auto}aside{overflow:visible;border-left:0;border-top:1px solid var(--line)}}
</style></head>
<body>__SITE_NAV__
<main id="main-content" tabindex="-1"><div id="map"></div>
<aside><h1>Crown map</h1><p>Each outline is one tree crown, coloured by the family of the model's first guess. Fainter outlines are guesses the model is less sure of. Zoom in for species names; click a crown for its five guesses.</p>
<div class="control"><label for="minp">Hide guesses below <output id="minpv" for="minp">0%</output></label><input type="range" id="minp" min="0" max="0.9" step="0.1" value="0"><small>The model's confidence in its first guess.</small></div>
<div id="legend" aria-live="polite"></div></aside></main>
<script>
'use strict';
const COLOURS=__COLOURS__,TREE=__TREE__,GREY='#8c8c8c';
const src=new URLSearchParams(location.hash.slice(1)).get('data');
const hidden=new Set();
if(!src){document.getElementById('main-content').innerHTML='<div id="empty"><h1>Crown map</h1><p>This map needs a data link. The crowns are not published with the site; ask the team for the link.</p></div>';}
else{
maplibregl.addProtocol('pmtiles',new pmtiles.Protocol().tile);
const lookup=['coalesce',...['top1_family','top1_order','top1_clade'].map(k=>['get',['get',k],['literal',COLOURS]]),GREY];
const map=new maplibregl.Map({container:'map',hash:'view',maxZoom:21,center:[-79.85,9.155],zoom:15,style:{version:8,glyphs:'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf',
 sources:{imagery:{type:'raster',tileSize:256,maxzoom:18,attribution:'Imagery: Esri, Maxar, Earthstar Geographics',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}']},
 crowns:{type:'vector',url:'pmtiles://'+src}},
 layers:[{id:'imagery',type:'raster',source:'imagery'},
 {id:'hit',type:'fill',source:'crowns','source-layer':'crowns',paint:{'fill-color':'#000','fill-opacity':0}},
 {id:'crowns',type:'line',source:'crowns','source-layer':'crowns',paint:{'line-color':lookup,'line-width':['interpolate',['linear'],['zoom'],14,1,19,2.5],'line-opacity':['interpolate',['linear'],['get','top1_p'],0,.35,1,1]}},
 {id:'names',type:'symbol',source:'crowns','source-layer':'crowns',minzoom:18.5,layout:{'text-field':['get','top1_name'],'text-font':['Noto Sans Regular'],'text-size':12,'text-max-width':8},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.75)','text-halo-width':1.5}}]}});
map.addControl(new maplibregl.NavigationControl(),'top-right');map.addControl(new maplibregl.ScaleControl(),'bottom-left');
function filter(){const min=+document.getElementById('minp').value,f=['all',['>=',['get','top1_p'],min],['!',['in',['get','top1_family'],['literal',[...hidden]]]]];for(const id of['hit','crowns','names'])map.setFilter(id,f);}
document.getElementById('minp').oninput=e=>{document.getElementById('minpv').textContent=Math.round(e.target.value*100)+'%';filter();};
const open=new Set();
function famsOf(node){return typeof node==='string'?[node]:node[1].flatMap(famsOf);}
function legend(){const seen={};for(const f of map.querySourceFeatures('crowns',{sourceLayer:'crowns'})){const k=f.properties.top1_family||'Unknown';seen[k]=(seen[k]||0)+1;}
 const total=Object.values(seen).reduce((a,b)=>a+b,0)||1;
 const count=n=>famsOf(n).reduce((a,f)=>a+(seen[f]||0),0);
 const keep=n=>famsOf(n).some(f=>seen[f]||hidden.has(f));
 function row(n,rank){const name=typeof n==='string'?n:n[0],kids=typeof n==='string'?[]:n[1].filter(keep).sort((a,b)=>count(b)-count(a)),
  fams=famsOf(n),on=!fams.every(f=>hidden.has(f)),isOpen=kids.length&&open.has(name),c=count(n);
  let h=`<li><div class="tn rank-${rank}">`+(kids.length?`<button class="tw" data-o="${name}" aria-expanded="${!!isOpen}" aria-label="${isOpen?'Close':'Open'} ${name}"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`:'<span class="tw"></span>')
   +`<button class="tl" data-h="${name}" aria-pressed="${on}"><span class="swatch" style="border-color:${COLOURS[name]||GREY}"></span>${name}</button>`
   +`<span class="tc" style="--s:${c/total*100}%;--c:${COLOURS[name]||GREY}">${c.toLocaleString()}</span></div>`;
  if(isOpen)h+='<ul role="group">'+kids.map(k=>row(k,rank==='clade'?'order':'family')).join('')+'</ul>';return h+'</li>';}
 const tops=TREE.filter(keep).sort((a,b)=>count(b)-count(a));
 document.getElementById('legend').innerHTML=tops.length?`<div class="legend-head"><h2>Crowns in view</h2><button id="openall">${open.size?'Close all':'Open all'}</button></div><p class="legend-note">By clade, order and family. Click a name to hide it on the map.</p><ul role="tree" aria-label="Taxa in view">`+tops.map(t=>row(t,'clade')).join('')+'</ul>':'<div class="legend-head"><h2>Crowns in view</h2></div><p class="legend-note">None here. Zoom out or pan to the outlined area.</p>';}
document.getElementById('legend').onclick=e=>{if(e.target.id==='openall'){if(open.size)open.clear();else TREE.forEach(([c,os])=>{open.add(c);os.forEach(([o])=>open.add(o));});legend();document.getElementById('openall').focus();return;}
 const o=e.target.closest('[data-o]'),h=e.target.closest('[data-h]');
 if(o){const k=o.dataset.o;open.has(k)?open.delete(k):open.add(k);legend();document.querySelector(`[data-o="${k}"]`)?.focus();return;}
 if(!h)return;const k=h.dataset.h,node=[...TREE,...TREE.flatMap(c=>c[1])].find(n=>n[0]===k),fams=node?famsOf(node):[k];
 const all=fams.every(f=>hidden.has(f));fams.forEach(f=>all?hidden.delete(f):hidden.add(f));filter();legend();document.querySelector(`[data-h="${k}"]`)?.focus();};
map.on('idle',legend);
map.on('click','hit',e=>{const p=e.features[0].properties,names=(p.top5_names||'').split('|'),ps=(p.top5_p||'').split(',').map(Number);
 const esc=s=>String(s).replace(/[&<>"]/g,c=>'&#'+c.charCodeAt(0)+';');
 new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<b>${esc(p.top1_family||'')}</b><table>${names.map((n,i)=>`<tr><td>${esc(n)}</td><td>${Math.round(ps[i]*100)}%</td></tr>`).join('')}</table>`).addTo(map);});
map.on('mouseenter','hit',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','hit',()=>map.getCanvas().style.cursor='');
}
</script></body></html>
'''
