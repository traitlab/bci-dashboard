"""Photo inspection keeps the model crop, history and focus where reviewers expect them."""

import runpy

from test_atlas_mission_view import ROOT, photo, run_atlas


def cropped(key, mission, neighbours=None, **extra):
    return photo(key, mission, neighbours, source_width=4000, source_height=3000, crop=1281, **extra)


def test_model_crop_swaps_in_the_original_and_fills_the_viewport_with_the_outlined_square():
    points = [cropped("query", "flight-a", [[1, .9]]), photo("candidate", "flight-b", [[0, .9]])]
    run_atlas(points, r"""
$('workspaceEnlarge').onclick();const image=$('comparisonQueryImage'),viewport=$('comparisonQueryViewport'),crop=recordedCrop(P[0]),button=$('comparisonQueryModelCrop');
// The panels open on the 480px thumbnail; zooming must not scale that, it swaps in the original first.
image.naturalWidth=480;image.naturalHeight=360;image.onload();
assert.equal(image.src,'thumbs/480/query.webp');assert.match($('comparisonQueryDetailStatus').textContent,/^Fit\. 480 × 360 loaded pixels\.$/);assert.equal(button.disabled,false);
button.onclick();button.onclick();assert.equal(image.src,P[0].image);assert.equal($('comparisonQueryStage').style.width,'100%');assert.equal(button.getAttribute('aria-pressed'),'false');assert.equal($('comparisonQueryDetailStatus').textContent,'Loading the original image…');
image.naturalWidth=4000;image.naturalHeight=3000;image.onload();
assert.equal($('comparisonQueryOverlay').getAttribute('hidden'),null);assert.equal($('comparisonQueryOverlay').getAttribute('viewBox'),'0 0 4000 3000');assert.equal($('comparisonQueryOutline').getAttribute('width'),1281);
const width=parseFloat($('comparisonQueryStage').style.width),scale=width/4000;
assert.ok(Math.abs(crop.side*scale-Math.min(viewport.clientWidth,viewport.clientHeight))<1);assert.equal($('comparisonQueryStage').style.height,Math.round(width*3/4)+'px');
assert.ok(Math.abs(viewport.scrollLeft+viewport.clientWidth/2-(crop.x+crop.side/2)*scale)<1e-6);assert.ok(Math.abs(viewport.scrollTop+viewport.clientHeight/2-(crop.y+crop.side/2)*scale)<1e-6);
assert.equal(button.getAttribute('aria-pressed'),'true');assert.equal($('comparisonQueryFit').getAttribute('aria-pressed'),'false');
assert.match($('comparisonQueryDetailStatus').textContent,/^Model crop, the outlined 1281 px square fills the image area\. 4000 × 3000 loaded pixels\. Focus the image area/);
$('comparisonQueryFit').onclick();assert.equal($('comparisonQueryStage').style.width,'100%');assert.equal(viewport.scrollLeft,0);assert.equal(viewport.scrollTop,0);
const other=$('comparisonCandidateImage');other.naturalWidth=480;other.naturalHeight=360;other.onload();
assert.equal($('comparisonCandidateModelCrop').disabled,true);assert.equal(setImageDetailMode('comparisonCandidate','crop'),false);
""")
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    assert 'id="comparisonQueryActual"' not in html and 'id="comparisonCandidateActual"' not in html
    assert 'id="sharedQueryActual"' in html and 'id="sharedQueryModelCrop"' not in html


def test_shared_panels_without_a_crop_zoom_to_actual_pixels_of_the_original():
    run_atlas([photo("query", "flight-a")], r"""
renderSharedFrame('sharedQuery','query','Fabaceae',{labels_available:true});const image=$('sharedQueryImage'),viewport=$('sharedQueryViewport');
image.naturalWidth=480;image.naturalHeight=360;image.onload();assert.equal(image.src,'thumbs/480/query.webp');
$('sharedQueryActual').onclick();assert.equal(image.src,P[0].image);assert.equal($('sharedQueryStage').style.width,'100%');
image.naturalWidth=4000;image.naturalHeight=3000;image.onload();
assert.equal($('sharedQueryStage').style.width,'4000px');assert.equal(viewport.scrollLeft,(4000-viewport.clientWidth)/2);assert.equal(viewport.scrollTop,(3000-viewport.clientHeight)/2);
assert.match($('sharedQueryDetailStatus').textContent,/^Actual pixels, one image pixel per CSS pixel\. 4000 × 3000 loaded pixels\./);
""")


def test_model_crop_refits_after_a_resize_and_recentres_when_clicked_again():
    points = [cropped("query", "flight-a", [[1, .9]]), photo("candidate", "flight-b", [[0, .9]])]
    run_atlas(points, r"""
$('workspaceEnlarge').onclick();const image=$('comparisonQueryImage'),viewport=$('comparisonQueryViewport'),stage=$('comparisonQueryStage'),crop=recordedCrop(P[0]);
const centred=()=>{const scale=parseFloat(stage.style.width)/4000;assert.ok(Math.abs(crop.side*scale-Math.min(viewport.clientWidth,viewport.clientHeight))<1);assert.ok(Math.abs(viewport.scrollLeft+viewport.clientWidth/2-(crop.x+crop.side/2)*scale)<1e-6);assert.ok(Math.abs(viewport.scrollTop+viewport.clientHeight/2-(crop.y+crop.side/2)*scale)<1e-6)};
image.naturalWidth=480;image.naturalHeight=360;image.onload();$('comparisonQueryModelCrop').onclick();image.naturalWidth=4000;image.naturalHeight=3000;image.onload();centred();
// The pane height follows the window (48dvh), so a resize must refill and recentre the crop.
viewport.clientWidth=500;viewport.clientHeight=380;refitModelCrops();centred();
viewport.scrollLeft=0;viewport.scrollTop=0;$('comparisonQueryModelCrop').onclick();centred();
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
assert.match($('mapMatchSupport').textContent,/^All flights: Pl@ntNet matches unavailable for this photo: it has no Pl@ntNet vector in this atlas, which was drawn from 2 of 3 inventory photos\. .* 0 stored matches,/);assert.equal($('fitMatches').disabled,true);
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
