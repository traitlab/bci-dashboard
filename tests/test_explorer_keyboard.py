"""Catalogue section jumps bypass long lists without changing the saved task."""

from html.parser import HTMLParser

import pytest
from test_explorer_browser import ROOT, catalogue, run_browser, template


class PageTargets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = {}
        self.order = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        assert int(attributes.get("tabindex", "0")) <= 0
        if identity := attributes.get("id"):
            self.targets[identity] = (tag, attributes)
            self.order.append(identity)


@pytest.mark.parametrize("published", [False, True])
def test_section_jumps_have_real_targets_before_the_long_taxonomy(published):
    page = PageTargets()
    page.feed((ROOT / "docs/explorer.html").read_text() if published else template())
    for identity, target in [
        ("skipGallery", "gallery"),
        ("skipSelected", "selectedTitle"),
        ("backToPhotos", "gallery"),
    ]:
        tag, attributes = page.targets[identity]
        assert tag == "a"
        assert attributes["href"] == "#" + target
        assert target in page.targets
    for identity in ["skipGallery", "skipSelected"]:
        assert page.targets[identity][1]["class"] == "site-skip"
        assert page.order.index("main-content") < page.order.index(identity)
        assert page.order.index(identity) < page.order.index("facets")
    assert page.order.index("annotation") < page.order.index("backToPhotos")
    assert page.targets["empty"][1]["tabindex"] == "-1"


def test_gallery_and_inspector_jumps_preserve_filters_page_identity_and_history():
    data = catalogue()
    data["photos"] = [
        {**data["photos"][0], "key": "photo-" + str(index)} for index in range(60)
    ]
    run_browser(
        r"""
const originalHash=location.hash,originalState=JSON.stringify(state),originalHistory=historyEntries.slice(),originalPhotos=JSON.stringify(photos),cards=$('gallery').children;
assert.equal(state.page,1);assert.equal(cards[0].getAttribute('data-frame'),'photo-24');
function jump(id,target){let prevented=false;$(id).onclick({preventDefault(){prevented=true}});assert.equal(prevented,true);assert.equal(document.activeElement,target);assert.equal(location.hash,originalHash);assert.equal(JSON.stringify(state),originalState);assert.deepEqual(historyEntries,originalHistory);assert.equal($('gallery').children,cards);assert.equal(JSON.stringify(photos),originalPhotos)}
jump('skipGallery',cards[0]);jump('skipSelected',$('selectedTitle'));
$('annotation').focus();jump('backToPhotos',cards[0]);
$('inspector').scrollTop=500;$('detailViewport').scrollTop=200;
$('showSelected').onclick();assert.equal(document.activeElement,$('selectedTitle'));assert.equal($('inspector').scrollTop,0);assert.equal($('detailViewport').scrollTop,200);assert.equal(location.hash,originalHash);
$('inspector').scrollTop=400;jump('skipSelected',$('selectedTitle'));assert.equal($('inspector').scrollTop,0);
$('inspector').scrollTop=400;$('detailViewport').scrollTop=200;
cards[1].onclick();assert.equal(state.frame,cards[1].getAttribute('data-frame'));assert.equal(document.activeElement,$('selectedTitle'));assert.equal($('inspector').scrollTop,0);assert.equal($('detailViewport').scrollTop,200);
""",
        payload=data,
        initial_hash="#source=recorded&taxon=f&search=flight-a&status=compare&frame=photo-0&page=1",
    )


@pytest.mark.parametrize("empty_catalogue", [False, True])
def test_gallery_jump_focuses_empty_results_when_no_card_is_available(empty_catalogue):
    data = catalogue()
    if empty_catalogue:
        data["photos"] = []
    run_browser(
        r"""
assert.equal($('gallery').children.length,0);assert.equal($('empty').hidden,false);
const hash=location.hash,saved=JSON.stringify(state),entries=historyEntries.slice();
for(const id of ['skipGallery','backToPhotos']){let prevented=false;$(id).onclick({preventDefault(){prevented=true}});assert.equal(prevented,true);assert.equal(document.activeElement,$('empty'));assert.equal(location.hash,hash);assert.equal(JSON.stringify(state),saved);assert.deepEqual(historyEntries,entries)}
""",
        payload=data,
        initial_hash="#frame=unavailable&search=no-results",
    )


def test_photo_buttons_advertise_the_review_shortcuts():
    html = template()
    for identity, key, name in [("previousPhoto", "k", "Previous"), ("nextPhoto", "j", "Next"), ("dialogPrevious", "k", "Previous"), ("dialogNext", "j", "Next")]:
        assert f'<button id="{identity}"' in html
        tag = html.split(f'<button id="{identity}"')[1].split(">")[0]
        assert f'aria-keyshortcuts="{key}"' in tag and f'title="{name} photo ({key})"' in tag


def test_review_keys_move_and_open_but_never_steal_text_entry_or_actual_pixel_scrolling():
    run_browser(
        r"""
const press=(key,extra={})=>{let prevented=false;listeners['document:keydown']({key,...extra,preventDefault(){prevented=true}});return prevented};
assert.equal(state.frame,'b');
press('j');assert.equal(state.frame,'c');press('k');press('k');assert.equal(state.frame,'a & ä /?.JPG');
press('ArrowRight');press('ArrowLeft');assert.equal(state.frame,'a & ä /?.JPG');
for(const extra of [{ctrlKey:true},{metaKey:true},{altKey:true},{shiftKey:true}]){press('j',extra);assert.equal(state.frame,'a & ä /?.JPG')}
for(const tag of ['input','select','textarea']){const field=make(tag);field.focus();press('j');assert.equal(state.frame,'a & ä /?.JPG')}
$('detailViewport').focus();press('j');press('e');assert.equal($('photoDialog').open,undefined);assert.equal(state.frame,'a & ä /?.JPG');
document.activeElement=null;press('e');assert.equal($('photoDialog').open,true);
""",
        initial_hash="#frame=b",
    )


def test_detail_dialog_compares_labels_and_moves_through_matching_photos():
    run_browser(
        r"""
const press=key=>listeners['document:keydown']({key,preventDefault(){}});
press('e');assert.equal($('dialogKey').textContent,'b');assert.equal($('dialogCompare').textContent,'Recorded: Canopia · Pl@ntNet: Canopia alba (0.81)');
assert.equal($('dialogPrevious').disabled,false);
$('dialogNext').focus();$('dialogNext').onclick();assert.equal($('dialogKey').textContent,'c');assert.equal($('dialogCompare').textContent,'Recorded: Forestaceae');
press('j');assert.equal($('dialogKey').textContent,'d');assert.equal($('dialogCompare').textContent,'Pl@ntNet: Canopia alba (0.81)');
press('e');assert.equal($('dialogKey').textContent,'d');
press('j');assert.equal($('dialogCompare').textContent,'Recorded: Old unresolved name');
press('k');assert.equal($('dialogKey').textContent,'d');
$('dialogNext').focus();press('j');press('j');assert.equal($('dialogKey').textContent,'z');
assert.equal($('dialogNext').disabled,true);assert.equal(document.activeElement,$('closeDialog'));
$('dialogPrevious').onclick();assert.equal($('dialogKey').textContent,'e');
""",
        initial_hash="#frame=b",
    )


def test_dead_review_options_are_disabled_unless_current_and_back_to_photos_finds_the_card():
    run_browser(
        r"""
const disabled=()=>Object.fromEntries($('labelStatus').options.map(o=>[o.value,Boolean(o.disabled)]));
assert.deepEqual(disabled(),{all:false,with:false,without:false,compare:false});
setState({taxon:'s',search:'flight-a'});assert.deepEqual(disabled(),{all:false,with:false,without:false,compare:true});
setState({status:'compare'});assert.deepEqual(disabled(),{all:false,with:false,without:false,compare:false});
setState({status:'all',taxon:'',search:''});
let prevented=false;$('backToPhotos').onclick({preventDefault(){prevented=true}});
assert.equal(prevented,true);assert.equal(document.activeElement.getAttribute('data-frame'),'c');assert.equal(document.activeElement.revealed,true);
setState({layout:'table'});assert.equal($('evidenceRows').children[2].children[4].title,'flight-a');
""",
        initial_hash="#frame=c",
    )
