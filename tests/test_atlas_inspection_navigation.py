"""Photo inspection keeps the model crop, history and focus where reviewers expect them."""

import runpy

from test_atlas_mission_view import ROOT, photo, run_atlas


def cropped(key, mission, neighbours=None, **extra):
    return photo(key, mission, neighbours, source_width=4000, source_height=3000, crop=1281, **extra)


def test_actual_pixels_centres_on_the_model_crop_and_keeps_its_outline():
    points = [cropped("query", "flight-a", [[1, .9]]), photo("candidate", "flight-b", [[0, .9]])]
    run_atlas(points, r"""
$('workspaceEnlarge').onclick();
for(const prefix of ['comparisonQuery','comparisonCandidate']){const image=$(prefix+'Image');image.naturalWidth=4000;image.naturalHeight=3000;image.onload()}
$('comparisonQueryActual').onclick();
const crop=recordedCrop(P[0]),viewport=$('comparisonQueryViewport');assert.equal(crop.x,1359);assert.equal(crop.y,859);
assert.equal(viewport.scrollLeft,crop.x+crop.side/2-viewport.clientWidth/2);assert.equal(viewport.scrollTop,crop.y+crop.side/2-viewport.clientHeight/2);
assert.equal($('comparisonQueryStage').style.width,'4000px');assert.equal($('comparisonQueryOverlay').getAttribute('hidden'),null);assert.equal($('comparisonQueryOverlay').getAttribute('viewBox'),'0 0 4000 3000');assert.equal($('comparisonQueryOutline').getAttribute('width'),1281);
assert.match($('comparisonQueryDetailStatus').textContent,/^Actual pixels, centred on the model crop\. One image pixel per CSS pixel\. 4000 × 3000 loaded pixels\. Focus the image area/);
$('comparisonQueryFit').onclick();assert.equal(viewport.scrollLeft,0);assert.equal(viewport.scrollTop,0);
$('comparisonCandidateActual').onclick();const other=$('comparisonCandidateViewport');assert.equal(other.scrollLeft,(4000-other.clientWidth)/2);assert.equal(other.scrollTop,(3000-other.clientHeight)/2);
assert.doesNotMatch($('comparisonCandidateDetailStatus').textContent,/model crop/);assert.match($('comparisonCandidateDetailStatus').textContent,/^Actual pixels, one image pixel per CSS pixel/);
""")


def test_choosing_photos_pushes_history_and_back_restores_once():
    points = [photo("query", "flight-a", [[1, .9]]), photo("first", "flight-a", [[2, .9]]), photo("second", "flight-b", [[0, .9]])]
    run_atlas(points, r"""
const card=key=>$('results').children.find(button=>button.getAttribute('data-frame')===key),start=location.hash,entries=historyEntries.length;
card('first').onclick();assert.equal(P[selected].key,'first');const first=location.hash;assert.equal(historyEntries.at(-1),first);
card('second').onclick();assert.equal(P[selected].key,'second');assert.equal(historyEntries.at(-1),location.hash);assert.equal(historyEntries.length,entries+2);
let restores=0;const original=select;select=(...args)=>{restores++;return original(...args)};
location.hash=first;listeners.popstate();listeners.hashchange();assert.equal(P[selected].key,'first');assert.equal(restores,1);
location.hash=start;listeners.popstate();listeners.hashchange();assert.equal(P[selected].key,'query');assert.equal(restores,2);
select=original;$('workspaceChooseCandidate').onclick();assert.equal(P[selected].key,'first');assert.equal(historyEntries.at(-1),location.hash);assert.equal(historyEntries.length,entries+3);
location.hash=start;listeners.hashchange();assert.equal(P[selected].key,'query');
""")


def test_focus_moves_to_match_position_at_list_ends():
    points = [photo("query", "flight-a", [[1, .9], [2, .8]]), photo("one", "flight-b"), photo("two", "flight-c")]
    run_atlas(points, r"""
const next=$('workspaceNextCandidate'),previous=$('workspacePreviousCandidate');
next.focus();next.onclick();assert.equal(next.disabled,true);assert.equal(document.activeElement,$('workspaceRank'));
previous.focus();previous.onclick();assert.equal(previous.disabled,true);assert.equal(document.activeElement,$('workspaceRank'));
next.focus();next.onclick();previous.focus();previous.onclick();assert.equal(document.activeElement,$('workspaceRank'));
openPhotoComparison(0,$('workspaceEnlarge'));$('nextComparison').focus();$('nextComparison').onclick();assert.equal($('nextComparison').disabled,true);assert.equal(document.activeElement,$('photoComparisonRank'));
""")
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    assert 'id="workspaceRank" tabindex="-1"' in html
    assert 'id="photoComparisonRank" tabindex="-1"' in html


def test_unknown_frame_shows_only_the_inventory_message():
    run_atlas([photo("query", "flight-a")], r"""
assert.equal(P[selected].key,'NOPE.JPG');assert.match($('linkStatus').textContent,/not in the recorded photo inventory/);
assert.equal($('selectionStatus').textContent,'');assert.doesNotMatch($('status').textContent,/outside/);assert.doesNotMatch($('browseCount').textContent,/outside/);
assert.equal($('botanistLabel').textContent,'');assert.equal($('inspectPhoto').disabled,true);
location.hash='#frame=query';listeners.hashchange();assert.equal($('botanistLabel').textContent,'Recorded frame label: Fabaceae');assert.equal($('inspectPhoto').disabled,false);
$('search').value='nothing';filter();assert.match($('selectionStatus').textContent,/outside the current filter/);
""", initial_hash="#frame=NOPE.JPG")


def test_locations_without_matches_punctuates_support_and_disables_fit():
    points = [photo("query", "flight-a", model_available=False), photo("matched", "flight-a", [[2, .9]]), photo("other", "flight-b", [[1, .9]])]
    run_atlas(points, r"""
assert.match($('mapMatchSupport').textContent,/^All flights: Pl@ntNet matches unavailable for this photo\. 0 stored matches,/);assert.equal($('fitMatches').disabled,true);
select(1);assert.equal($('fitMatches').disabled,false);assert.match($('mapMatchSupport').textContent,/^All flights: 1 stored matches/);
""", initial_hash="#frame=query&view=locations", page="embedding-atlas.html")


def test_toolbar_chooser_name_and_small_link_targets():
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    assert 'aria-controls="browsePhotos">Choose photo</button>' in html
    assert "Browse photos" not in html
    assert ".matching-context a,#experimentalMatching nav a,#advanced nav a{display:inline-flex;align-items:center;min-height:44px}" in html


def test_image_viewports_scroll_horizontally_with_arrow_keys_only_when_overflowing():
    run_atlas([photo("query", "flight-a", [])], r"""
for(const prefix of ['comparisonQuery','comparisonCandidate','sharedQuery','sharedCandidate']){const VIEW=$(prefix+'Viewport');const ev=(key,extra={})=>({key,prevented:false,preventDefault(){this.prevented=true},...extra});
VIEW.scrollWidth=4000;VIEW.scrollLeft=100;
let e=ev('ArrowRight');VIEW.onkeydown(e);assert.equal(VIEW.scrollLeft,140);assert.equal(e.prevented,true);
e=ev('ArrowLeft');VIEW.onkeydown(e);assert.equal(VIEW.scrollLeft,100);assert.equal(e.prevented,true);
e=ev('ArrowDown');VIEW.onkeydown(e);assert.equal(VIEW.scrollLeft,100);assert.equal(e.prevented,false);
e=ev('ArrowRight',{shiftKey:true});VIEW.onkeydown(e);assert.equal(VIEW.scrollLeft,100);assert.equal(e.prevented,false);
VIEW.scrollWidth=VIEW.clientWidth;e=ev('ArrowRight');VIEW.onkeydown(e);assert.equal(VIEW.scrollLeft,100);assert.equal(e.prevented,false);
}
""")
