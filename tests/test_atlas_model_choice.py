"""Model choice stays explicit across tasks without inventing missing matches."""

import runpy
from pathlib import Path

import pytest
from test_atlas_mission_view import photo, run_atlas

ROOT = Path(__file__).resolve().parents[1]


def test_experimental_model_has_secondary_disclosure_and_select_group():
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    control = html.split('<select id="matchingModel"')[1].split("</select>")[0]
    assert control.index('value="plantnet"') < control.index(
        '<optgroup label="Experimental">'
    )
    assert 'value="plantclef">PlantCLEF (experimental)' in control
    assert (
        '<details id="experimentalMatching"><summary>Experimental matching</summary>'
        in html
    )
    assert '<nav class="model-links"' not in html
    assert html.index('id="matchingModel"') < html.index('<section id="photosView"')
    assert '<button id="showModelComparisonView"' not in html


@pytest.mark.parametrize(
    "atlas_page,model,target",
    [
        ("embedding-atlas.html", "plantnet", "crownfirst-atlas.html"),
        ("crownfirst-atlas.html", "plantclef", "embedding-atlas.html"),
    ],
)
def test_model_switch_keeps_frame_view_scope_and_both_filter_contexts(
    atlas_page, model, target
):
    run_atlas(
        [
            photo(
                "query",
                "flight-a",
                [[1, 0.123456789]],
                other_mission_neighbours=[[1, 0.987654321]],
            ),
            photo("candidate", "flight-b"),
        ],
        r"""
assert.equal(browseState('matchingModel=madeup'),'');assert.equal(browseState('matchingModel=plantclef'),'');assert.equal(currentMatchingModel(),__MODEL__);assert.equal($('matchingModel').value,__MODEL__);
const before=location.hash;
const destination=matchingModelHref(__MODEL__==='plantnet'?'plantclef':'plantnet');
assert.equal(destination.split('#')[0],__TARGET__);
assert.equal('#'+destination.split('#')[1],before);
const returned=new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]);assert.equal(returned.get('atlasSearch'),'query');assert.equal(returned.get('atlasLabels'),'with');assert.equal(returned.get('missions'),'other');
const params=new URLSearchParams(destination.split('#')[1]);assert.equal(params.get('frame'),'query');assert.equal(params.get('view'),'locations');assert.equal(params.get('missions'),'other');assert.equal(params.get('atlasSearch'),'query');assert.equal(params.get('atlasLabels'),'with');
assert.equal(new URLSearchParams(params.get('browse')).get('layout'),'table');
$('matchingModel').value=__MODEL__==='plantnet'?'plantclef':'plantnet';$('matchingModel').onchange();assert.equal(location.href,destination);assert.equal($('matchingModel').value,__MODEL__);$('matchingModel').value=__MODEL__==='plantnet'?'plantclef':'plantnet';listeners.pageshow();assert.equal($('matchingModel').value,__MODEL__);
assert.equal(P[selected].key,'query');assert.deepEqual(photoPair.candidates,[[1,.987654321]]);
""".replace("__MODEL__", repr(model)).replace("__TARGET__", repr(target)),
        initial_hash="#frame=query&view=locations&browse=source%3Dprediction%26layout%3Dtable&missions=other&atlasSearch=query&atlasLabels=with",
        page=atlas_page,
    )


@pytest.mark.parametrize(
    "atlas_page,model",
    [("embedding-atlas.html", "plantnet"), ("crownfirst-atlas.html", "plantclef")],
)
def test_map_photo_navigation_and_catalogue_return_keep_the_active_model(
    atlas_page, model
):
    run_atlas(
        [photo("query", "flight-a")],
        r"""
for(const link of navLinks.filter(link=>['locations','photos'].includes(link.getAttribute('data-site-task'))))assert.equal(link.getAttribute('href').split('#')[0],__PAGE__);
assert.equal(compareLink.getAttribute('href').split('#')[0],__PAGE__);assert.equal(new URLSearchParams(compareLink.getAttribute('href').split('#')[1]).get('view'),'models');
const catalogueContext=new URLSearchParams(catalogueHash('query','source=prediction&matchingModel=plantclef').slice(1));
assert.equal(catalogueContext.get('matchingModel'),__MODEL__==='plantclef'?'plantclef':null);assert.equal(catalogueContext.get('source'),'prediction');assert.equal(catalogueContext.get('frame'),'query');
let prevented=false;compareLink.onclick({button:0,preventDefault(){prevented=true}});assert.equal(prevented,true);assert.equal(atlasView,'models');assert.equal(currentMatchingModel(),__MODEL__);assert.equal($('matchingModelControl').hidden,true);showAtlasView('photos');showAtlasView('locations');assert.equal($('matchingModelControl').hidden,false);assert.equal(P[selected].key,'query');assert.equal(currentMatchingModel(),__MODEL__);
""".replace("__PAGE__", repr(atlas_page)).replace("__MODEL__", repr(model)),
        page=atlas_page,
    )


def test_photo_without_model_data_stays_selected_mapped_and_inspectable():
    points = [
        photo(
            "query",
            "flight-a",
            [[1, 0.99]],
            model_available=False,
            xy=None,
            rgb=None,
            crop=1280,
            source_width=4000,
            source_height=3000,
        ),
        photo(
            "available",
            "flight-b",
            [[2, 0.123456789], [0, 0.99]],
            other_mission_neighbours=[[2, 0.123456789]],
        ),
        photo("also-available", "flight-c"),
    ]
    run_atlas(
        points,
        r"""
assert.equal(P[selected].key,'query');assert.equal(recordedCrop(P[selected]),null);assert.deepEqual(photoPair.candidates,[]);assert.equal($('neighbors').children.length,0);assert.equal($('mapMatchList').children.length,0);
for(const id of ['neighborSupport','workspaceCandidateEmpty','mapMatchEmpty'])assert.equal($(id).textContent,'Pl@ntNet matches unavailable for this photo');
assert.equal($('workspaceEnlarge').disabled,true);assert.equal(openPhotoComparison(0),false);assert.equal(openPhotoComparison(),true);assert.equal(photoComparison.query,0);assert.equal($('comparisonCandidate').hidden,true);$('closePhotoComparison').onclick();
draw();assert.equal(mapHits.some(row=>row[2]===0),true);assert.equal(plotHits.some(row=>row[2]===0),false);assert.equal(mapPointColour(P[0],0,1,'pca',new Map(),null),'#74858e');
assert.equal(missionViewSupport(P,1,'all').eligible,1);assert.equal(missionViewSupport(P,1,'other').eligible,1);assert.deepEqual(storedPhotoCandidates(P,1),[[2,.123456789]]);
select(1);assert.deepEqual(photoPair.candidates,[[2,.123456789]]);assert.equal($('neighbors').children.length,1);
""",
        page="embedding-atlas.html",
    )


def test_unrecorded_frame_never_shows_another_photo_as_selected():
    run_atlas(
        [photo("query", "flight-a", [[1, 0.99]]), photo("candidate", "flight-b")],
        r"""
assert.equal(P[selected].key,'not-recorded');assert.equal(P[selected].model_available,false);assert.equal($('key').textContent.includes('not-recorded'),true);assert.equal($('neighbors').children.length,0);assert.equal(mapHits.some(row=>row[2]===selected),false);
assert.match($('linkStatus').textContent,/No replacement photo is selected/);assert.equal($('photo').getAttribute('src'),null);assert.equal($('neighborSupport').textContent,'Pl@ntNet matches unavailable for this photo');
showAtlasView('locations');$('locate').onclick();$('fitMatches').onclick();assert.equal(P[selected].key,'not-recorded');assert.equal(new URLSearchParams(location.hash.slice(1)).get('frame'),'not-recorded');assert.match($('status').textContent,/2 of 2 frames/);assert.equal(visible.length,2);
location.hash='#frame=another-unknown';listeners.hashchange();assert.equal(P.length,3);assert.equal(P[selected].key,'another-unknown');assert.equal(P.some(p=>p.key==='not-recorded'),false);assert.equal(visible.length,2);
location.hash='#frame=query';listeners.hashchange();assert.equal(P.length,2);assert.equal(P[selected].key,'query');assert.equal(P.some(p=>p.inventory_available===false),false);
""",
        initial_hash="#frame=not-recorded&view=locations",
        page="embedding-atlas.html",
    )


def test_unknown_frame_cannot_create_or_reuse_review_notes():
    run_atlas(
        [photo("query", "flight-a", model_available=False)],
        r"""
assert.equal($('workspaceReviewNote').disabled,true);assert.equal($('workspaceDownloadReview').disabled,true);
$('workspaceReviewNote').value='note for unknown one';$('workspaceReviewNote').oninput();assert.equal(reviewNotes.size,0);assert.equal(currentReviewNotes().size,0);assert.equal($('workspaceReviewNote').value,'');
let downloads=0;downloadReviewJson=()=>downloads++;$('workspaceDownloadReview').onclick();assert.equal(downloads,0);
$('inspectPhoto').onclick();assert.equal($('reviewNote').disabled,true);assert.equal($('downloadReviewRecord').disabled,true);
$('reviewNote').value='dialog note for unknown one';$('reviewNote').oninput();$('downloadReviewRecord').onclick();assert.equal(downloads,0);assert.equal(reviewNotes.size,0);assert.equal(currentReviewNotes().size,0);
assert.throws(()=>reviewRecord(data,photoPair,'https://example.org/embedding-atlas.html','2026-10-16'),/cannot be reviewed/);
const injected=new Map([[reviewNoteKey(photoPair),'not an inventory photo']]);assert.equal(reviewNoteBundle(data,injected,'https://example.org/embedding-atlas.html','2026-10-16').record_count,0);
$('closePhotoComparison').onclick();location.hash='#frame=unknown-two';listeners.hashchange();assert.equal($('workspaceReviewNote').value,'');assert.equal(reviewNotes.size,0);assert.equal(currentReviewNotes().size,0);assert.equal($('workspaceReviewNote').disabled,true);
location.hash='#frame=query';listeners.hashchange();assert.equal(P[selected].key,'query');assert.equal($('workspaceReviewNote').disabled,false);assert.equal($('workspaceDownloadReview').disabled,false);assert.equal($('workspaceReviewNote').value,'');
$('workspaceReviewNote').value='real inventory photo without model matches';$('workspaceReviewNote').oninput();assert.equal(reviewNotes.size,1);assert.equal(reviewNoteBundle(data,reviewNotes,'https://example.org/embedding-atlas.html','2026-10-16').record_count,1);
$('inspectPhoto').onclick();assert.equal($('reviewNote').disabled,false);assert.equal($('downloadReviewRecord').disabled,false);assert.equal($('reviewNote').value,'real inventory photo without model matches');$('closePhotoComparison').onclick();
location.hash='#frame=unknown-three';listeners.hashchange();assert.equal($('workspaceReviewNote').value,'');assert.equal(reviewNotes.size,1);assert.equal(Array.from(currentReviewNotes().values()).filter(meaningfulReviewNote).length,1);assert.equal(reviewNoteBundle(data,reviewNotes,'https://example.org/embedding-atlas.html','2026-10-16').records[0].query.key,'query');
""",
        initial_hash="#frame=unknown-one",
        page="embedding-atlas.html",
    )
