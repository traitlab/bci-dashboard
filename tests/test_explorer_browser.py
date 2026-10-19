"""Catalogue browsing preserves photo identity and evidence-source boundaries."""

import json
import runpy
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[1]
# An explicit selection: without one, the default selection follows the first match.
SELECTED = '#' + urlencode({'frame': 'a & ä /?.JPG'})


def template():
    return runpy.run_path(ROOT / "dashboard/explorer_assets.py")["HTML"]


def catalogue():
    taxa = [
        {"id": "f", "name": "Forestaceae", "rank": "family", "parent": None},
        {"id": "g", "name": "Canopia", "rank": "genus", "parent": "f"},
        {"id": "s", "name": "Canopia alba", "rank": "species", "parent": "g"},
        {"id": "t", "name": "Canopia lutea", "rank": "species", "parent": "g"},
        {"id": "other", "name": "Elseaceae", "rank": "family", "parent": None},
    ]
    photos = []
    for key, label, recorded, guess, predicted in [
        ("a & ä /?.JPG", "Canopia alba", "s", "Canopia lutea", "t"),
        ("b", "Canopia", "g", "Canopia alba", "s"),
        ("c", "Forestaceae", "f", None, None),
        ("d", None, None, "Canopia alba", "s"),
        ("e", "Old unresolved name", None, None, None),
        ("z", "Elseaceae", "other", "Elseaceae", "other"),
    ]:
        photos.append({
            "key": key, "image": "https://example.org/" + key + ".jpg",
            "mission": "flight-a", "label": label, "recorded_taxon": recorded,
            "recorded_status": "ok" if recorded else "unresolved" if label else "missing",
            "prediction": {"status": "ok" if predicted else "empty" if key == "e" else "missing", "name": guess, "taxon": predicted, "score": .812345 if predicted else None, "version": None, "project": "bcnm", "project_source": "recorded", "tied": key == "b"},
            "representation": {"version": "embedding-v1", "crop": 1280, "source_width": 4000, "source_height": 3000, "neighbours": [{"key": "z", "score": .76543}]} if key == "a & ä /?.JPG" else None,
            "annotation_url": "https://example.org/annotation/" + key if key == "b" else None,
        })
    return {"schema_version": 1, "photos": photos, "taxa": taxa, "provenance": {"predictions": {"available": True}}, "coverage": {}}


def node(script):
    if not shutil.which("node"):
        pytest.skip("Node is required to execute browser logic")
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode:
        pytest.fail(result.stderr + result.stdout, pytrace=False)


def helpers():
    return template().split("// EXPLORER_HELPERS_START")[1].split("// EXPLORER_HELPERS_END")[0]


def run_browser(checks, payload=None, initial_hash="", prelude=""):
    setup = r"""
const assert=require('node:assert/strict'),elements=new Map(),listeners={},historyEntries=[];
function make(tag='div') {return {tagName:tag,children:[],attributes:{},dataset:{},style:{setProperty(name,value){this[name]=value},removeProperty(name){delete this[name]}},value:'',isConnected:true,clientWidth:600,clientHeight:450,scrollLeft:0,scrollTop:0,naturalWidth:0,naturalHeight:0,
append(...nodes){for(const n of nodes){if(n?.tagName==='fragment')this.append(...n.children);else this.children.push(n)}},replaceChildren(...nodes){this.children=[];this.append(...nodes)},setAttribute(name,value){this.attributes[name]=String(value)},getAttribute(name){return this.attributes[name]??null},removeAttribute(name){delete this.attributes[name];if(name==='src')delete this.src;if(name==='href')delete this.href},focus(){document.activeElement=this},scrollIntoView(){this.revealed=true},showModal(){this.open=true},close(){this.open=false;this.onclose?.()},remove(){this.removed=true},querySelector(selector){const match=selector.match(/(data-taxon|data-root)="([^"]*)"/);function find(n){if(match&&n.attributes?.[match[1]]===match[2])return n;for(const child of n.children||[]){const found=find(child);if(found)return found}return null}return find(this)},get options(){return this.children}}}
function get(id){if(!elements.has(id))elements.set(id,make());return elements.get(id)}
global.document={getElementById:get,createElement:make,createDocumentFragment:()=>make('fragment'),activeElement:null};global.CSS={escape:value=>value};global.location={hash:__HASH__};global.history={pushState(_,__,hash){historyEntries.push(hash);location.hash=hash},replaceState(_,__,hash){historyEntries.push(hash);location.hash=hash}};global.window={matchMedia:()=>({matches:false,addEventListener(){}}),addEventListener(name,fn){listeners[name]=fn}};
get('explorer-data').textContent=__DATA__;
for(const [id,values] of [['source',['prediction','recorded']],['labelStatus',['all','with','without','compare']]])for(const value of values){const option=make('option');option.value=value;get(id).append(option)}
""".replace("__HASH__", json.dumps(initial_hash)).replace("__DATA__", json.dumps(json.dumps(payload or catalogue())))
    script = template().split("<script>")[1].split("</script>")[0]
    node(setup + prelude + script + checks)


def test_taxon_membership_counts_compose_without_promoting_guesses_to_labels():
    script = helpers() + "\nconst c=" + json.dumps(catalogue()) + r""";
const assert=require('node:assert/strict');
const s=readExplorerState('',c.photos);assert.equal(s.source,'prediction');
assert.deepEqual(matchingPhotoKeys(c,{...s,taxon:'s'}),['b','d']);
assert.deepEqual(matchingPhotoKeys(c,{...s,source:'recorded',taxon:'f'}),['a & ä /?.JPG','b','c']);
assert.equal(taxonCounts(c,{...s,source:'recorded'}).get('f'),3);assert.equal(taxonCounts(c,s).get('f'),3);
assert.equal(taxonCounts(c,s).get('unassigned'),2);assert.deepEqual(matchingPhotoKeys(c,{...s,taxon:'unassigned'}),['c','e']);
const composed={...s,taxon:'s',status:'with',search:'flight-a'};assert.deepEqual(matchingPhotoKeys(c,composed),['b']);assert.equal(taxonCounts(c,composed).get('s'),1);
assert.deepEqual(matchingPhotoKeys(c,{...s,taxon:'missing-taxon'}),[]);assert.deepEqual(matchingPhotoKeys(c,{...s,source:'another-model'}),[]);assert.deepEqual(matchingPhotoKeys(c,{...s,status:'bad-filter'}),[]);
c.provenance.predictions.available=false;assert.deepEqual(matchingPhotoKeys(c,s),[]);assert.deepEqual(matchingPhotoKeys(c,{...s,source:'recorded',taxon:'f'}),['a & ä /?.JPG','b','c']);
"""
    node(script)


def test_label_option_counts_are_prospective_and_compose_with_source_taxon_and_search():
    run_browser(r"""
function root(source){return $('taxonomy').children.find(n=>n.getAttribute?.('data-root')===source)}
function counts(){return Object.fromEntries($('labelStatus').options.map(o=>[o.value,Number(o.textContent.match(/\((\d+)\)$/)[1])]))}
assert.deepEqual(counts(),{all:6,with:5,without:1,compare:1});
setState({taxon:'s',search:'flight-a'});
assert.deepEqual(counts(),{all:2,with:1,without:1,compare:0});
const options=Array.from($('labelStatus').options);
$('labelStatus').focus();$('labelStatus').value='without';$('labelStatus').onchange();
assert.deepEqual(counts(),{all:2,with:1,without:1,compare:0});assert.equal($('labelStatus').value,'without');
assert.equal(document.activeElement,$('labelStatus'));assert.deepEqual($('labelStatus').options,options);
assert.match($('resultCount').textContent,/1 of 6/);assert.match($('outsideNotice').textContent,/outside these filters/);
assert.equal($('gallery').children.length,1);assert.equal(state.frame,'a & ä /?.JPG');
root('recorded').focus();root('recorded').onclick();assert.equal(state.source,'recorded');assert.equal(state.taxon,'any');
assert.deepEqual(counts(),{all:4,with:4,without:0,compare:1});assert.equal(root('recorded').getAttribute('aria-current'),'true');
assert.equal(document.activeElement,root('recorded'));
assert.equal($('labelStatus').value,'without');assert.match($('resultCount').textContent,/0 of 6/);
assert.equal($('gallery').children.length,0);
setState({status:'with'});assert.deepEqual(counts(),{all:4,with:4,without:0,compare:1});
setState({search:'no photo matches'});assert.deepEqual(counts(),{all:0,with:0,without:0,compare:0});
assert.equal($('gallery').children.length,0);assert.match($('resultCount').textContent,/0 of 6/);
""", initial_hash=SELECTED)


def test_taxon_roots_filter_by_source_and_split_the_filtered_population():
    data = catalogue()
    data['photos'][4]['prediction'].update(status='unresolved', name='Unresolved first name')
    data['photos'].append({**data['photos'][3], 'key': 'whitespace', 'label': ' \t ', 'prediction': {'status': 'missing', 'name': None}})
    run_browser(r"""
function root(source){return $('taxonomy').children.find(n=>n.getAttribute?.('data-root')===source)}
assert.deepEqual(labelStatusCounts(catalogue,state),{all:7,with:5,without:2,compare:1});
assert.equal(root('recorded').children[1].textContent,'4');assert.equal(root('prediction').children[1].textContent,'4');assert.equal(root('recorded').getAttribute('aria-current'),'false');
setState({source:'recorded',status:'with'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['a & ä /?.JPG','b','c','e','z']);
setState({taxon:'f',search:'no matches',status:'without'});assert.equal(root('recorded').children[1].textContent,'0');
setState({taxon:'',search:'',status:'all'});assert.equal(matchingPhotoKeys(catalogue,state).length,7);
setState({source:'prediction',taxon:'unassigned'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['c','e','whitespace']);
assert.equal($('browseTitle').textContent,'No Pl@ntNet guess or unresolved name');assert.match($('sourceHelp').textContent,/Taxa below use the Pl@ntNet first guess/);
setState({taxon:'any'});assert.equal($('browseTitle').textContent,'Any Pl@ntNet taxon');assert.deepEqual(matchingPhotoKeys(catalogue,state).filter(k=>['c','e','whitespace'].includes(k)),[]);assert.equal(matchingPhotoKeys(catalogue,state).length,4);
setState({source:'recorded'});assert.equal($('browseTitle').textContent,'Any recorded taxon');assert.deepEqual(matchingPhotoKeys(catalogue,state),['a & ä /?.JPG','b','c','z']);assert.equal(taxonCounts(catalogue,state).get('any'),4);assert.equal(taxonCounts(catalogue,state).get('unassigned'),3);
setState({status:'without'});assert.equal(taxonCounts(catalogue,state).get('any'),0);assert.equal(matchingPhotoKeys(catalogue,state).length,0);assert.match($('activeFilters').children[0].textContent,/^Taxon \(recorded label\): Any recorded taxon/);
setState({taxon:'unassigned',status:'all'});assert.equal($('browseTitle').textContent,'No recorded label or unresolved name');assert.match($('sourceHelp').textContent,/Taxa below use the recorded label/);setState({source:'prediction'});
assert.deepEqual(labelStatusCounts(catalogue,state),{all:3,with:2,without:1,compare:0});
""", payload=data)


def test_count_helpers_preserve_explicit_unavailable_sources_and_empty_populations():
    data = catalogue()
    data['provenance']['predictions']['available'] = False
    run_browser(r"""
assert.deepEqual(labelStatusCounts(catalogue,state),{all:0,with:0,without:0,compare:0});
function root(source){return $('taxonomy').children.find(n=>n.getAttribute?.('data-root')===source)}
assert.equal(root('prediction').disabled,true);assert.equal(root('prediction').children[0].textContent,'Pl@ntNet guesses unavailable');
assert.equal(state.source,'prediction');
setState({source:'recorded'});assert.deepEqual(labelStatusCounts(catalogue,state),{all:6,with:5,without:1,compare:0});
setState({source:'unsupported'});assert.deepEqual(labelStatusCounts(catalogue,state),{all:0,with:0,without:0,compare:0});
assert.equal(state.source,'unsupported');assert.match($('stateNotice').textContent,/taxon source unavailable/);
assert.equal(state.frame,'a & ä /?.JPG');
""", payload=data)
    data['photos'] = []
    run_browser(r"""
assert.deepEqual(labelStatusCounts(catalogue,state),{all:0,with:0,without:0,compare:0});
assert.equal($('gallery').children.length,0);assert.equal(state.frame,'');
for(const option of $('labelStatus').options)assert.match(option.textContent,/\(0\)$/);
""", payload=data)


def test_filtering_retains_unrepresented_photo_pin_and_exact_neighbor_ranking():
    run_browser(r"""
assert.equal(state.frame,'a & ä /?.JPG');assert.equal($('gallery').children.length,6);assert.match($('predictionLabel').children[0].textContent,/Canopia lutea/);assert.match($('recordedLabel').children[0].textContent,/Canopia alba/);assert.match($('predictionProvenance').textContent,/Model version not recorded/);
const image=$('selectedImage').src,neighbors=$('similar').children.map(n=>n.children[0]?.textContent),rep=JSON.stringify(photos[0].representation);
chooseTaxon('other');assert.equal(state.frame,'a & ä /?.JPG');assert.equal($('selectedImage').src,image);assert.match($('outsideNotice').textContent,/stays open in the inspector/);assert.equal($('gallery').children.some(card=>card.getAttribute('data-frame')===state.frame),false);assert.match($('resultCount').textContent,/1 of 6/);assert.deepEqual($('similar').children.map(n=>n.children[0]?.textContent),neighbors);assert.equal(JSON.stringify(photos[0].representation),rep);
setState({search:'no results'});assert.equal($('gallery').children.length,0);assert.equal($('empty').hidden,false);assert.equal($('nextPage').disabled,true);assert.match($('resultCount').textContent,/0 of 6/);
setState({frame:'b'},{focusPhoto:true});assert.equal(state.frame,'b');assert.match($('representationStatus').textContent,/unavailable.*catalogue photo remains/);assert.equal($('selectedImage').src,'https://example.org/b.jpg');assert.equal($('annotation').href,'https://example.org/annotation/b');assert.equal(document.activeElement,$('selectedTitle'));assert.match($('predictionLabel').children[1].textContent,/Tied first score/);
$('allPhotos').onclick();assert.equal(state.taxon,'');assert.equal(state.search,'');assert.equal(state.status,'all');assert.equal(state.frame,'b');
""", initial_hash=SELECTED)


def test_map_link_preserves_selected_catalogue_photo_without_a_representation():
    run_browser(r"""
let map=new URL($('cameraLocations').href,'https://example.org/');
assert.equal(map.pathname,'/embedding-atlas.html');
assert.equal(new URLSearchParams(map.hash.slice(1)).get('view'),'locations');
assert.equal(new URLSearchParams(map.hash.slice(1)).get('frame'),'a & ä /?.JPG');
setState({frame:'b'});
map=new URL($('cameraLocations').href,'https://example.org/');
assert.equal(new URLSearchParams(map.hash.slice(1)).get('frame'),'b');
assert.equal(new URLSearchParams(map.hash.slice(1)).get('view'),'locations');
""")


def test_similarity_tool_links_keep_photo_identity_even_without_model_matches():
    run_browser(r"""
function target(id){const link=$(id);assert.equal(link.getAttribute('aria-disabled'),null);return new URL(link.href,'https://example.org/')}
let similar=target('plantnetResearch'),comparison=target('crownResearch');
assert.equal(similar.pathname,'/embedding-atlas.html');assert.equal(new URLSearchParams(similar.hash.slice(1)).get('frame'),'a & ä /?.JPG');
assert.equal(comparison.pathname,'/embedding-atlas.html');assert.equal(new URLSearchParams(comparison.hash.slice(1)).get('frame'),'a & ä /?.JPG');assert.equal(new URLSearchParams(comparison.hash.slice(1)).get('view'),'models');
assert.equal($('plantnetLinkStatus').hidden,true);assert.equal($('plantnetLinkStatus').textContent,'');assert.equal($('browsePlantnet').hidden,true);
setState({frame:'b'});
similar=target('plantnetResearch');assert.equal(new URLSearchParams(similar.hash.slice(1)).get('frame'),'b');assert.equal($('plantnetLinkStatus').hidden,false);assert.match($('plantnetLinkStatus').textContent,/unavailable for this photo/);assert.equal($('browsePlantnet').hidden,false);
comparison=target('crownResearch');assert.equal(new URLSearchParams(comparison.hash.slice(1)).get('frame'),'b');assert.equal(new URLSearchParams(comparison.hash.slice(1)).get('view'),'models');
setState({frame:'missing'});
for(const id of ['cameraLocations','plantnetResearch','crownResearch']){assert.equal($(id).href,undefined);assert.equal($(id).getAttribute('aria-disabled'),'true')}
setState({frame:'a & ä /?.JPG'});assert.equal(new URLSearchParams(target('plantnetResearch').hash.slice(1)).get('frame'),state.frame);assert.equal($('plantnetLinkStatus').hidden,true);assert.equal($('plantnetLinkStatus').textContent,'');
""")


def test_empty_catalogue_has_no_selected_photo_routes():
    data = catalogue()
    data['photos'] = []
    run_browser(r"""
assert.equal(state.frame,'');for(const id of ['cameraLocations','plantnetResearch','crownResearch']){assert.equal($(id).href,undefined);assert.equal($(id).getAttribute('aria-disabled'),'true')}assert.equal($('plantnetLinkStatus').hidden,false);assert.equal($('browsePlantnet').hidden,false);
""", payload=data)


def test_explicit_coarse_taxon_survives_incomplete_parent_lineage():
    data = catalogue()
    data["taxa"].append({"id": "root-genus", "name": "Arrabidaea", "rank": "genus", "parent": None})
    data["photos"][4].update(label="Arrabidaea", recorded_taxon="root-genus", recorded_status="unresolved")
    run_browser(r"""
setState({source:'recorded',taxon:'root-genus'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['e']);assert.equal(taxonCounts(catalogue,state).get('root-genus'),1);setState({frame:'e'});assert.match($('recordedLabel').children[1].textContent,/lineage is incomplete/);
""", payload=data)


def test_gallery_loading_and_failure_states_keep_photo_identity():
    run_browser(r"""
const card=$('gallery').children[0],preview=card.children[0],message=preview.children[0],image=preview.children[1];assert.equal(message.hidden,false);assert.equal(message.textContent,'Loading photo…');assert.equal(image.hidden,false);assert.equal(image.loading,'lazy');image.onload();assert.equal(message.hidden,true);assert.equal(image.hidden,false);image.onerror();assert.equal(message.hidden,false);assert.equal(message.textContent,'Photo unavailable');assert.equal(image.hidden,true);assert.equal(card.getAttribute('data-frame'),'a & ä /?.JPG');assert.match(card.children[1].children.at(-1).textContent,/a & ä/);
""")


def test_taxonomy_omits_empty_branches_but_preserves_active_path():
    run_browser(r"""
setState({source:'recorded',search:'no matches',taxon:'s'});const tree=$('taxonomy');assert.ok(tree.querySelector('[data-taxon="f"]'));assert.ok(tree.querySelector('[data-taxon="g"]'));assert.ok(tree.querySelector('[data-taxon="s"]'));assert.equal(tree.querySelector('[data-taxon="other"]'),null);assert.equal(tree.querySelector('[data-taxon="t"]'),null);assert.equal(tree.querySelector('[data-taxon="unassigned"]'),null);assert.match($('resultCount').textContent,/0 of 6/);chooseTaxon('unassigned');assert.ok(tree.querySelector('[data-taxon="unassigned"]'));assert.equal(tree.querySelector('[data-taxon="f"]'),null);
""")


def test_visible_family_button_filters_without_expanding_first_or_duplicates():
    run_browser(r"""
const family=$('taxonomy').querySelector('[data-taxon="f"]'),disclosure=$('taxonomy').children.find(n=>n.tagName==='details'&&n.children[0].children.includes(family));assert.ok(disclosure);assert.equal(disclosure.open,false);let prevented=false,stopped=false;family.focus();family.onclick({preventDefault(){prevented=true},stopPropagation(){stopped=true}});assert.equal(prevented,true);assert.equal(stopped,true);assert.equal(state.taxon,'f');assert.deepEqual(matchingPhotoKeys(catalogue,state),['a & ä /?.JPG','b','d']);assert.equal(state.frame,'a & ä /?.JPG');assert.equal(document.activeElement,$('taxonomy').querySelector('[data-taxon="f"]'));let occurrences=0;function visit(n){if(n.getAttribute?.('data-taxon')==='f')occurrences++;for(const child of n.children||[])visit(child)}visit($('taxonomy'));assert.equal(occurrences,1);
""")


def test_breadcrumb_focus_and_unavailable_source_do_not_select_a_new_photo():
    run_browser(r"""
chooseTaxon('s');const family=$('breadcrumbs').children.find(n=>n.getAttribute('data-crumb')==='f');family.focus();family.onclick();assert.equal(state.taxon,'f');assert.equal(document.activeElement,$('breadcrumbs').children.find(n=>n.getAttribute('data-crumb')==='f'));const selected=state.frame,copy=$('gallery').children.find(card=>card.getAttribute('data-frame')===selected).children[1];setState({source:'unsupported'});assert.equal(state.frame,selected);assert.match($('stateNotice').textContent,/source unavailable/);assert.equal($('gallery').children.length,0);assert.equal(copy.children[0].textContent,'Canopia alba');assert.equal(copy.children[1].textContent,'Recorded label');
""")


def test_url_history_restores_source_taxon_search_and_identity_without_fallback():
    run_browser(r"""
const first=state.frame;setState({source:'recorded',taxon:'f',search:'flight',status:'with',frame:'c'});const saved=location.hash;setState({source:'prediction',taxon:'s',search:'',status:'without',frame:'d'});
location.hash=saved;listeners.popstate();assert.deepEqual(state,{source:'recorded',taxon:'f',search:'flight',status:'with',frame:'c',page:0});assert.equal($('taxonomy').children.find(n=>n.className==='taxa-heading').textContent,'Recorded label taxa');assert.equal($('selectedImage').src,'https://example.org/c.jpg');assert.equal($('breadcrumbs').children.at(-1).textContent,'Forestaceae');
const special={...state,frame:first,search:'à & /? #',taxon:'s'};assert.deepEqual(readExplorerState(explorerHash(special),photos),special);
location.hash='#source=absent&taxon=not-here&frame=absent';listeners.hashchange();assert.equal(state.frame,'absent');assert.match($('selectedUnavailable').textContent,/Requested photo unavailable/);assert.match($('stateNotice').textContent,/taxon source unavailable.*taxon unavailable.*No replacement/);assert.equal($('gallery').children.length,0);assert.equal($('selectedImageFrame').hidden,true);
""")


@pytest.mark.parametrize("event", ["popstate", "hashchange"])
def test_history_navigation_closes_stale_enlargement_and_focuses_restored_identity(event):
    run_browser(r"""
setState({frame:'b'});$('enlarge').focus();$('enlarge').onclick();assert.equal($('photoDialog').open,true);assert.equal($('dialogKey').textContent,'b');location.hash=explorerHash({...state,frame:'c',source:'recorded',taxon:'f'});listeners.__EVENT__();assert.equal(state.frame,'c');assert.equal($('photoDialog').open,false);assert.equal($('selectedKey').textContent,'c');assert.equal(document.activeElement,$('selectedTitle'));assert.equal($('selectedImage').src,'https://example.org/c.jpg');
""".replace("__EVENT__", event))


def test_detail_uses_loaded_pixels_and_does_not_change_photo_or_recorded_geometry():
    run_browser(r"""
const original=JSON.stringify(photos[0]),hash=location.hash;$('enlarge').focus();$('enlarge').onclick();assert.equal($('photoDialog').open,true);assert.equal($('actualImage').disabled,true);
$('detailImage').naturalWidth=2000;$('detailImage').naturalHeight=1500;$('detailImage').onload();$('actualImage').onclick();assert.equal($('detailStage').style.width,'2000px');assert.equal($('detailStage').style.height,'1500px');assert.equal($('detailViewport').scrollLeft,700);assert.equal($('detailViewport').scrollTop,525);assert.equal($('detailViewport').style.overscrollBehavior,'contain');
$('closeDialog').onclick();assert.equal(document.activeElement,$('enlarge'));assert.equal(JSON.stringify(photos[0]),original);assert.equal(location.hash,hash);$('photoDialog').scrollTop=900;$('enlarge').onclick();assert.equal($('photoDialog').scrollTop,0);assert.equal(detail.mode,'actual');$('fitImage').onclick();assert.equal($('detailViewport').style.overscrollBehavior,'auto');assert.equal($('detailStage').style.width,'100%');
$('detailImage').onerror();assert.equal($('actualImage').disabled,true);assert.equal($('detailOriginal').href,photos[0].image);assert.equal(JSON.stringify(photos[0]),original);
""")


def test_paging_keeps_the_selection_in_place_instead_of_pinning_it():
    node(helpers() + r"""
const assert=require('node:assert/strict'),keys=Array.from({length:60},(_,i)=>'p'+i),page=photoPage(keys,'outside',1);
assert.deepEqual(page.keys,keys.slice(24,48));assert.equal(page.total,60);assert.equal(page.start,25);assert.equal(page.end,48);assert.equal(page.outside,true);assert.equal(page.pages,3);
const inside=photoPage(keys,'p30',0);assert.deepEqual(inside.keys,keys.slice(0,24));assert.equal(inside.outside,false);
const only=photoPage(['selected'],'selected',7);assert.deepEqual(only.keys,['selected']);assert.equal(only.total,1);assert.equal(only.page,0);assert.equal(only.outside,false);
const none=photoPage([],'',0);assert.deepEqual(none.keys,[]);assert.equal(none.start,0);assert.equal(none.pages,1);
""")


def test_offline_builder_escapes_script_payload_and_refuses_invalid_identity(tmp_path):
    build = runpy.run_path(ROOT / "dashboard/build_explorer.py")["build"]
    data = catalogue()
    hostile = "</script><script>globalThis.injected=true</script>"
    data["photos"][0]["label"] = hostile
    source, output = tmp_path / "catalogue.json", tmp_path / "nested/explorer.html"
    source.write_text(json.dumps(data))
    build(source, output)
    html = output.read_text()
    assert hostile not in html
    payload = html.split('<script id="explorer-data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(payload)["photos"][0]["label"] == hostile
    assert "<script" not in payload
    data["photos"].append(data["photos"][0])
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate explorer key"):
        build(source, output)


def test_labelbox_correction_link_is_available_when_enlarging_the_exact_photo():
    payload = catalogue()
    payload['photos'][1]['annotation_url'] = 'https://app.labelbox.com/projects/projectB/data-rows/rowB'
    run_browser(r"""
setState({frame:'b'});$('enlarge').onclick();assert.equal($('annotation').href,photos[1].annotation_url);assert.equal($('detailAnnotation').href,photos[1].annotation_url);assert.equal($('detailAnnotation').hidden,false);assert.match($('detailAnnotationStatus').textContent,/Labelbox project access.*data refresh/);
$('closeDialog').onclick();setState({frame:'c'});$('enlarge').onclick();assert.equal($('detailAnnotation').hidden,true);assert.equal($('detailAnnotation').getAttribute('href'),null);assert.match($('detailAnnotationStatus').textContent,/No Labelbox item link/);
""", payload=payload)


def test_text_sort_uses_one_collator_and_keeps_numeric_accent_insensitive_order():
    data = catalogue()
    sample = data['photos'][0]
    labels = ['b10', 'B2', 'a', 'Á', 'é', 'e', None, ' ', 'Z', 'item 9', 'item 10', 'Éclair', 'eclair', 'b2']
    data['photos'] = [{**sample, 'key': f'k{i}', 'label': label} for i, label in enumerate(labels)]
    node(helpers() + "\nconst c=" + json.dumps(data) + r""";
const assert=require('node:assert/strict'),s=readExplorerState('',c.photos),compare=String.prototype.localeCompare;let calls=0;
String.prototype.localeCompare=function(...args){calls++;return compare.apply(this,args)};
assert.deepEqual(matchingPhotoKeys(c,{...s,order:'label-asc'}),['k2','k3','k1','k13','k0','k4','k5','k11','k12','k9','k10','k8','k6','k7']);
assert.deepEqual(matchingPhotoKeys(c,{...s,order:'label-desc'}),['k8','k10','k9','k11','k12','k4','k5','k0','k1','k13','k2','k3','k6','k7']);
assert.equal(calls,0);
""")


def test_render_scans_the_catalogue_at_most_once_per_count():
    run_browser(r"""
let scans=0;const base=basePhotoMatches;basePhotoMatches=(...args)=>{scans++;return base(...args)};
setState({order:'label-asc',search:'flight'});scans=0;render();assert.equal(scans,3*photos.length);
setState({status:'with'});scans=0;render();assert.equal(scans,4*photos.length);
assert.deepEqual(labelStatusCounts(catalogue,state),{all:6,with:5,without:1,compare:1});
""")


def test_one_history_step_restores_once_even_when_both_events_fire():
    run_browser(r"""
setState({taxon:'f'});const saved=location.hash;setState({taxon:'s'});
let renders=0;const original=render;render=()=>{renders++;original()};
location.hash=saved;listeners.popstate();listeners.hashchange();assert.equal(renders,1);assert.equal(state.taxon,'f');
location.hash='#source=recorded';listeners.hashchange();listeners.popstate();assert.equal(renders,2);assert.equal(state.source,'recorded');
setState({taxon:'g'});location.hash=saved;listeners.popstate();assert.equal(renders,4);assert.equal(state.taxon,'f');
""")


def test_root_taxon_focus_survives_rerender_without_array_children():
    run_browser(r"""
const host=$('taxonomy'),replace=host.replaceChildren;host.replaceChildren=function(...nodes){replace.apply(this,nodes);this.children.find=undefined};render();
const root=source=>Array.prototype.find.call(host.children,n=>n.getAttribute?.('data-root')===source);
root('recorded').focus();root('recorded').onclick();assert.equal(state.taxon,'any');assert.equal(document.activeElement,root('recorded'));
""")


@pytest.mark.parametrize('initial_hash,patch,expected', [
    ('', "{search:'Elseaceae'}", 'z'),
    ('#status=compare', '{}', 'a & ä /?.JPG'),
    ('#source=recorded&taxon=unassigned', '{}', 'd'),
])
def test_fresh_load_selects_the_first_match_until_a_photo_is_chosen(initial_hash, patch, expected):
    run_browser(r"""
setState(__PATCH__);assert.equal(state.frame,__EXPECTED__);assert.equal($('outsideNotice').textContent,'');assert.equal(new URLSearchParams(location.hash.slice(1)).has('frame'),false);
assert.equal($('gallery').children[0].getAttribute('aria-pressed'),'true');assert.match($('photoPosition').textContent,/^Photo 1 of/);
setState({search:'',status:'all',taxon:'',source:'prediction'});assert.equal(state.frame,'a & ä /?.JPG');
setState({frame:'c'});setState({search:'Elseaceae'});assert.equal(state.frame,'c');assert.match($('outsideNotice').textContent,/outside these filters/);assert.equal(new URLSearchParams(location.hash.slice(1)).get('frame'),'c');
""".replace('__PATCH__', patch).replace('__EXPECTED__', json.dumps(expected)), initial_hash=initial_hash)


def test_out_of_range_page_is_clamped_in_the_url_without_a_new_entry():
    run_browser(r"""
assert.equal(state.page,0);assert.equal(new URLSearchParams(location.hash.slice(1)).has('page'),false);assert.equal(new URLSearchParams(location.hash.slice(1)).get('taxon'),'f');assert.equal(historyEntries.length,1);
""", initial_hash='#taxon=f&page=9999')
