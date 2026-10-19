"""Confidence review uses raw scores, with stable order and transparent missing data."""

import copy
import runpy
from urllib.parse import urlencode

import pytest
from test_atlas_mission_view import photo, run_atlas
from test_explorer_browser import ROOT, catalogue, run_browser


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
""", payload=confidence_catalogue(), initial_hash='#frame=p0')


def test_inclusive_unrounded_minimum_score_presence_and_counts_compose():
    run_browser(r"""
setState({source:'recorded',taxon:'f',search:'flight-a',status:'compare',minConfidence:'.41'});
assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p1','p2','p4']);
assert.equal(taxonCounts(catalogue,state).get('s'),4);assert.equal(labelStatusCounts(catalogue,state).compare,4);
setState({minConfidence:'.41210'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2','p4']);
assert.equal(state.frame,'p0');assert.match($('outsideNotice').textContent,/outside these filters/);
setState({minConfidence:'0'});assert.equal(matchingPhotoKeys(catalogue,state).length,5+3);setState({minConfidence:'.01'});assert.equal(matchingPhotoKeys(catalogue,state).length,4);
setState({minConfidence:'1'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p4']);
setState({minConfidence:'',confidence:'missing'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p5','p6','p7']);
setState({minConfidence:'.5'});assert.deepEqual(matchingPhotoKeys(catalogue,state),[]);assert.match($('confidenceHelp').textContent,/missing scores do not satisfy a narrowed range/);setState({minConfidence:'0',maxConfidence:'1'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p5','p6','p7']);setState({minConfidence:'',maxConfidence:''});
setState({minConfidence:'',confidence:'scored'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p1','p2','p3','p4']);
catalogue.provenance.predictions.available=false;setState({status:'all',confidence:'missing'});assert.equal(matchingPhotoKeys(catalogue,state).length,8);
""", payload=confidence_catalogue(), initial_hash='#frame=p0')


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
setState({confidence:'scored'});$('minConfidence').value='.41';$('minConfidence').onchange();
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
$('minConfidence').onchange();assert.equal(state.minConfidence,'.9');assert.equal($('minConfidence').value,'.');assert.equal($('stateNotice').textContent.includes('confidence controls unavailable'),false);
$('minConfidence').value='';$('minConfidence').oninput();assert.equal(state.minConfidence,'');assert.equal(matchingPhotoKeys(catalogue,state).length,8);
""", payload=confidence_catalogue())


@pytest.mark.parametrize('field', ['minConfidence', 'filterConfidence'])
def test_minimum_accepts_comma_decimals_and_never_commits_an_invalid_value(field):
    run_browser(r"""
const input=$(__FIELD__),other=$(__FIELD__==='minConfidence'?'filterConfidence':'minConfidence'),error=$(__FIELD__+'Error');
input.value='0,9';input.oninput();assert.equal(state.minConfidence,'0.9');assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2','p4']);assert.equal(other.value,'0.9');
input.value='abc';input.oninput();assert.equal(state.minConfidence,'0.9');input.onchange();
assert.equal(state.minConfidence,'0.9');assert.equal(input.value,'abc');assert.equal(input.getAttribute('aria-invalid'),'true');assert.equal(error.hidden,false);assert.match(error.textContent,/number from 0 to 1/);
assert.equal(other.getAttribute('aria-invalid'),null);assert.match($('resultCount').textContent,/^3 of 8/);assert.equal(new URLSearchParams(location.hash.slice(1)).get('minConfidence'),'0.9');
input.value='0,41209';input.oninput();assert.equal(state.minConfidence,'0.41209');assert.equal(input.getAttribute('aria-invalid'),null);assert.equal(error.hidden,true);
setState({minConfidence:''});input.value='1,5';input.onchange();assert.equal(state.minConfidence,'');assert.equal(input.value,'1,5');assert.equal(input.getAttribute('aria-invalid'),'true');
""".replace('__FIELD__', repr(field)), payload=confidence_catalogue())


def test_only_without_score_checkbox_replaces_the_score_select_and_disables_the_minimum():
    html = runpy.run_path(ROOT / 'dashboard/explorer_assets.py')['HTML']
    assert 'id="confidenceFilter"' not in html and 'Has score</option>' not in html
    assert '<input id="missingScore" type="checkbox" aria-describedby="confidenceHelp">Only photos without a score</label>' in html
    run_browser(r"""
setState({minConfidence:'.5'});$('missingScore').checked=true;$('missingScore').onchange();
assert.equal(state.confidence,'missing');assert.equal(state.minConfidence,'');assert.deepEqual(matchingPhotoKeys(catalogue,state),['p5','p6','p7']);
assert.equal(new URLSearchParams(location.hash.slice(1)).get('confidence'),'missing');
for(const id of ['minConfidence','maxConfidence','filterConfidence','filterMaxConfidence'])assert.equal($(id).disabled,true);assert.match($('confidenceHelp').textContent,/missing scores do not satisfy a narrowed range/);
$('missingScore').checked=false;$('missingScore').onchange();assert.equal(state.confidence,'all');assert.equal(matchingPhotoKeys(catalogue,state).length,8);
for(const id of ['minConfidence','maxConfidence','filterConfidence','filterMaxConfidence'])assert.equal($(id).disabled,false);assert.equal($('confidenceHelp').textContent.includes('missing scores'),false);
""", payload=confidence_catalogue())
    run_browser(r"""
assert.equal($('missingScore').checked,true);assert.equal($('minConfidence').disabled,true);assert.deepEqual(matchingPhotoKeys(catalogue,state),['p5','p6','p7']);
""", payload=confidence_catalogue(), initial_hash='#confidence=missing')


def test_legacy_has_score_link_still_filters_and_its_chip_removes_it():
    run_browser(r"""
assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p1','p2','p3','p4']);assert.equal($('missingScore').checked,false);assert.equal($('minConfidence').disabled,false);
const chip=$('activeFilters').children.find(button=>button.getAttribute('data-filter')==='confidence');assert.match(chip.textContent,/Has score/);
chip.onclick();assert.equal(state.confidence,'all');assert.equal(matchingPhotoKeys(catalogue,state).length,8);assert.equal(new URLSearchParams(location.hash.slice(1)).has('confidence'),false);
""", payload=confidence_catalogue(), initial_hash='#confidence=scored')


def test_score_range_defaults_keep_unscored_photos_and_narrowing_drops_them():
    html = runpy.run_path(ROOT / 'dashboard/explorer_assets.py')['HTML']
    for field, value in [('minConfidence', '0'), ('maxConfidence', '1')]:
        assert f'<input id="{field}" type="text" inputmode="decimal" value="{value}"' in html
    run_browser(r"""
assert.equal($('minConfidence').value,'0');assert.equal($('maxConfidence').value,'1');assert.equal($('filterConfidence').value,'0');assert.equal($('filterMaxConfidence').value,'1');
assert.equal(matchingPhotoKeys(catalogue,state).length,8);assert.equal(explorerHash(state).includes('Confidence'),false);
setState({minConfidence:'0',maxConfidence:'1'});assert.equal(matchingPhotoKeys(catalogue,state).length,8);assert.equal(explorerHash(state).includes('Confidence'),false);
setState({minConfidence:'',maxConfidence:'.9'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p1','p2','p3']);
setState({maxConfidence:'.41209'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p3']);
setState({minConfidence:'.9',maxConfidence:'.9'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2']);
setState({minConfidence:'0',maxConfidence:'.5'});assert.deepEqual(matchingPhotoKeys(catalogue,state),['p0','p3']);
assert.match(new URLSearchParams(explorerHash(state).slice(1)).get('maxConfidence'),/^.5$/);
const chips=$('activeFilters').children.map(button=>button.getAttribute('data-filter')).filter(Boolean);assert.deepEqual(chips,['maxConfidence']);
$('activeFilters').children[0].onclick();assert.equal(state.maxConfidence,'');assert.equal(matchingPhotoKeys(catalogue,state).length,8);
""", payload=confidence_catalogue())


def test_lower_above_upper_is_rejected_inline_and_never_committed():
    run_browser(r"""
for(const [id,other] of [['minConfidence','maxConfidence'],['filterConfidence','filterMaxConfidence']]){
setState({minConfidence:'',maxConfidence:'.5'});$(id).value='.8';$(id).oninput();assert.equal(state.minConfidence,'');
$(id).onchange();assert.equal(state.minConfidence,'');assert.equal($(id).value,'.8');assert.equal($(id).getAttribute('aria-invalid'),'true');
assert.match($(id+'Error').textContent,/lower score must not be above the upper/);assert.equal($(id+'Error').hidden,false);
$(id).value='.2';$(id).oninput();assert.equal(state.minConfidence,'.2');assert.equal($(id).getAttribute('aria-invalid'),null);assert.equal($(id+'Error').hidden,true)}
setState({minConfidence:'',maxConfidence:'.5'});$('maxConfidence').value='-1';$('maxConfidence').onchange();assert.match($('maxConfidenceError').textContent,/number from 0 to 1/);assert.equal(state.maxConfidence,'.5');
""", payload=confidence_catalogue())
    run_browser(r"""
assert.deepEqual(matchingPhotoKeys(catalogue,state),[]);assert.match($('stateNotice').textContent,/confidence controls unavailable/);
""", payload=confidence_catalogue(), initial_hash='#source=recorded&frame=p0&minConfidence=.8&maxConfidence=.2')


def test_old_minimum_link_reads_as_the_lower_bound_and_upper_bound_roundtrips():
    run_browser(r"""
assert.equal(state.minConfidence,'.9');assert.equal($('minConfidence').value,'.9');assert.equal($('maxConfidence').value,'1');
assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2','p4']);
$('maxConfidence').value='.95';$('maxConfidence').oninput();assert.deepEqual(matchingPhotoKeys(catalogue,state),['p1','p2']);
const saved=location.hash;assert.match(saved,/minConfidence=.9/);assert.match(saved,/maxConfidence=.95/);
const context=new URLSearchParams(new URL($('cameraLocations').href,'https://example.org').hash.slice(1)).get('browse');assert.equal(new URLSearchParams(context).get('maxConfidence'),'.95');
setState({minConfidence:'',maxConfidence:''});location.hash=saved;listeners.popstate();assert.equal(state.maxConfidence,'.95');assert.equal($('maxConfidence').value,'.95');
""", payload=confidence_catalogue(), initial_hash='#minConfidence=.9')
