"""Alternate catalogue views share one population, selection and navigation state."""

import copy
from html.parser import HTMLParser
from urllib.parse import urlencode

import pytest
from test_explorer_browser import catalogue, run_browser, template
from test_explorer_confidence import confidence_catalogue


class EvidenceStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = {}
        self.headers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.targets[attrs['id']] = (tag, attrs)
        if tag == 'th':
            self.headers.append(attrs)


def test_evidence_view_has_explicit_controls_semantic_headers_and_own_scroll_region():
    page = EvidenceStructure()
    page.feed(template())
    assert page.targets['showPhotos'][1]['aria-pressed'] == 'true'
    assert page.targets['showEvidence'][1]['aria-pressed'] == 'false'
    assert page.targets['activeFilters'][1]['aria-label'] == 'Active filters'
    assert page.targets['evidenceScroll'][1]['role'] == 'region'
    assert page.targets['evidenceScroll'][1]['tabindex'] == '0'
    assert page.targets['evidenceRows'][0] == 'tbody'
    assert len(page.headers) == 6
    assert all(header.get('scope') == 'col' for header in page.headers)
    assert page.targets['clearEmptyFilters'][0] == 'button'
    assert '.evidence-scroll{max-width:100%;overflow:auto;' in template()


def test_view_switch_preserves_exact_order_pagination_pinned_identity_and_evidence():
    data = confidence_catalogue()
    sample = data['photos'][0]
    data['photos'] = []
    for index in range(60):
        photo = copy.deepcopy(sample)
        photo.update(key=f'p{index}', mission='flight-a' if index < 59 else 'other')
        photo['prediction']['score'] = index / 60
        data['photos'].append(photo)
    run_browser(r"""
setState({source:'recorded',taxon:'f',search:'flight-a',status:'compare',order:'confidence-desc',page:1});
const evidence=JSON.stringify(photos),savedState={...state},savedCards=$('gallery').children.map(card=>card.getAttribute('data-frame')),position=$('photoPosition').textContent,count=$('resultCount').textContent;
assert.equal(savedCards.length,25);assert.equal(savedCards[0],'p0');
$('showEvidence').focus();$('showEvidence').onclick();
assert.equal(state.layout,'table');assert.equal(state.page,1);assert.equal(state.frame,'p0');
for(const name of ['source','taxon','search','status','order'])assert.equal(state[name],savedState[name]);
assert.equal($('gallery').hidden,true);assert.equal($('evidenceScroll').hidden,false);
assert.equal($('showEvidence').getAttribute('aria-pressed'),'true');assert.equal(document.activeElement,$('showEvidence'));
assert.deepEqual($('evidenceRows').children.map(row=>row.getAttribute('data-frame')),savedCards);
assert.equal($('photoPosition').textContent,position);assert.equal($('resultCount').textContent,count);
const row=$('evidenceRows').children[1],key=row.getAttribute('data-frame');row.children[5].children[0].onclick();
assert.equal(state.frame,key);assert.equal(document.activeElement,$('selectedTitle'));
assert.equal($('evidenceRows').children[0].getAttribute('data-frame'),key);
assert.equal($('enlarge').disabled,false);$('enlarge').onclick();assert.equal($('photoDialog').open,true);$('closeDialog').onclick();
$('showPhotos').onclick();assert.equal(state.layout,'photos');assert.equal(state.page,1);assert.equal(state.frame,key);
assert.equal($('gallery').hidden,false);assert.equal($('evidenceScroll').hidden,true);
assert.equal($('gallery').children[0].getAttribute('data-frame'),key);assert.equal(JSON.stringify(photos),evidence);
""", payload=data)


def test_view_and_filters_roundtrip_history_and_selected_photo_tool_context():
    run_browser(r"""
assert.equal(state.layout,'table');assert.equal($('gallery').hidden,true);
assert.equal(state.source,'recorded');assert.equal(state.search,'flight-a');
const saved=location.hash;
for(const id of ['cameraLocations','plantnetResearch','crownResearch','similarPhotosTask']){
 const params=new URLSearchParams(new URL($(id).href,'https://example.org').hash.slice(1)),context=new URLSearchParams(params.get('browse'));
 assert.equal(context.get('layout'),'table');assert.equal(context.get('source'),'recorded');assert.equal(context.get('search'),'flight-a');
}
$('showPhotos').onclick();assert.equal(location.hash.includes('layout='),false);
location.hash=saved;listeners.popstate();assert.equal(state.layout,'table');assert.equal($('showEvidence').getAttribute('aria-pressed'),'true');
$('showPhotos').onclick();location.hash=saved;listeners.hashchange();assert.equal(state.layout,'table');
const hash=explorerHash(state);assert.equal(readExplorerState(hash,photos).layout,'table');
""", initial_hash='#'+urlencode({'source':'recorded','search':'flight-a','frame':'a & ä /?.JPG','layout':'table'}))


def test_table_distinguishes_zero_missing_score_missing_guess_and_unavailable_source():
    data = confidence_catalogue()
    data['photos'][0]['label'] = ' \t '
    data['photos'][0]['mission'] = ''
    data['photos'][5]['prediction'].update(name=None, status='empty')
    run_browser(r"""
function row(key){return $('evidenceRows').children.find(row=>row.getAttribute('data-frame')===key)}
assert.equal(row('p3').children[3].textContent,'0.00 / 1');assert.equal(row('p4').children[3].textContent,'1.00 / 1');
for(const key of ['p5','p6','p7'])assert.equal(row(key).children[3].textContent,'Unavailable');
assert.equal(row('p0').children[1].textContent,'No recorded label');assert.equal(row('p0').children[4].textContent,'Not recorded');
assert.equal(row('p5').children[2].textContent,'No names returned');assert.match(row('p0').children[2].textContent,/Canopia lutea/);
assert.match(row('p0').children[3].title,/0.41209/);
catalogue.provenance.predictions.available=false;setState({source:'recorded'});
assert.equal(row('p3').children[2].textContent,'Pl@ntNet guesses unavailable');assert.equal(row('p3').children[3].textContent,'Unavailable');
assert.equal(row('p3').children[1].textContent,'Canopia alba');
""", payload=data, initial_hash='#layout=table')


def test_active_filter_removal_changes_only_that_constraint_and_retains_focus():
    run_browser(r"""
function chips(){return $('activeFilters').children.filter(button=>button.getAttribute('data-filter'))}
function chip(key){return chips().find(button=>button.getAttribute('data-filter')===key)}
assert.equal($('activeFilters').hidden,true);
setState({source:'recorded',taxon:'f',search:'flight-a',status:'compare',confidence:'scored',minConfidence:'.8',missions:'other',layout:'table'});
assert.deepEqual(chips().map(button=>button.getAttribute('data-filter')),['taxon','search','status','confidence','minConfidence']);
assert.match(chip('taxon').textContent,/Forestaceae/);assert.match(chip('search').getAttribute('aria-label'),/Remove filter.*flight-a/);
const frame=state.frame;chip('search').focus();chip('search').onclick();
assert.equal(state.search,'');assert.equal(state.source,'recorded');assert.equal(state.frame,frame);assert.equal(state.taxon,'f');assert.equal(state.status,'compare');assert.equal(state.confidence,'scored');assert.equal(state.minConfidence,'.8');assert.equal(state.missions,'other');assert.equal(state.layout,'table');
assert.equal(document.activeElement,chip('taxon'));
chip('taxon').onclick();assert.equal(state.taxon,'');assert.equal(state.status,'compare');
chip('confidence').onclick();assert.equal(state.confidence,'all');assert.equal(state.minConfidence,'.8');
chip('minConfidence').onclick();assert.equal(state.minConfidence,'');chip('status').focus();chip('status').onclick();
assert.equal($('activeFilters').hidden,true);assert.equal(document.activeElement,$('resultCount'));
""")


@pytest.mark.parametrize('clear_control', ['clearEmptyFilters', 'strip', 'allPhotos'])
def test_clear_constraints_from_empty_results_keeps_grouping_selection_scope_layout_order(clear_control):
    run_browser(r"""
setState({source:'recorded',frame:'b',taxon:'s',search:'no matches',status:'without',confidence:'missing',minConfidence:'.9',order:'confidence-desc',layout:'table',missions:'other'});
assert.equal($('empty').hidden,false);assert.equal($('evidenceRows').children.length,1);
assert.equal($('evidenceRows').children[0].getAttribute('data-frame'),'b');
const control=__CONTROL__==='strip'?$('activeFilters').children.at(-1):$(__CONTROL__);control.focus();control.onclick();
assert.equal(state.source,'recorded');assert.equal(state.frame,'b');assert.equal(state.layout,'table');assert.equal(state.order,'confidence-desc');assert.equal(state.missions,'other');
assert.equal(state.taxon,'');assert.equal(state.search,'');assert.equal(state.status,'all');assert.equal(state.confidence,'all');assert.equal(state.minConfidence,'');assert.equal(state.page,0);
assert.equal($('empty').hidden,true);assert.equal($('activeFilters').hidden,true);assert.equal($('evidenceRows').children.length,6);assert.equal(document.activeElement,$('resultCount'));
""".replace('__CONTROL__', repr(clear_control)))


def test_invalid_minimum_has_removable_chip_without_substituting_matching_results():
    run_browser(r"""
assert.equal($('empty').hidden,false);assert.match($('stateNotice').textContent,/confidence controls unavailable/);
const chip=$('activeFilters').children.find(button=>button.getAttribute('data-filter')==='minConfidence');assert.match(chip.textContent,/NaN/);
assert.equal($('evidenceRows').children.length,1);assert.equal(state.frame,'b');
chip.onclick();assert.equal(state.minConfidence,'');assert.equal($('stateNotice').textContent,'');assert.equal(state.frame,'b');assert.equal(state.layout,'table');assert.equal($('empty').hidden,true);
""", initial_hash='#source=recorded&frame=b&minConfidence=NaN&layout=table')


@pytest.mark.parametrize('empty_catalogue', [False, True])
def test_table_jump_targets_inspect_action_or_empty_message_without_changing_state(empty_catalogue):
    data = catalogue()
    if empty_catalogue:
        data['photos'] = []
    run_browser(r"""
const saved=JSON.stringify(state),hash=location.hash;
for(const id of ['skipGallery','backToPhotos']){
 let prevented=false;$(id).onclick({preventDefault(){prevented=true}});assert.equal(prevented,true);
 const target=$('evidenceRows').children.length?$('evidenceRows').children[0].children[5].children[0]:$('empty');
 assert.equal(document.activeElement,target);assert.equal(JSON.stringify(state),saved);assert.equal(location.hash,hash);
}
""", payload=data, initial_hash='#layout=table')


def test_table_image_failures_do_not_change_selected_photo_or_other_evidence():
    run_browser(r"""
const row=$('evidenceRows').children[0],image=row.children[0].children[0].children[1],status=row.children[0].children[0].children[0],original=JSON.stringify(photos);
assert.equal(status.textContent,'Loading photo…');image.onload();assert.equal(status.hidden,true);
image.onerror();assert.equal(image.hidden,true);assert.equal(status.textContent,'Photo unavailable');assert.equal(status.hidden,false);
assert.equal(state.frame,'a & ä /?.JPG');assert.equal(row.children[1].textContent,'Canopia alba');assert.equal(row.children[2].textContent,'Canopia lutea');assert.equal(JSON.stringify(photos),original);
""", initial_hash='#layout=table')


def test_confidence_disclosure_starts_closed_and_exposes_active_or_invalid_controls():
    page = EvidenceStructure()
    page.feed(template())
    assert 'open' not in page.targets['confidenceOptions'][1]
    run_browser(r"""
assert.equal(Boolean($('confidenceOptions').open),false);
$('confidenceOptions').open=true;setState({search:'flight-a'});assert.equal($('confidenceOptions').open,true);
$('confidenceOptions').open=false;setState({order:'confidence-desc'});assert.equal($('confidenceOptions').open,true);
$('confidenceOptions').open=false;setState({order:'catalogue',minConfidence:'NaN'});assert.equal($('confidenceOptions').open,true);
assert.match($('stateNotice').textContent,/confidence controls unavailable/);
""")
    run_browser("assert.equal($('confidenceOptions').open,true);", initial_hash='#confidence=missing')


def test_inspector_taxon_pivots_use_recorded_ids_and_preserve_selected_photo_constraints():
    run_browser(r"""
setState({source:'recorded',search:'flight-a',status:'compare',confidence:'scored',minConfidence:'.8',order:'confidence-desc',layout:'table',missions:'other'});
const frame=state.frame,evidence=JSON.stringify(photos);
assert.equal($('browseRecordedTaxon').disabled,false);assert.equal($('browsePredictedTaxon').disabled,false);
$('browsePredictedTaxon').focus();$('browsePredictedTaxon').onclick();
assert.equal(state.source,'prediction');assert.equal(state.taxon,'t');assert.equal(state.frame,frame);
for(const [key,value] of Object.entries({search:'flight-a',status:'compare',confidence:'scored',minConfidence:'.8',order:'confidence-desc',layout:'table',missions:'other'}))assert.equal(state[key],value);
assert.equal(document.activeElement,$('browsePredictedTaxon'));assert.equal($('recordedLabel').children[0].textContent,'Canopia alba');
$('browseRecordedTaxon').onclick();assert.equal(state.source,'recorded');assert.equal(state.taxon,'s');assert.equal(state.frame,frame);assert.equal(state.page,0);
assert.equal(JSON.stringify(photos),evidence);
setState({frame:'c'});assert.equal($('browseRecordedTaxon').disabled,false);$('browseRecordedTaxon').onclick();assert.equal(state.taxon,'f');
""")


@pytest.mark.parametrize('failure', ['unresolved', 'unknown_id', 'no_name', 'unavailable_predictions', 'unavailable_photo'])
def test_inspector_pivots_never_infer_taxa_from_unresolved_names(failure):
    data = catalogue()
    first = data['photos'][0]
    if failure == 'unresolved':
        first['recorded_status'] = 'unresolved'
        first['prediction']['status'] = 'unresolved'
    elif failure == 'unknown_id':
        first['recorded_taxon'] = 'missing-taxon'
        first['prediction']['taxon'] = 'missing-taxon'
    elif failure == 'no_name':
        first['label'] = ' \t '
        first['prediction']['name'] = ''
    elif failure == 'unavailable_predictions':
        data['provenance']['predictions']['available'] = False
    run_browser(r"""
const failure=__FAILURE__;
if(failure==='unavailable_photo')setState({frame:'does-not-exist'});
const saved=JSON.stringify(state);
assert.equal($('browsePredictedTaxon').disabled,true);$('browsePredictedTaxon').onclick();assert.equal(JSON.stringify(state),saved);
if(failure!=='unavailable_predictions'){
 assert.equal($('browseRecordedTaxon').disabled,true);$('browseRecordedTaxon').onclick();assert.equal(JSON.stringify(state),saved);
}
if(failure==='unavailable_photo')assert.equal($('taxonPivots').hidden,true);
else {assert.equal($('predictedTaxonHelp').hidden,false);assert.ok($('predictedTaxonHelp').textContent.length)}
""".replace('__FAILURE__', repr(failure)), payload=data)
