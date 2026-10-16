"""Flight controls show the real effect and preserve it across navigation."""

from test_atlas_mission_view import photo, run_atlas
from test_explorer_browser import run_browser


def test_distinct_flight_rankings_show_counts_and_new_matches():
    run_atlas([
        photo("query", "flight-a", [[1, .99], [2, .9]], other_mission_neighbours=[[2, .9], [3, .8]]),
        photo("same", "flight-a"), photo("other", "flight-b"), photo("new", "flight-c"),
    ], r"""
const options=$('similarMissionMode').options;
assert.equal(options[0].textContent,'All flights (2 matches)');
assert.equal(options[1].textContent,'Exclude selected flight (2 matches, 1 new)');
assert.match($('similarMissionHelp').textContent,/Selected flight: flight-a/);
assert.match($('similarMissionHelp').textContent,/1 from the selected flight/);
$('similarMissionMode').value='other';$('similarMissionMode').onchange();
assert.deepEqual(photoPair.candidates,[[2,.9],[3,.8]]);
assert.equal($('mapMissionMode').value,'other');assert.equal($('mapMissionHelp').textContent,$('similarMissionHelp').textContent);
assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),'other');
assert.equal(new URLSearchParams(navLinks[0].getAttribute('href').split('#')[1]).get('missions'),'other');
assert.equal(new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]).get('missions'),'other');
const alternate=location.hash;
$('showLocationsView').onclick();assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),'other');
select(2);assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),'other');
location.hash='#frame=query';listeners.popstate();assert.equal(neighborMode,'all');
location.hash=alternate;listeners.hashchange();assert.equal(neighborMode,'other');assert.deepEqual(photoPair.candidates,[[2,.9],[3,.8]]);
""")


def test_identical_flight_rankings_explain_why_nothing_changes():
    run_atlas([
        photo("query", "flight-a", [[1, .9]], other_mission_neighbours=[[1, .9]]),
        photo("other", "flight-b"),
    ], r"""
assert.match($('similarMissionMode').options[1].textContent,/1 match, same matches/);
assert.match($('similarMissionHelp').textContent,/Both choices return the same stored matches/);
$('mapMissionMode').value='other';$('mapMissionMode').onchange();
assert.equal(neighborMode,'other');assert.equal(photoPair.candidates[0][0],1);
assert.match($('mapMissionHelp').textContent,/same stored matches/);
""")


def test_unavailable_flight_ranking_is_disabled_with_a_reason():
    run_atlas([photo("query", None, [[1, .9]]), photo("next", "flight-b")], r"""
assert.equal($('similarMissionMode').options[1].disabled,true);
assert.match($('similarMissionHelp').textContent,/no recorded mission ID/);
assert.equal(neighborMode,'other');assert.equal(photoPair.candidates.length,0);
assert.match($('neighborSupport').textContent,/unavailable/);
""", initial_hash="#frame=query&missions=other")


def test_catalogue_round_trip_keeps_the_selected_flight_scope():
    run_browser(r"""
assert.equal(state.missions,'other');
setState({status:'compare'});
assert.equal(new URLSearchParams(location.hash.slice(1)).get('missions'),'other');
for(const id of ['cameraMapTask','compareModelsTask','similarPhotosTask','cameraLocations','crownResearch']){
 assert.equal(new URLSearchParams(new URL($(id).href,'https://example.org').hash.slice(1)).get('missions'),'other');
}
""", initial_hash="#frame=b&missions=other")


def test_same_photos_reordered_are_distinct_from_identical_rankings():
    run_atlas([
        photo("query", "flight-a", [[1, .9], [2, .8]], other_mission_neighbours=[[2, .9], [1, .8]]),
        photo("one", "flight-b"), photo("two", "flight-c"),
    ], r"""
assert.match($('similarMissionMode').options[1].textContent,/2 matches, reordered/);
assert.match($('similarMissionHelp').textContent,/same photos; their stored scores or order differ/);
$('similarMissionMode').value='other';$('similarMissionMode').onchange();assert.equal(photoPair.candidates[0][0],2);
""")


def test_removal_without_new_matches_reports_the_actual_effect():
    run_atlas([
        photo("query", "flight-a", [[1, .9], [2, .8]], other_mission_neighbours=[[2, .8]]),
        photo("same", "flight-a"), photo("other", "flight-b"),
    ], r"""
assert.match($('similarMissionMode').options[1].textContent,/1 match, 1 removed/);
assert.match($('similarMissionHelp').textContent,/removes 1 of the all-flight matches/);
""")


def test_missing_alternative_export_disables_the_option_without_faking_matches():
    run_atlas([photo("query", "flight-a", [[1, .9]]), photo("other", "flight-b")], r"""
assert.equal($('similarMissionMode').options[1].disabled,true);
assert.match($('similarMissionMode').options[1].textContent,/unavailable/);
assert.match($('similarMissionHelp').textContent,/no stored other-mission ranking/);
""")
