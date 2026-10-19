"""Mission-specific similarity keeps one query and one candidate authority."""

import json
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_atlas(points, checks, initial_hash="#frame=query", comparison=None, page=None, encoder="Crownfirst test encoder"):
    if not shutil.which("node"):
        pytest.skip("Node is needed to execute mission view behavior")
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    script = html.split("<script>")[1].split("</script>")[0]
    payload = {
        "points": points,
        "provenance": {
            "encoder": encoder,
            "labels": {"available": True},
            "versions": [],
            "dimensions": 3,
            "projection": "PCA",
            "input_count": len(points),
            "excluded": {},
            "sources": [],
        },
    }
    if comparison is not None:
        payload["comparison"] = comparison
    setup = r"""
const assert=require('node:assert/strict'),elements=new Map(),contexts=new Map(),listeners={};
function context(id){if(!contexts.has(id))contexts.set(id,{arcs:[],fills:[],texts:[],lines:[],moveTo(x,y){this.lines.push([x,y])},lineTo(x,y){this.lines.push([x,y])},fillText(text,x,y){this.texts.push([text,x,y])},strokeText(){},scale(){},fillRect(){},beginPath(){},arc(x,y,r){this.arcs.push(r)},fill(){this.fills.push(this.fillStyle)},stroke(){},drawImage(){}});return contexts.get(id)}
function make(id){return {id,children:[],attributes:{},isConnected:true,clientWidth:640,clientHeight:520,value:'',style:{},contains(target){return target===this||this.children.some(child=>child.contains?.(target))},focus(){document.activeElement=this},scrollIntoView(){},setPointerCapture(){},getContext:()=>context(id),replaceChildren(...v){this.children=v},append(...v){this.children.push(...v)},getAttribute(name){return this.attributes[name]??null},removeAttribute(name){delete this[name];delete this.attributes[name]},setAttribute(name,value){this[name]=value;this.attributes[name]=value},addEventListener(){},showModal(){this.open=true},close(){this.open=false;this.onclose?.()}}}
function element(id){if(!elements.has(id))elements.set(id,make(id));return elements.get(id)}
for(const id of ['similarMissionMode','mapMissionMode'])element(id).options=['all','other'].map(value=>({value}));
const payload=__PAYLOAD__;
element('atlas-data').textContent=JSON.stringify(payload);
const navLinks=['embedding-atlas.html','crownfirst-atlas.html','explorer.html','embedding-atlas.html#view=photos','crownfirst-atlas.html#view=locations','crownfirst-atlas.html#view=models'].map((href,index)=>{const link=make('nav'+index);link.setAttribute('href',href);if(index>=3){const view=['photos','locations','models'][index-3];link.setAttribute('data-atlas-view',view);link.setAttribute('data-site-task',view)}return link});
const compareLink=make('compareModelsLink');compareLink.setAttribute('href','crownfirst-atlas.html#view=models');compareLink.setAttribute('data-atlas-view','models');navLinks.push(compareLink);
for(const [id,model,targetView] of [['plantclefPhotosLink','plantclef','photos'],['plantclefMapLink','plantclef','locations'],['ordinaryMatchingLink','plantnet','photos']]){const link=element(id);link.setAttribute('href',model==='plantclef'?'crownfirst-atlas.html':'embedding-atlas.html');link.setAttribute('data-matching-model',model);link.setAttribute('data-atlas-view',targetView);navLinks.push(link)}
const historyEntries=[];
global.document={getElementById:element,querySelector:()=>element('inspector'),querySelectorAll:selector=>selector==='nav a'?navLinks:[],createElement:make,addEventListener(name,fn){listeners['document:'+name]=fn}};global.devicePixelRatio=1;global.location={hash:'#frame=query'};global.history={pushState(_,__,hash){historyEntries.push(hash);location.hash=hash},replaceState(_,__,hash){location.hash=hash}};global.window={addEventListener(name,fn){listeners[name]=fn},removeEventListener(name,fn){if(listeners[name]===fn)delete listeners[name]},matchMedia:()=>({matches:false})};global.requestAnimationFrame=()=>{};global.Image=class{};
""".replace("__PAYLOAD__", json.dumps(payload)).replace("'#frame=query'", json.dumps(initial_hash))
    if page is not None:
        setup += "location.pathname=" + json.dumps("/" + page) + ";"
    result = subprocess.run(["node", "-e", setup + script + checks], capture_output=True, text=True, check=False)
    if result.returncode:
        pytest.fail(result.stderr + result.stdout, pytrace=False)


def photo(key, mission, neighbours=None, **extra):
    return {
        "key": key,
        "mission": mission,
        "label": "Fabaceae",
        "family": "Fabaceae",
        "lat": 9.1,
        "lon": -79.8,
        "xy": [0, 0],
        "rgb": [1, 2, 3],
        "group": "pool",
        "image": "https://example.org/" + key + ".jpg",
        "neighbours": neighbours or [],
        **extra,
    }


def test_mission_toggle_updates_cards_rings_and_modal_without_changing_query():
    points = [
        photo("query", "flight-a", [[1, .99], [2, .98]], other_mission_neighbours=[[3, .88], [4, .77]]),
        photo("same-one", "flight-a"),
        photo("same-two", "flight-a"),
        photo("other-one", "flight-b", [[0, .88]], other_mission_neighbours=[[0, .88]]),
        photo("other-two", "flight-c"),
        photo("unknown", None, other_mission_neighbours=None),
    ]
    run_atlas(points, r"""
assert.equal(neighborMode,'all');assert.equal($('similarMissionMode').value,'all');assert.match($('similarModel').textContent,/Crownfirst test encoder/);
assert.match($('neighborSupport').textContent,/2 of 2 stored matches.*5 other photos/);
const allButton=$('neighbors').children[0].children[0];assert.match(allButton['aria-label'],/same-one.*0.990.*Same recorded mission/);
context('map').arcs=[];context('plot').arcs=[];draw();assert.deepEqual(context('map').arcs,[3,3,3,10,10,14,9]);assert.deepEqual(context('plot').arcs,[3,3,3,10,10,14,9]);
allButton.onclick();$('workspaceEnlarge').onclick();assert.equal(photoComparison.mode,'all');assert.equal(photoComparison.query,0);assert.deepEqual(photoComparison.candidates,[[1,.99],[2,.98]]);assert.match($('photoComparisonScore').textContent,/0.990/);$('closePhotoComparison').onclick();
const initial={selected,hash:location.hash,view:{...view},visible,rows:$('results').children};browsePage=2;
context('map').arcs=[];context('plot').arcs=[];$('similarMissionMode').value='other';$('similarMissionMode').focus();$('similarMissionMode').onchange();
assert.equal(selected,initial.selected);assert.equal(location.hash,initial.hash+'&missions=other&atlasPage=3');assert.deepEqual(view,initial.view);assert.equal(visible,initial.visible);assert.equal(browsePage,2);assert.equal($('results').children,initial.rows);assert.equal(document.activeElement,$('similarMissionMode'));
assert.deepEqual(context('map').arcs,[3,3,3,10,10,14,9]);assert.deepEqual(context('plot').arcs,[3,3,3,10,10,14,9]);
assert.match($('neighborSupport').textContent,/2 of 2 stored matches.*2 photos with other recorded mission IDs/);
const otherButton=$('neighbors').children[0].children[0];assert.match(otherButton['aria-label'],/other-one.*0.880.*Other recorded mission/);otherButton.onclick();$('workspaceEnlarge').onclick();
assert.equal(photoComparison.mode,'other');assert.equal(photoComparison.query,0);assert.deepEqual(photoComparison.candidates,[[3,.88],[4,.77]]);assert.match($('photoComparisonContext').textContent,/Exclude selected flight.*do not prove different trees/);assert.match($('photoComparisonScore').textContent,/0.880/);
$('nextComparison').onclick();assert.match($('photoComparisonScore').textContent,/0.770/);assert.equal($('nextComparison').disabled,true);$('nextComparison').onclick();assert.equal(photoComparison.rank,1);assert.equal(selected,0);assert.equal(location.hash,initial.hash+'&missions=other&atlasPage=3');
$('previousComparison').onclick();$('chooseComparison').onclick();assert.equal(selected,3);assert.equal(neighborMode,'other');assert.equal($('similarMissionMode').value,'other');assert.equal(location.hash,'#frame=other-one&missions=other');assert.match($('neighbors').children[0].children[0]['aria-label'],/query.*Other recorded mission/);
assert.equal(missionRelation({mission:null},{mission:null}),'Mission unknown');assert.equal(missionRelation({mission:' '},{mission:' '}),'Mission unknown');
""")


def test_missing_mission_and_old_payloads_never_fall_back_to_all_missions():
    points = [
        photo("query", "flight-a", [[1, .99]], other_mission_neighbours=[[2, .8]]),
        photo("old-payload", "flight-a", [[0, .99]]),
        photo("unknown", None, [[0, .8]], other_mission_neighbours=None),
    ]
    run_atlas(points, r"""
$('similarMissionMode').value='other';$('similarMissionMode').onchange();select(2);
assert.equal(neighborMode,'other');assert.equal($('neighbors').children.length,0);assert.match($('neighborSupport').textContent,/unavailable.*no recorded mission ID/);assert.equal(openPhotoComparison(0),false);
context('map').arcs=[];context('plot').arcs=[];draw();assert.deepEqual(context('map').arcs,[3,3,14,9]);assert.deepEqual(context('plot').arcs,[3,3,14,9]);
$('inspectPhoto').onclick();assert.equal($('photoComparison').open,true);assert.equal(photoComparison.mode,'other');assert.equal($('comparisonCandidate').hidden,true);$('closePhotoComparison').onclick();
select(1);assert.equal(neighborMode,'other');assert.equal($('neighbors').children.length,0);assert.match($('neighborSupport').textContent,/unavailable.*no stored other-mission ranking/);assert.equal(openPhotoComparison(0),false);
$('similarMissionMode').value='all';$('similarMissionMode').onchange();assert.equal($('neighbors').children.length,1);assert.match($('neighbors').children[0].children[0]['aria-label'],/query.*Same recorded mission/);
P[1].mission=null;P[0].mission=null;renderSimilarPhotos();assert.match($('neighbors').children[0].children[0]['aria-label'],/Mission unknown/);assert.doesNotMatch($('neighbors').children[0].children[0]['aria-label'],/Same recorded mission/);
P[0].label=null;data.provenance.labels.available=false;renderSimilarPhotos();assert.match($('neighbors').children[0].children[0]['aria-label'],/Recorded frame labels unavailable/);data.provenance.labels.available=true;renderSimilarPhotos();assert.match($('neighbors').children[0].children[0]['aria-label'],/No recorded frame label/);
""")


def test_known_query_with_no_eligible_missions_has_explicit_empty_state():
    points = [
        photo("query", "flight-a", [[1, .99]], other_mission_neighbours=[]),
        photo("same-mission", "flight-a"),
        photo("unknown", None),
    ]
    run_atlas(points, r"""
const hash=location.hash,initialView={...view};$('similarMissionMode').value='other';$('similarMissionMode').onchange();
assert.equal(selected,0);assert.equal(location.hash,hash+'&missions=other');assert.deepEqual(view,initialView);assert.equal($('neighbors').children.length,0);assert.match($('neighborSupport').textContent,/0 eligible photos with another recorded mission ID/);assert.equal(openPhotoComparison(0),false);
assert.deepEqual(missionViewSupport(P,0,'other'),{available:true,eligible:0,reason:'0 eligible photos with another recorded mission ID.'});
$('similarMissionMode').value='all';$('similarMissionMode').onchange();assert.equal($('neighbors').children.length,1);assert.equal(selected,0);
""")
