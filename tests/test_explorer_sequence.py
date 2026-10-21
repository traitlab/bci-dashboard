"""Consecutive inspection follows the filtered population, and the gallery page follows the selection."""

import pytest
from test_explorer_browser import ROOT, SELECTED, catalogue, run_browser, template
from test_explorer_keyboard import PageTargets


def test_consecutive_matches_cross_pages_in_both_directions_and_keep_exact_evidence():
    data = catalogue()
    sample = data['photos'][0]
    data['photos'] = [
        {**sample, 'key': f'photo-{index}', 'image': f'https://example.org/{index}.jpg',
         'label': f'Recorded {index}', 'annotation_url': f'https://example.org/annotation/{index}',
         'prediction': {**sample['prediction'], 'name': f'Guess {index}', 'score': index / 100}}
        for index in range(60)
    ]
    run_browser(r"""
const before=JSON.stringify(photos),scope={source:state.source,taxon:state.taxon,search:state.search,status:state.status};
function exact(index){
assert.equal(state.frame,'photo-'+index);assert.equal($('selectedKey').textContent,state.frame);
assert.equal($('selectedImage').src,'thumbs/480/'+encodeURIComponent(photos[index].key)+'.webp');
assert.equal($('recordedLabel').children[0].textContent,'Recorded '+index);
assert.equal($('predictionLabel').children[0].textContent,'Guess '+index);
assert.equal($('annotation').href,'https://example.org/annotation/'+index);
assert.equal($('photoPosition').textContent,'Photo '+(index+1)+' of 60 matching photos');
assert.equal(new URLSearchParams(location.hash.slice(1)).get('frame'),state.frame);
for(const field of Object.keys(scope))assert.equal(state[field],scope[field]);
assert.equal(state.page,Math.floor(index/24));assert.equal($('gallery').children.find(card=>card.getAttribute('aria-pressed')==='true').getAttribute('data-frame'),state.frame);
}
$('nextPhoto').focus();
for(let index=1;index<60;index++){$('nextPhoto').onclick();exact(index);assert.equal(document.activeElement,index<59?$('nextPhoto'):$('photoPosition'))}
assert.equal($('nextPhoto').disabled,true);const end=location.hash,entries=historyEntries.length;
$('nextPhoto').onclick();assert.equal(location.hash,end);assert.equal(historyEntries.length,entries);
$('previousPhoto').focus();
for(let index=58;index>=0;index--){$('previousPhoto').onclick();exact(index);assert.equal(document.activeElement,index>0?$('previousPhoto'):$('photoPosition'))}
assert.equal($('previousPhoto').disabled,true);assert.equal(JSON.stringify(photos),before);
const saved=historyEntries[24];location.hash=saved;listeners.popstate();exact(25);
assert.equal($('previousPhoto').disabled,false);assert.equal($('nextPhoto').disabled,false);
""", payload=data, initial_hash='#source=recorded&taxon=f&search=flight-a&status=compare&frame=photo-0&page=1')


@pytest.mark.parametrize('patch,reason', [
    ("{search:'no matches'}", 'No photos match'),
    ("{taxon:'s'}", 'outside these filters'),
    ("{frame:'missing'}", 'Requested photo unavailable'),
    ("{frame:''}", 'Choose a photo'),
    ("{source:'invalid'}", 'filters unavailable'),
    ("{taxon:'invalid'}", 'filters unavailable'),
    ("{status:'invalid'}", 'filters unavailable'),
])
def test_unavailable_sequence_does_not_substitute_selection(patch, reason):
    run_browser(r"""
setState(__PATCH__);const before=JSON.stringify(state),entries=historyEntries.length;
assert.equal($('previousPhoto').disabled,true);assert.equal($('nextPhoto').disabled,true);
assert.ok($('photoPosition').textContent.includes(__REASON__));
$('previousPhoto').onclick();$('nextPhoto').onclick();
assert.equal(JSON.stringify(state),before);assert.equal(historyEntries.length,entries);
""".replace('__PATCH__', patch).replace('__REASON__', repr(reason)), initial_hash=SELECTED)


def test_position_recomputes_on_filters_and_restores_without_changing_selection():
    run_browser(r"""
const first=state.frame;
assert.equal($('photoPosition').textContent,'Photo 1 of 6 matching photos');
setState({source:'recorded',taxon:'f'});assert.equal(state.frame,first);
assert.equal($('photoPosition').textContent,'Photo 1 of 3 matching photos');
$('nextPhoto').onclick();assert.equal(state.frame,'b');const saved=location.hash;
assert.equal($('photoPosition').textContent,'Photo 2 of 3 matching photos');
setState({taxon:'s'});assert.equal(state.frame,'b');assert.match($('photoPosition').textContent,/outside these filters/);
location.hash=saved;listeners.hashchange();assert.equal(state.frame,'b');
assert.equal($('photoPosition').textContent,'Photo 2 of 3 matching photos');
setState({frame:first,status:'compare'});
assert.equal($('photoPosition').textContent,'Photo 1 of 1 matching photos');
assert.equal($('previousPhoto').disabled,true);assert.equal($('nextPhoto').disabled,true);
const entries=historyEntries.length;$('nextPhoto').onclick();assert.equal(state.frame,first);assert.equal(historyEntries.length,entries);
""")


def test_empty_catalogue_and_mobile_movement_keep_the_selected_frame_explicit():
    data = catalogue()
    data['photos'] = []
    run_browser(r"""
assert.equal(state.frame,'');assert.equal($('previousPhoto').disabled,true);assert.equal($('nextPhoto').disabled,true);
assert.match($('photoPosition').textContent,/No photos match/);
""", payload=data)
    run_browser(r"""
window.matchMedia=()=>({matches:true});$('inspector').scrollTop=500;
$('nextPhoto').focus();$('nextPhoto').onclick();assert.equal(state.frame,'b');
assert.equal($('inspector').scrollTop,0);assert.equal($('inspector').revealed,true);
assert.equal(document.activeElement,$('nextPhoto'));
""")


@pytest.mark.parametrize("published", [False, True])
def test_sequence_controls_have_real_keyboard_and_status_targets(published):
    page = PageTargets()
    page.feed((ROOT / "docs/explorer.html").read_text() if published else template())
    for identity in ['previousPhoto', 'nextPhoto']:
        tag, attributes = page.targets[identity]
        assert tag == 'button'
        assert attributes['aria-describedby'] == 'photoPosition'
        assert page.order.index('selectedKey') < page.order.index(identity)
        assert page.order.index(identity) < page.order.index('selectedImageFrame')
    assert page.targets['photoPosition'][1]['tabindex'] == '-1'
    assert page.targets['photoPosition'][1]['role'] == 'status'


def test_missing_selection_image_or_annotation_does_not_borrow_another_photos_evidence():
    data = catalogue()
    data['photos'][1]['image'] = None
    run_browser(r"""
assert.equal($('annotation').hidden,true);
$('nextPhoto').onclick();assert.equal(state.frame,'b');assert.equal($('annotation').href,'https://example.org/annotation/b');
assert.equal($('selectedImage').src,undefined);assert.equal($('enlarge').disabled,true);
assert.equal($('selectedImageStatus').textContent,'Photo URL unavailable.');
$('nextPhoto').onclick();assert.equal(state.frame,'c');assert.equal($('annotation').hidden,true);assert.equal($('annotation').href,undefined);
assert.equal($('selectedImage').src,'thumbs/480/c.webp');
setState({frame:''});assert.equal($('selectedUnavailable').textContent,'Choose a photo from the gallery.');
assert.equal($('selectedImageFrame').hidden,true);assert.equal($('nextPhoto').disabled,true);
""", payload=data)
