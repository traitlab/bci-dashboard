"""Photo chooser state is reproducible without changing catalogue context."""

from urllib.parse import urlencode

from test_atlas_mission_view import photo, run_atlas


def test_reload_restores_atlas_filters_page_and_separate_catalogue_context():
    points = [photo("query", "query-flight", label=None)] + [
        photo(f"canopy-{index:03}", "flight-b") for index in range(120)
    ]
    comparison = {
        "cohort": [[point["key"], point["label"]] for point in points[1:]],
        "frames": [],
        "invalid_common_keys": [],
        "unshared_counts": [1, 0],
        "sources": [],
    }
    context = urlencode({"search": "other catalogue text", "taxon": "Fabaceae", "page": "4", "layout": "table"})
    initial_hash = "#" + urlencode({"frame": "query", "view": "locations", "browse": context, "missions": "other", "atlasSearch": "canopy", "atlasLabels": "with", "atlasShared": "1", "atlasPage": "2"})
    run_atlas(points, r"""
assert.equal(selected,0);assert.equal(atlasView,'locations');assert.equal(neighborMode,'other');
assert.equal($('search').value,'canopy');assert.equal($('group').value,'With recorded label');assert.equal(browseSharedOnly,true);assert.equal($('sharedBrowseScope').checked,true);assert.equal(browsePage,1);
assert.equal(visible.length,120);assert.equal($('results').children.length,51);assert.equal($('results').children[1].getAttribute('data-frame'),'canopy-050');assert.equal($('browsePhotos').open,true);assert.match($('selectionStatus').textContent,/outside/);
const before=new URLSearchParams(location.hash.slice(1)),catalogue=before.get('browse');assert.equal(new URLSearchParams(catalogue).get('layout'),'table');
for(const index of [0,1]){const params=new URLSearchParams(navLinks[index].getAttribute('href').split('#')[1]);assert.equal(params.get('atlasSearch'),'canopy');assert.equal(params.get('atlasLabels'),'with');assert.equal(params.get('atlasShared'),'1');assert.equal(params.get('atlasPage'),'2');assert.equal(params.get('browse'),catalogue);assert.equal(params.get('missions'),'other');assert.equal(params.get('frame'),'query')}
const catalogueParams=new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]);assert.equal(catalogueParams.get('search'),'other catalogue text');assert.equal(catalogueParams.get('page'),'4');assert.equal(catalogueParams.get('layout'),'table');assert.equal(catalogueParams.has('atlasSearch'),false);
$('clearBrowseFilters').onclick();const cleared=new URLSearchParams(location.hash.slice(1));assert.equal(cleared.get('frame'),'query');assert.equal(cleared.get('missions'),'other');assert.equal(cleared.get('browse'),catalogue);assert.equal(cleared.has('atlasSearch'),false);assert.equal(cleared.has('atlasLabels'),false);assert.equal(cleared.has('atlasShared'),false);assert.equal(cleared.has('atlasPage'),false);assert.equal(visible.length,121);
location.hash='#'+before.toString();listeners.popstate();assert.equal(browsePage,1);assert.equal(browseSharedOnly,true);assert.equal($('group').value,'With recorded label');assert.equal($('search').value,'canopy');assert.equal(visible.length,120);
""", initial_hash=initial_hash, comparison=comparison)


def test_search_edit_history_and_page_navigation_restore_same_query():
    points = [photo("query", "flight-a")] + [photo(f"canopy-{index}", "flight-b") for index in range(110)]
    run_atlas(points, r"""
const initial=location.hash;const originalNeighbors=$('neighbors').children;
$('search').value='can';$('search').oninput();const edits=historyEntries.length;assert.equal(edits,1);
$('search').value='canopy';$('search').oninput();assert.equal(historyEntries.length,edits);assert.equal(new URLSearchParams(location.hash.slice(1)).get('atlasSearch'),'canopy');assert.equal(selected,0);assert.equal($('neighbors').children,originalNeighbors);
$('search').onblur();const filtered=location.hash;$('nextBrowsePage').onclick();assert.equal(browsePage,1);assert.equal(new URLSearchParams(location.hash.slice(1)).get('atlasPage'),'2');assert.equal($('results').children[1].getAttribute('data-frame'),'canopy-50');
location.hash=filtered;listeners.popstate();assert.equal(browsePage,0);assert.equal($('search').value,'canopy');assert.equal(selected,0);
location.hash=initial;listeners.popstate();assert.equal($('search').value,'');assert.equal(browsePage,0);assert.equal(visible.length,111);assert.equal(selected,0);
""")


def test_invalid_parameters_default_and_valid_ones_survive_missing_photo():
    run_atlas([photo("query", "flight-a"), photo("next", "flight-b")], r"""
assert.equal(requestedFrameKey,'absent');assert.equal($('search').value,'next');assert.equal($('group').value,'All frames');assert.equal(browsePage,0);assert.equal(browseSharedOnly,false);assert.deepEqual(visible,[1]);
let params=new URLSearchParams(location.hash.slice(1));assert.equal(params.has('atlasLabels'),false);assert.equal(params.has('atlasPage'),false);assert.equal(params.has('atlasShared'),false);assert.equal(params.get('frame'),'absent');
$('group').value='Without recorded label';$('group').onchange();params=new URLSearchParams(location.hash.slice(1));assert.equal(params.get('frame'),'absent');assert.equal(params.get('atlasLabels'),'without');assert.equal(params.get('atlasSearch'),'next');assert.equal(params.get('missions'),'other');
const otherModel=new URLSearchParams(navLinks[0].getAttribute('href').split('#')[1]);assert.equal(otherModel.get('frame'),'absent');assert.equal(otherModel.get('atlasLabels'),'without');assert.equal(otherModel.get('atlasSearch'),'next');
for(const value of ['0','-1','1.5','Infinity','9007199254740992','2x']){location.hash='#frame=absent&atlasPage='+value+'&atlasLabels=with';listeners.hashchange();assert.equal(browsePage,0);assert.equal($('group').value,'With recorded label');assert.equal(new URLSearchParams(location.hash.slice(1)).has('atlasPage'),false)}
location.hash='#frame=absent&atlasPage=999';listeners.hashchange();assert.equal(browsePage,0);assert.equal(new URLSearchParams(location.hash.slice(1)).has('atlasPage'),false);
""", initial_hash="#frame=absent&view=locations&missions=other&atlasSearch=next&atlasLabels=imaginary&atlasShared=yes&atlasPage=-4")


def test_copy_link_uses_current_full_url_and_reports_denial_truthfully():
    run_atlas([photo("query", "flight-a"), photo("next", "flight-b")], r"""
(async()=>{
global.location=new URL('https://example.org/crownfirst-atlas.html?release=current'+location.hash);
let copied=null;Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{async writeText(value){copied=value}}}});
$('search').value='next';$('search').oninput();$('showLocationsView').onclick();await $('copyViewLink').onclick();assert.equal(copied,location.href);assert.match(copied,/release=current/);assert.match(copied,/atlasSearch=next/);assert.match(copied,/view=locations/);assert.equal($('copyViewStatus').textContent,'View link copied.');assert.equal($('copyViewFallback').hidden,true);
$('group').value='Without recorded label';$('group').onchange();assert.equal($('copyViewStatus').textContent,'');
navigator.clipboard.writeText=async()=>{throw new Error('Permission denied')};await $('copyViewLink').onclick();assert.doesNotMatch($('copyViewStatus').textContent,/copied/i);assert.match($('copyViewStatus').textContent,/Select and copy/);assert.equal($('copyViewFallback').hidden,false);assert.equal($('copyViewFallback').value,location.href);assert.equal(document.activeElement,$('copyViewFallback'));
delete navigator.clipboard;await $('copyViewLink').onclick();assert.doesNotMatch($('copyViewStatus').textContent,/copied/i);assert.equal($('copyViewFallback').value,location.href);
})().catch(error=>{console.error(error);process.exitCode=1});
""")
