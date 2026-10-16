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
assert.equal(state.page,1);assert.equal(cards[0].getAttribute('data-frame'),'photo-0');
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
