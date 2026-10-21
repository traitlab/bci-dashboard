"""Model choice stays explicit across tasks without inventing missing matches."""

import runpy
from pathlib import Path

import pytest
from test_atlas_mission_view import photo, run_atlas

ROOT = Path(__file__).resolve().parents[1]


def test_research_links_stay_in_closed_disclosure_without_model_selector():
    html = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
    research = html.split('<details id="experimentalMatching">')[1].split("</details>")[
        0
    ]
    assert 'id="plantclefPhotosLink"' in research
    assert 'id="plantclefMapLink"' in research
    assert 'id="compareModelsLink"' in research
    assert '<select id="matchingModel"' not in html
    assert "matchingModelControl" not in html
    assert "pageshow" not in html


def navigation_population():
    points = [
        photo(
            "query",
            "flight-a",
            [[1, 0.123456789]],
            other_mission_neighbours=[[1, 0.987654321]],
        )
    ] + [photo(f"canopy-{index:03}", "flight-b") for index in range(110)]
    comparison = {
        "cohort": [[point["key"], point["label"]] for point in points],
        "frames": [],
        "invalid_common_keys": [],
        "unshared_counts": [0, 0],
        "sources": [],
    }
    return points, comparison


@pytest.mark.parametrize("initial_view", ["photos", "locations", "models"])
def test_experimental_entry_and_ordinary_return_keep_frame_scope_and_filters(
    initial_view,
):
    points, comparison = navigation_population()
    run_atlas(
        points,
        r"""
assert.equal(currentMatchingModel(),'plantnet');assert.equal($('ordinaryMatchingLink').hidden,atlasView!=='models');
for(const [id,expectedView] of [['plantclefPhotosLink','photos'],['plantclefMapLink','locations']]){
 const link=$(id),destination=link.getAttribute('href');assert.equal(destination.split('#')[0],'crownfirst-atlas.html');const params=new URLSearchParams(destination.split('#')[1]);assert.equal(params.get('frame'),'query');assert.equal(params.get('view'),expectedView==='locations'?null:expectedView);assert.equal(params.get('missions'),'other');assert.equal(params.get('atlasSearch'),'canopy');assert.equal(params.get('atlasLabels'),'with');assert.equal(params.get('atlasShared'),'1');assert.equal(params.get('atlasPage'),'2');assert.equal(new URLSearchParams(params.get('browse')).get('layout'),'table');assert.equal(params.has('matchingModel'),false);
 let prevented=false;link.onclick({button:0,preventDefault(){prevented=true}});assert.equal(prevented,false);assert.equal(P[selected].key,'query');
}
assert.deepEqual(photoPair.candidates,[[1,.987654321]]);
""",
        initial_hash="#frame=query&view="
        + initial_view
        + "&browse=source%3Dprediction%26layout%3Dtable&missions=other&atlasSearch=canopy&atlasLabels=with&atlasShared=1&atlasPage=2",
        page="embedding-atlas.html",
        comparison=comparison,
    )


@pytest.mark.parametrize("initial_view", ["photos", "locations", "models"])
def test_direct_research_urls_keep_explicit_experimental_context_and_return_to_plantnet(
    initial_view,
):
    points, comparison = navigation_population()
    run_atlas(
        points,
        r"""
assert.equal(currentMatchingModel(),'plantclef');assert.match($('workspaceTitle').textContent,/Experimental/);assert.match($('matchingMethodStatus').textContent,/Experimental/);assert.equal($('ordinaryMatchingLink').hidden,false);
const returnParams=new URLSearchParams($('ordinaryMatchingLink').getAttribute('href').split('#')[1]);assert.equal($('ordinaryMatchingLink').getAttribute('href').split('#')[0],'embedding-atlas.html');assert.equal(returnParams.get('view'),atlasView==='locations'?null:'photos');assert.equal(returnParams.get('frame'),'query');assert.equal(returnParams.get('missions'),'other');assert.equal(returnParams.get('atlasSearch'),'canopy');assert.equal(returnParams.get('atlasLabels'),'with');assert.equal(returnParams.get('atlasShared'),'1');assert.equal(returnParams.get('atlasPage'),'2');assert.equal(new URLSearchParams(returnParams.get('browse')).get('layout'),'table');
for(const link of navLinks.filter(link=>['locations','photos'].includes(link.getAttribute('data-site-task')))){assert.equal(link.getAttribute('href').split('#')[0],'embedding-atlas.html');assert.equal(link.getAttribute('aria-current'),null);let prevented=false;link.onclick({button:0,preventDefault(){prevented=true}});assert.equal(prevented,false)}
let prevented=false;compareLink.onclick({button:0,preventDefault(){prevented=true}});assert.equal(prevented,true);assert.equal(atlasView,'models');assert.equal(currentMatchingModel(),'plantclef');assert.equal(compareLink.getAttribute('href').split('#')[0],'crownfirst-atlas.html');
$('showPhotosView').onclick();assert.equal(P[selected].key,'query');assert.equal(currentMatchingModel(),'plantclef');assert.match($('workspaceTitle').textContent,/Experimental PlantCLEF/);assert.equal($('ordinaryMatchingLink').hidden,false);
const catalogueContext=new URLSearchParams(catalogueHash('query','source=prediction').slice(1));assert.equal(catalogueContext.has('matchingModel'),false);
""",
        initial_hash="#frame=query&view="
        + initial_view
        + "&browse=source%3Dprediction%26layout%3Dtable&missions=other&atlasSearch=canopy&atlasLabels=with&atlasShared=1&atlasPage=2",
        page="crownfirst-atlas.html",
        comparison=comparison,
    )


def test_matching_crop_explanation_uses_recorded_size_and_keeps_unknown_unknown():
    run_atlas(
        [
            photo("query", "flight-a", crop=640, source_width=2000, source_height=1500),
            photo("unknown", "flight-b"),
        ],
        r"""
assert.match($('matchingMethodStatus').textContent,/Pl@ntNet matching.*640 × 640 px/);assert.doesNotMatch($('matchingMethodStatus').textContent,/1280/);
select(1);assert.match($('matchingMethodStatus').textContent,/Model crop footprint is not recorded/);assert.doesNotMatch($('matchingMethodStatus').textContent,/640|1280/);
""",
        page="embedding-atlas.html",
    )


@pytest.mark.parametrize(
    "atlas_page", ["embedding-atlas.html", "crownfirst-atlas.html"]
)
def test_optional_model_links_respect_published_pages(atlas_page):
    run_atlas(
        [photo("query", "flight-a")],
        r"""
const nav=document.querySelector('.site-nav');nav.setAttribute('data-photo-pages',location.pathname.slice(1));updateLinks('query');
assert.equal($('ordinaryMatchingLink').hidden,true);
for(const id of ['plantclefPhotosLink','plantclefMapLink'])assert.equal($(id).hidden,currentMatchingModel()==='plantnet');
nav.setAttribute('data-photo-pages','embedding-atlas.html crownfirst-atlas.html');updateLinks('query');
assert.equal($('ordinaryMatchingLink').hidden,currentMatchingModel()==='plantnet');
for(const id of ['plantclefPhotosLink','plantclefMapLink'])assert.equal($(id).hidden,false);
""",
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
for(const id of ['neighborSupport','workspaceCandidateEmpty','mapMatchEmpty'])assert.equal($(id).textContent,'Pl@ntNet matches unavailable for this photo.');
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
assert.match($('linkStatus').textContent,/No replacement photo is selected/);assert.equal($('photo').getAttribute('src'),null);assert.equal($('neighborSupport').textContent,'Pl@ntNet matches unavailable for this photo.');
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
