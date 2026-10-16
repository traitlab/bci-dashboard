"""A photo inspection round trip retains the catalogue review population."""

import copy
from urllib.parse import urlencode

from test_atlas_mission_view import photo, run_atlas
from test_explorer_browser import catalogue, run_browser


def test_catalogue_links_carry_grouping_filters_search_and_page():
    data = catalogue()
    sample = data["photos"][0]
    data["photos"] = []
    for index in range(80):
        point = copy.deepcopy(sample)
        point["key"] = f"photo {index} & ä.JPG"
        point["mission"] = "flight-a & forêt"
        data["photos"].append(point)
    run_browser(r"""
setState({source:'recorded',taxon:'s',status:'compare',search:'a & forêt',page:2});
assert.equal(state.page,2);
for(const id of ['cameraLocations','plantnetResearch','crownResearch','similarPhotosTask','cameraMapTask','compareModelsTask']){
 const params=new URLSearchParams(new URL($(id).href,'https://example.org').hash.slice(1));
 const saved=new URLSearchParams(params.get('browse'));
 assert.equal(saved.get('source'),'recorded');assert.equal(saved.get('taxon'),'s');
 assert.equal(saved.get('status'),'compare');assert.equal(saved.get('search'),'a & forêt');
 assert.equal(saved.get('page'),'2');assert.equal(saved.has('frame'),false);
 assert.equal(params.get('frame'),state.frame);
}
""", payload=data)


def test_atlas_returns_current_photo_to_the_original_review_population():
    context = urlencode({"source": "recorded", "taxon": "s", "status": "compare",
                         "search": "a & forêt", "page": "2"})
    initial = "#" + urlencode({"frame": "query", "view": "locations", "browse": context})
    run_atlas([photo("query", "flight-a"), photo("next & ä.JPG", "flight-b")], r"""
function returned(){return new URLSearchParams(new URL(navLinks[2].getAttribute('href'),'https://example.org').hash.slice(1))}
let params=returned();assert.equal(params.get('source'),'recorded');assert.equal(params.get('taxon'),'s');
assert.equal(params.get('status'),'compare');assert.equal(params.get('search'),'a & forêt');
assert.equal(params.get('page'),'2');assert.equal(params.get('frame'),'query');
$('showModelComparisonView').onclick();select(1);
params=returned();assert.equal(params.get('frame'),'next & ä.JPG');assert.equal(params.get('status'),'compare');
const current=new URLSearchParams(location.hash.slice(1));assert.equal(current.get('view'),'models');
assert.equal(new URLSearchParams(current.get('browse')).get('search'),'a & forêt');
for(const link of [navLinks[0],navLinks[1],navLinks[3]])assert.equal(new URLSearchParams(new URL(link.getAttribute('href'),'https://example.org').hash.slice(1)).get('browse'),current.get('browse'));
location.hash='#frame=query';listeners.hashchange();assert.equal(returned().has('source'),false);
""", initial_hash=initial)


def test_return_context_never_changes_the_destination_or_reuses_a_stale_frame():
    context = urlencode({"source": "recorded", "status": "compare", "frame": "old",
                         "redirect": "https://example.org/elsewhere", "browse": "nested"})
    initial = "#" + urlencode({"frame": "absent", "view": "models", "browse": context})
    run_atlas([photo("query", "flight-a")], r"""
let link=navLinks[2].getAttribute('href');assert.equal(link.split('#')[0],'explorer.html');
let params=new URLSearchParams(link.split('#')[1]);assert.equal(params.get('frame'),'absent');
assert.equal(params.get('source'),'recorded');assert.equal(params.get('status'),'compare');
assert.equal(params.has('redirect'),false);assert.equal(params.has('browse'),false);
select(0);params=new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]);
assert.equal(params.get('frame'),'query');assert.equal(params.get('status'),'compare');
""", initial_hash=initial)


def test_top_level_atlas_tasks_keep_selection_filters_and_history_in_one_page():
    context = urlencode({"source": "recorded", "status": "compare", "page": "2"})
    initial = "#" + urlencode({"frame": "next & ä.JPG", "view": "locations", "browse": context})
    run_atlas([photo("query", "flight-a"), photo("next & ä.JPG", "flight-b")], r"""
const original=location.hash;
function activeTask(){return navLinks.filter(link=>link.getAttribute('data-site-task')&&link.getAttribute('aria-current')==='page').map(link=>link.getAttribute('data-site-task'))}
assert.deepEqual(activeTask(),['locations']);assert.equal($('workspaceTitle').textContent,'Drone map');assert.match($('workspaceDescription').textContent,/drone photo location.*not tree locations/);
for(const [index,view] of [[3,'photos'],[4,'locations'],[5,'models']]){
 const params=new URLSearchParams(navLinks[index].getAttribute('href').split('#')[1]);
 assert.equal(params.get('frame'),'next & ä.JPG');assert.equal(params.get('view')||'photos',view);
 assert.equal(new URLSearchParams(params.get('browse')).get('status'),'compare');
}
let prevented=false;
navLinks[5].onclick({button:0,preventDefault(){prevented=true}});
assert.equal(prevented,true);assert.equal(historyEntries.length,1);
assert.equal(selected,1);assert.equal(atlasView,'models');assert.deepEqual(activeTask(),['models']);assert.equal($('workspaceTitle').textContent,'Compare models');
const modelHash=location.hash;
assert.equal(new URLSearchParams(location.hash.slice(1)).get('browse'),new URLSearchParams(original.slice(1)).get('browse'));
navLinks[5].onclick({button:0,preventDefault(){}});assert.equal(historyEntries.length,1);
location.hash=original;listeners.popstate();assert.deepEqual(activeTask(),['locations']);assert.equal(selected,1);
location.hash=modelHash;listeners.hashchange();assert.deepEqual(activeTask(),['models']);assert.equal(selected,1);
prevented=false;navLinks[4].onclick({button:0,ctrlKey:true,preventDefault(){prevented=true}});assert.equal(prevented,false);assert.equal(atlasView,'models');
prevented=false;navLinks[3].onclick({button:0,preventDefault(){prevented=true}});assert.equal(prevented,false);
""", initial_hash=initial)


def test_global_map_and_comparison_links_remain_available_for_an_empty_catalogue():
    data = catalogue()
    data["photos"] = []
    run_browser(r"""
for(const [id,view] of [['cameraMapTask','locations'],['compareModelsTask','models']]){
 const url=new URL($(id).href,'https://example.org');
 assert.equal(url.pathname,'/crownfirst-atlas.html');
 const params=new URLSearchParams(url.hash.slice(1));assert.equal(params.get('view'),view);assert.equal(params.has('frame'),false);
}
""", payload=data)
