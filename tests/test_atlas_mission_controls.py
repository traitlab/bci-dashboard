"""Flight controls show the real effect and preserve it across navigation."""

import json

import pytest

from test_atlas_mission_view import photo, run_atlas
from test_explorer_browser import run_browser


FLIGHTS = [
    photo("query", "20260114_bciarmour_wptne01_m3e", [[1, .99], [2, .9], [3, .85]], other_mission_neighbours=[[2, .9], [4, .8], [3, .85]]),
    photo("same", "20260114_bciarmour_wptne01_m3e"), photo("near", "20251017_bciarmour_wptne_m3e"),
    photo("near-two", "20251017_bciarmour_wptne_m3e"), photo("far", "20241226_bcitbarbour3o_wptover100norte_m3e"),
]


def test_flight_picker_names_this_photos_flight_and_counts_each_stored_flight():
    run_atlas(FLIGHTS, r"""
const labels=id=>Array.from($(id).options,option=>option.textContent);
assert.deepEqual(labels('similarMissionMode'),['Any flight (3 matches)','Other flights (3 matches)','2024-12-26 · bcitbarbour3o wptover100norte m3e (1 match)','2025-10-17 · bciarmour wptne m3e (2 matches)','This photo’s flight · 2026-01-14 · bciarmour wptne01 m3e (1 match)']);
assert.deepEqual(labels('mapMissionMode'),labels('similarMissionMode'));
assert.deepEqual(Array.from($('similarMissionMode').options,option=>option.disabled),[false,false,false,false,false]);
assert.match($('similarMissionHelp').textContent,/^This photo: flight 2026-01-14 · bciarmour wptne01 m3e\. .*does not search that whole flight\.$/);
assert.equal($('mapMissionHelp').textContent,$('similarMissionHelp').textContent);
""")


def test_picking_a_flight_filters_stored_matches_and_survives_navigation():
    run_atlas(FLIGHTS, r"""
const flight='20251017_bciarmour_wptne_m3e';
$('similarMissionMode').value=flight;$('similarMissionMode').onchange();
assert.deepEqual(photoPair.candidates,[[2,.9],[3,.85]]);assert.equal($('mapMissionMode').value,flight);
assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),flight);assert.equal(new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]).get('missions'),flight);
assert.match($('neighborSupport').textContent,/^2 stored matches from this flight, filtered from this photo’s stored top matches, not re-ranked among the flight’s 2 photos\.$/);
const picked=location.hash;
select(4);assert.equal(neighborMode,flight);assert.equal($('similarMissionMode').value,flight);
assert.deepEqual(Array.from($('similarMissionMode').options).filter(option=>option.value===flight).map(option=>[option.textContent,option.disabled]),[['2025-10-17 · bciarmour wptne m3e (0 matches)',true]]);
location.hash='#frame=query&view=photos&missions=other';listeners.hashchange();assert.equal(neighborMode,'other');assert.deepEqual(photoPair.candidates,[[2,.9],[4,.8],[3,.85]]);
location.hash='#frame=query';listeners.popstate();assert.equal(neighborMode,'all');assert.deepEqual(photoPair.candidates,[[1,.99],[2,.9],[3,.85]]);
location.hash='#frame=query&missions=not-a-flight';listeners.hashchange();assert.equal(neighborMode,'all');
location.hash=picked;listeners.hashchange();assert.equal(neighborMode,flight);assert.deepEqual(photoPair.candidates,[[2,.9],[3,.85]]);
const bundle=reviewNoteBundle(data,new Map([[JSON.stringify([0,3,flight]),'same crown?']]),'https://example.org/embedding-atlas.html','2026-01-01T00:00:00Z');
assert.equal(bundle.records[0].relationship.mode,flight);assert.equal(bundle.records[0].candidate.key,'near-two');
""")


def test_old_other_mode_links_still_restore_and_sync_both_controls():
    run_atlas([
        photo("query", "flight-a", [[1, .99], [2, .9]], other_mission_neighbours=[[2, .9], [3, .8]]),
        photo("same", "flight-a"), photo("other", "flight-b"), photo("new", "flight-c"),
    ], r"""
assert.equal(neighborMode,'other');assert.deepEqual(photoPair.candidates,[[2,.9],[3,.8]]);
assert.equal($('similarMissionMode').value,'other');assert.equal($('mapMissionMode').value,'other');
assert.equal(new URLSearchParams(navLinks[0].getAttribute('href').split('#')[1]).get('missions'),'other');
assert.equal(new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]).get('missions'),'other');
$('showLocationsView').onclick();assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),'other');
select(2);assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),'other');
$('mapMissionMode').value='all';$('mapMissionMode').onchange();assert.equal(neighborMode,'all');assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),null);
""", initial_hash="#frame=query&view=photos&missions=other")


def test_identical_flight_rankings_say_so_in_plain_words():
    run_atlas([
        photo("query", "flight-a", [[1, .9]], other_mission_neighbours=[[1, .9]]),
        photo("other", "flight-b"),
    ], r"""
assert.match($('similarMissionHelp').textContent,/Any flight and Other flights give the same matches here/);
$('mapMissionMode').value='other';$('mapMissionMode').onchange();
assert.equal(neighborMode,'other');assert.equal(photoPair.candidates[0][0],1);
""")


def test_empty_choices_are_disabled_not_hidden():
    run_atlas([photo("query", "flight-a", [[1, .9]], other_mission_neighbours=[]), photo("same", "flight-a")], r"""
assert.deepEqual(Array.from($('similarMissionMode').options,option=>[option.textContent,option.disabled]),[['Any flight (1 match)',false],['Other flights (0 matches)',true],['This photo’s flight · flight-a (1 match)',false]]);
""")


def test_unavailable_flight_ranking_is_disabled_with_a_reason():
    run_atlas([photo("query", None, [[1, .9]]), photo("next", "flight-b")], r"""
assert.equal($('similarMissionMode').options[1].disabled,true);
assert.match($('similarMissionHelp').textContent,/no recorded mission ID/);
assert.equal(neighborMode,'other');assert.equal(photoPair.candidates.length,0);
assert.match($('neighborSupport').textContent,/unavailable/);
""", initial_hash="#frame=query&missions=other")


@pytest.mark.parametrize("missions", ["other", "20251017_bciarmour_wptne_m3e", None])
def test_catalogue_round_trip_keeps_the_selected_flight_scope(missions):
    run_browser(r"""
const M=__MISSIONS__;assert.equal(state.missions??null,M);
setState({status:'compare'});
assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),M);
for(const id of ['cameraMapTask','compareModelsTask','similarPhotosTask','cameraLocations','crownResearch']){
 assert.equal(new URLSearchParams(new URL($(id).href,'https://example.org').hash.slice(1)).get('missions'),M);
}
""".replace("__MISSIONS__", json.dumps(missions)), initial_hash="#frame=b" + (f"&missions={missions}" if missions else ""))


def test_each_card_names_its_flight_and_marks_this_photos_flight():
    run_atlas(FLIGHTS, r"""
const cards=()=>$('neighbors').children.map(li=>li.children[0]),flights=()=>cards().map(button=>button.children.at(-1).children.find(child=>child.className==='similar-mission').textContent);
assert.deepEqual(flights(),['This photo’s flight','2025-10-17 · bciarmour wptne m3e','2025-10-17 · bciarmour wptne m3e']);
assert.match(cards()[0]['aria-label'],/^Fabaceae\. Frame same\. .* This photo’s flight$/);
$('similarMissionMode').value='other';$('similarMissionMode').onchange();
assert.deepEqual(flights(),['2025-10-17 · bciarmour wptne m3e','2024-12-26 · bcitbarbour3o wptover100norte m3e','2025-10-17 · bciarmour wptne m3e']);
""")


def test_missing_alternative_export_disables_the_option_without_faking_matches():
    run_atlas([photo("query", "flight-a", [[1, .9]]), photo("other", "flight-b")], r"""
assert.equal($('similarMissionMode').options[1].disabled,true);
assert.match($('similarMissionMode').options[1].textContent,/unavailable/);
assert.match($('similarMissionHelp').textContent,/no stored other-mission ranking/);
""")
