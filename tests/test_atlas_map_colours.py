"""Map colours convey stored evidence without changing retrieval or PCA plots."""

from test_atlas_mission_view import photo, run_atlas


def map_photos():
    return [
        photo("query", "flight-a", [[1, .98], [2, -.2]], other_mission_neighbours=[[3, .4]]),
        photo("near", "flight-a", lon=-79.81),
        photo("negative", "flight-b", lon=-79.82),
        photo("other", "flight-c", lon=-79.83),
        photo("context", None, lon=-79.9),
    ]


def test_neutral_default_layers_matches_and_preserves_pca_plot():
    run_atlas(map_photos(), r"""
assert.equal(mapColourMode,'locations');assert.equal($('mapColourMode').value,'locations');assert.equal($('mapColourSummary').hidden,true);assert.equal($('mapMatchKey').style.background,'#087f72');assert.equal($('mapContextKey').style.background,'#74858e');
context('map').fills=[];context('plot').fills=[];draw();
assert.deepEqual(context('map').fills,['#74858e','#74858e','#087f72','#087f72','#74858e']);
assert.deepEqual(context('plot').fills,['#E69F00','#E69F00','#E69F00','#E69F00','#E69F00']);
assert.deepEqual(mapHits.map(row=>row[2]),[3,4,1,2,0]);
assert.match($('mapColourExplanation').textContent,/Neutral.*stored similar photos.*do not identify species/);
assert.match($('mapMatchSupport').textContent,/2 stored matches, 2 pass browse filters, 0 hidden/);
assert.match($('mapModelLabel').textContent,/Crownfirst test encoder/);
const before={hash:location.hash,selected,visible,pair:photoPair};
$('mapColourMode').value='pca';$('mapColourMode').onchange();
assert.equal(location.hash,before.hash);assert.equal(selected,before.selected);assert.equal(visible,before.visible);assert.equal(photoPair,before.pair);
assert.equal($('mapColourSummary').hidden,false);assert.match($('mapMatchKey').style.background,/linear-gradient/);assert.equal($('mapContextKey').style.background,$('mapMatchKey').style.background);
assert.match($('mapColourExplanation').textContent,/three PCA components.*Retained variance is not recorded.*do not show species, confidence or distance/);
data.provenance.pca_explained_variance=[.1,.06,.045,.01];draw();assert.match($('mapColourExplanation').textContent,/20.5%/);
context('map').fills=[];draw();assert.deepEqual(context('map').fills,['rgb(1,2,3)','rgb(1,2,3)','rgb(1,2,3)','rgb(1,2,3)','rgb(1,2,3)']);
""")


def test_similarity_uses_only_stored_scores_and_reports_filtered_support():
    run_atlas(map_photos(), r"""
const before={hash:location.hash,selected,rankings:JSON.stringify(P[0].neighbours)};
$('mapColourMode').value='similarity';$('mapColourMode').onchange();
assert.deepEqual(mapScoreScale(mapCandidates()),{min:-.2,max:.98});
assert.equal($('mapSimilarityScale').hidden,false);assert.match($('mapScaleLabels').textContent,/-0.2 lower similarity to 0.98 higher similarity.*Scale varies/);
assert.match($('mapColourExplanation').textContent,/exported cosine similarity.*Grey means no exported score, not low similarity/);
assert.equal($('mapContextLegend').textContent,'No exported similarity score');assert.equal($('mapContextKey').style.background,'#74858e');assert.match($('mapMatchKey').style.background,/linear-gradient/);assert.match($('mapColourSummary').textContent,/Grey means no exported score, not low similarity/);
assert.equal(mapPointColour(P[4],4,0,'similarity',new Map(mapCandidates()),mapScoreScale(mapCandidates())),'#74858e');
assert.equal(similarityColour(-.2,mapScoreScale(mapCandidates())),'rgb(199,232,223)');
assert.equal(similarityColour(.98,mapScoreScale(mapCandidates())),'rgb(7,94,84)');
$('search').value='near';filter();assert.deepEqual(visible,[1]);
assert.match($('mapMatchSupport').textContent,/2 stored matches, 1 pass browse filters, 1 hidden.*Selected photo stays visible/);
assert.deepEqual(mapHits.map(row=>row[2]),[1,0]);assert.deepEqual(mapScoreScale(mapCandidates()),{min:-.2,max:.98});
assert.equal(location.hash,before.hash+'&atlasSearch=near');assert.equal(selected,before.selected);assert.equal(JSON.stringify(P[0].neighbours),before.rankings);
""")


def test_single_constant_empty_and_precise_scores_have_truthful_scales():
    run_atlas(map_photos(), r"""
assert.equal(mapScoreScale([]),null);assert.equal(similarityColour(undefined,null),'#74858e');
$('mapColourMode').value='similarity';$('mapColourMode').onchange();
P[0].neighbours=[[1,-.123456],[2,-.123456]];draw();
assert.match($('mapScaleLabels').textContent,/All 2 stored matches have cosine similarity -0.123456/);
assert.equal($('mapScaleBar').style.background,'rgb(103,163,154)');assert.equal($('mapMatchKey').style.background,'rgb(103,163,154)');
P[0].neighbours=[[1,.999999],[2,.999998]];draw();assert.match($('mapScaleLabels').textContent,/0.999998 lower similarity to 0.999999 higher similarity/);
P[0].neighbours=[[1,.5]];draw();assert.match($('mapScaleLabels').textContent,/All 1 stored matches have cosine similarity 0.5/);
P[0].neighbours=[];draw();assert.equal($('mapSimilarityScale').hidden,true);assert.match($('mapColourExplanation').textContent,/No stored match scores/);
""")


def test_map_mission_control_syncs_photo_scope_and_explicit_unavailable_states():
    run_atlas(map_photos(), r"""
const before={hash:location.hash,selected,visible,view:{...view}};
$('mapMissionMode').value='other';$('mapMissionMode').onchange();
assert.equal(neighborMode,'other');assert.equal($('similarMissionMode').value,'other');assert.equal($('mapMissionMode').value,'other');
assert.deepEqual(mapCandidates(),[[3,.4]]);assert.deepEqual(photoPair.candidates,[[3,.4]]);
assert.equal(location.hash,before.hash+'&missions=other');assert.equal(selected,before.selected);assert.equal(visible,before.visible);assert.deepEqual(view,before.view);
$('similarMissionMode').value='all';$('similarMissionMode').onchange();assert.equal($('mapMissionMode').value,'all');
$('mapMissionMode').value='other';$('mapMissionMode').onchange();select(4);
assert.match($('mapMatchSupport').textContent,/unavailable.*no recorded mission ID.*0 stored matches/);
select(1);assert.match($('mapMatchSupport').textContent,/unavailable.*no stored other-mission ranking.*0 stored matches/);
P[1].other_mission_neighbours=[];P.forEach(p=>p.mission='same');draw();
assert.match($('mapMatchSupport').textContent,/0 eligible photos with another recorded mission ID.*0 stored matches/);
""")


def test_fit_matches_honours_filters_keeps_selection_and_inspection_route():
    run_atlas(map_photos(), r"""
$('search').value='near';filter();showAtlasView('locations');
const before={hash:location.hash,selected,visible,mode:neighborMode,ranking:JSON.stringify(P[0].neighbours)};
$('fitMatches').onclick();
assert.equal(view.x,(geo[0][0]+geo[1][0])/2);assert.equal(view.y,geo[0][1]);
assert.equal(location.hash,before.hash);assert.equal(selected,before.selected);assert.equal(visible,before.visible);assert.equal(neighborMode,before.mode);assert.equal(JSON.stringify(P[0].neighbours),before.ranking);
$('search').value='no-photo';filter();$('fitMatches').onclick();assert.equal(view.x,geo[0][0]);assert.equal(view.y,geo[0][1]);assert.equal(Number.isFinite(view.scale),true);
$('togglePlot').onclick();assert.equal($('returnToMap').hidden,false);$('togglePlot').onclick();assert.equal($('returnToMap').hidden,true);
$('mapInspectPhoto').onclick();assert.equal(atlasView,'photos');assert.equal(document.activeElement,$('selectedPhotoHeading'));assert.equal(selected,before.selected);assert.equal(location.hash,frameHash(P[selected].key,'photos','',neighborMode,atlasBrowseState()));
""")


def test_coincident_hit_uses_draw_priority_but_nearest_point_wins():
    run_atlas(map_photos(), r"""
const near=new Set([1,2]),order=mapLayerOrder([0,1,2,3,4],0,near);
assert.deepEqual(order,[3,4,1,2,0]);assert.equal(closestPoint(order.map(i=>[100,100,i]),100,100),0);
assert.equal(closestPoint([[100,100,4],[100,100,1]],100,100),1);
assert.equal(closestPoint([[99,100,4],[100,100,0]],99,100),4);
assert.equal(closestPoint([[100,100,0]],200,200),null);
""")


def test_ranked_map_rows_inspect_the_actual_match_without_replacing_query():
    run_atlas(map_photos(), r"""
const rows=$('mapMatchList').children,first=rows[0].children[0],second=rows[1].children[0],hash=location.hash;
assert.equal(rows.length,2);assert.equal(first.children[0].textContent,'1');assert.equal(second.children[0].textContent,'2');
assert.match(second['aria-label'],/Inspect match 2.*Frame negative.*Cosine similarity -0.2/);
assert.equal(second.children[2].children[1].textContent,'Cosine -0.2');
second.onclick();assert.equal(photoComparison.query,0);assert.equal(photoComparison.rank,1);assert.deepEqual(photoComparison.candidates,[[1,.98],[2,-.2]]);assert.equal(photoComparison.returnFocus,second);assert.equal(photoComparison,photoPair);assert.equal(selected,0);assert.equal(location.hash,hash);assert.equal($('photoComparison').open,true);
$('closePhotoComparison').onclick();assert.equal(document.activeElement,second);
$('mapMissionMode').value='other';$('mapMissionMode').onchange();const other=$('mapMatchList').children[0].children[0];other.onclick();assert.equal(photoComparison.mode,'other');assert.equal(photoComparison.query,0);assert.deepEqual(photoComparison.candidates,[[3,.4]]);assert.equal(selected,0);assert.equal(location.hash,hash+'&missions=other');
""")


def test_choosing_a_map_match_returns_focus_to_visible_map_action():
    run_atlas(map_photos(), r"""
showAtlasView('locations');$('mapMatchList').children[1].children[0].onclick();
$('chooseComparison').onclick();assert.equal(selected,2);assert.equal(atlasView,'locations');assert.equal(document.activeElement,$('mapInspectPhoto'));
select(0);showAtlasView('photos');assert.equal(openPhotoComparison(0,$('inspectPhoto')),true);$('chooseComparison').onclick();assert.equal(atlasView,'photos');assert.equal(document.activeElement,$('inspectPhoto'));
""")


def test_numbered_map_rows_keep_exported_rank_when_filters_hide_matches():
    run_atlas(map_photos(), r"""
$('search').value='negative';filter();const rows=$('mapMatchList').children,first=rows[0].children[0],second=rows[1].children[0];
assert.equal(rows.length,2);assert.equal(first.children[0].textContent,'1');assert.equal(second.children[0].textContent,'2');
assert.match(first['aria-label'],/Hidden on the map by browse filters/);assert.equal(first.children[2].children[2].textContent,'Hidden on map by filters');assert.doesNotMatch(second['aria-label'],/Hidden/);
context('map').texts=[];draw();assert.deepEqual(context('map').texts.map(row=>row[0]),['2']);assert.equal($('mapMatchList').children,rows);
second.focus();second.onfocus();assert.equal(mapHighlightedMatch,2);assert.equal(document.activeElement,second);assert.equal($('mapMatchList').children,rows);
context('map').arcs=[];draw();assert.equal(context('map').arcs.includes(13),true);assert.equal($('mapMatchList').children,rows);
second.onblur();assert.equal(mapHighlightedMatch,null);
first.onclick();assert.equal(photoComparison.rank,0);assert.equal(photoComparison.query,0);assert.equal(selected,0);assert.deepEqual(visible,[2]);
""")


def test_ranked_thumbnail_pending_failure_and_empty_states_are_explicit():
    run_atlas(map_photos(), r"""
const preview=$('mapMatchList').children[0].children[0].children[1],status=preview.children[0],image=preview.children[1];
assert.equal(image.loading,'lazy');assert.notEqual(image.hidden,true);assert.equal(status.textContent,'Loading photo');
image.onload();assert.equal(status.hidden,true);image.onerror();image.onerror();assert.equal(image.hidden,true);assert.equal(status.hidden,false);assert.equal(status.textContent,'Photo unavailable');
$('mapMissionMode').value='other';$('mapMissionMode').onchange();select(4);
assert.equal($('mapMatchList').children.length,0);assert.equal($('mapMatchEmpty').hidden,false);assert.match($('mapMatchEmpty').textContent,/no recorded mission ID/);
""")


def test_labelbox_links_follow_selected_and_compared_photos_and_clear_missing_urls():
    points = map_photos()
    points[0]['annotation_url'] = 'https://app.labelbox.com/projects/projectA/data-rows/rowA'
    points[1]['annotation_url'] = 'https://app.labelbox.com/projects/projectB/data-rows/rowB'
    points[2]['annotation_url'] = 'https://app.labelbox.com.evil.test/projects/p/data-rows/r'
    run_atlas(points, r"""
assert.equal($('mapAnnotation').href,P[0].annotation_url);assert.equal($('selectedAnnotation').href,P[0].annotation_url);assert.equal($('mapAnnotation').hidden,false);
const rows=$('mapMatchList').children;assert.equal(rows[0].children[1].href,P[1].annotation_url);assert.equal(rows[0].children[1].target,'_blank');assert.match(rows[1].children[1].textContent,/No Labelbox/);
openPhotoComparison(0);assert.equal($('comparisonQueryAnnotation').href,P[0].annotation_url);assert.equal($('comparisonCandidateAnnotation').href,P[1].annotation_url);
$('nextComparison').onclick();assert.equal($('comparisonCandidateAnnotation').hidden,true);assert.equal($('comparisonCandidateAnnotation').getAttribute('href'),null);assert.match($('comparisonCandidateAnnotationStatus').textContent,/No Labelbox item link/);
$('closePhotoComparison').onclick();select(3);assert.equal($('mapAnnotation').hidden,true);assert.equal($('selectedAnnotation').hidden,true);assert.equal($('mapAnnotation').getAttribute('href'),null);
for(const annotation_url of ['javascript:alert(1)','https://app.labelbox.com/projects/p/data-rows/r?redirect=evil','https://app.labelbox.com@evil.test/projects/p/data-rows/r','https://example.org/item'])assert.equal(labelboxItemUrl({annotation_url}),null);
""")
