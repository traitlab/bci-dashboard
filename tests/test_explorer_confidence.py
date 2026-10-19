"""Confidence review uses raw scores, with stable order and transparent missing data."""

import copy
from urllib.parse import urlencode

import pytest
from test_atlas_mission_view import photo, run_atlas
from test_explorer_browser import catalogue, run_browser


def confidence_catalogue():
    data = catalogue()
    sample = data['photos'][0]
    data['photos'] = []
    for index, score in enumerate([.41209, .9, .9, 0, 1, None, -1, '0.8']):
        p = copy.deepcopy(sample)
        p.update(key=f'p{index}', image=f'https://example.org/{index}.jpg', annotation_url=f'https://example.org/annotation/{index}')
        p['prediction']['score'] = score
        data['photos'].append(p)
    return data


def test_raw_sort_stable_ties_missing_last_and_ordered_navigation_preserve_evidence():
    run_browser(r"""
const evidence=JSON.stringify(photos);
setState({order:'confidence-desc'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p4','p1','p2','p0','p3','p5','p6','p7']);
assert.equal(state.frame,'p0');assert.deepEqual($('gallery').children.map(card=>card.getAttribute('data-frame')),['p4','p1','p2','p0','p3','p5','p6','p7']);
assert.match($('resultCount').textContent,/Highest confidence first$/);
assert.equal($('photoPosition').textContent,'Photo 4 of 8 matching photos');
$('nextPhoto').focus();$('nextPhoto').onclick();assert.equal(state.frame,'p3');assert.equal(document.activeElement,$('nextPhoto'));
assert.equal($('selectedImage').src,'https://example.org/3.jpg');assert.equal($('annotation').href,'https://example.org/annotation/3');
$('previousPhoto').onclick();assert.equal(state.frame,'p0');
setState({order:'confidence-asc'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p3','p0','p1','p2','p4','p5','p6','p7']);
assert.equal($('photoPosition').textContent,'Photo 2 of 8 matching photos');
assert.equal(JSON.stringify(photos),evidence);
assert.ok($('gallery').children.find(card=>card.getAttribute('data-frame')==='p0').children[1].children.some(n=>n.textContent==='Pl@ntNet confidence: 0.41 / 1'));
""", payload=confidence_catalogue())


def test_inclusive_unrounded_minimum_score_presence_and_counts_compose():
    run_browser(r"""
setState({source:'recorded',taxon:'f',search:'flight-a',status:'compare',minConfidence:'.41'});
assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p1','p2','p4']);
assert.equal(taxonCounts(catalogue,state).get('s'),4);assert.equal(labelStatusCounts(catalogue,state).compare,4);
setState({minConfidence:'.41210'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2','p4']);
assert.equal(state.frame,'p0');assert.match($('outsideNotice').textContent,/outside these filters/);
setState({minConfidence:'0'});assert.equal(matchingPhotoKeys(catalogue,state).length,5);
setState({minConfidence:'1'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p4']);
setState({minConfidence:'',confidence:'missing'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p5','p6','p7']);
setState({minConfidence:'0'});assert.deepEqual(matchingPhotoKeys(catalogue,state),[]);assert.match($('confidenceHelp').textContent,/missing scores do not satisfy a minimum/);
setState({minConfidence:'',confidence:'scored'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p1','p2','p3','p4']);
catalogue.provenance.predictions.available=false;setState({status:'all',confidence:'missing'});assert.equal(matchingPhotoKeys(catalogue,state).length,8);
""", payload=confidence_catalogue())


@pytest.mark.parametrize('suffix', ['order=unknown', 'confidence=unknown', 'minConfidence=-.1', 'minConfidence=1.1', 'minConfidence=NaN', 'minConfidence=%20'])
def test_invalid_deep_link_is_explicit_without_substitution(suffix):
    run_browser(r"""
assert.deepEqual(matchingPhotoKeys(catalogue,state),[]);assert.match($('stateNotice').textContent,/confidence controls unavailable/);
assert.equal(state.frame,'p0');assert.equal($('nextPhoto').disabled,true);assert.equal($('previousPhoto').disabled,true);
""", payload=confidence_catalogue(), initial_hash='#source=recorded&frame=p0&'+suffix)


def test_confidence_controls_reset_page_and_roundtrip_history_and_atlas_context():
    run_browser(r"""
const defaultHash=explorerHash(state);assert.equal(defaultHash.includes('confidence'),false);assert.equal(defaultHash.includes('order='),false);
$('photoOrder').value='confidence-desc';$('photoOrder').onchange();assert.equal(state.order,'confidence-desc');assert.equal(state.page,0);
$('confidenceFilter').value='scored';$('confidenceFilter').onchange();$('minConfidence').value='.41';$('minConfidence').onchange();
const saved=location.hash;assert.match(saved,/minConfidence=.41/);
for(const id of ['cameraLocations','plantnetResearch','crownResearch','similarPhotosTask']){const context=new URLSearchParams(new URL($(id).href,'https://example.org').hash.slice(1)).get('browse'),p=new URLSearchParams(context);assert.equal(p.get('order'),'confidence-desc');assert.equal(p.get('confidence'),'scored');assert.equal(p.get('minConfidence'),'.41')}
setState({order:'catalogue',confidence:'all',minConfidence:''});location.hash=saved;listeners.popstate();
assert.equal(state.order,'confidence-desc');assert.equal($('minConfidence').value,'.41');
$('allPhotos').onclick();assert.equal(state.order,'confidence-desc');assert.equal(state.confidence,'all');assert.equal(state.minConfidence,'');
assert.equal(new URLSearchParams(location.hash.slice(1)).has('confidence'),false);assert.equal(new URLSearchParams(location.hash.slice(1)).get('order'),'confidence-desc');
""", payload=confidence_catalogue())
    context = urlencode({'source':'recorded','status':'compare','order':'confidence-asc','confidence':'scored','minConfidence':'.41'})
    run_atlas([photo('query','flight-a')], r"""
const params=new URLSearchParams(navLinks[2].getAttribute('href').split('#')[1]);
assert.equal(params.get('order'),'confidence-asc');assert.equal(params.get('confidence'),'scored');assert.equal(params.get('minConfidence'),'.41');
""", initial_hash='#'+urlencode({'frame':'query','browse':context}))


def test_minimum_applies_while_typing_and_waits_for_a_valid_value():
    run_browser(r"""
$('minConfidence').value='.9';$('minConfidence').oninput();assert.equal(state.minConfidence,'.9');assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2','p4']);
const cards=$('gallery').children;$('minConfidence').onchange();assert.equal($('gallery').children,cards);
$('minConfidence').value='.';$('minConfidence').oninput();assert.equal(state.minConfidence,'.9');assert.equal($('stateNotice').textContent.includes('confidence controls unavailable'),false);
$('minConfidence').onchange();assert.equal(state.minConfidence,'.');assert.match($('stateNotice').textContent,/confidence controls unavailable/);
$('minConfidence').value='';$('minConfidence').oninput();assert.equal(state.minConfidence,'');assert.equal(matchingPhotoKeys(catalogue,state).length,8);
""", payload=confidence_catalogue())
