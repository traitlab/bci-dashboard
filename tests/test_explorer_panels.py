"""Desktop panels resize and collapse per viewer without touching the shareable URL."""

import json

import pytest
from test_explorer_browser import helpers, node, run_browser

THROWING_STORAGE = "global.localStorage={getItem(){throw new Error('denied')},setItem(){throw new Error('denied')}};"


def memory_storage(saved=None):
    return ("const stored=new Map(" + json.dumps([["explorer-panels", saved]] if saved else []) + ");"
            "global.localStorage={getItem:key=>stored.get(key)??null,setItem:(key,value)=>stored.set(key,String(value))};")


def test_panel_width_clamps_to_limits_and_keeps_the_main_column_minimum():
    node(helpers() + r"""
const assert=require('node:assert/strict');
assert.equal(clampPanelWidth(260,200,480,1600,390),260);
assert.equal(clampPanelWidth(100,200,480,1600,390),200);
assert.equal(clampPanelWidth(900,200,480,1600,390),480);
assert.equal(clampPanelWidth(Infinity,200,480,1600,390),480);
assert.equal(clampPanelWidth(479.6,200,480,1600,390),480);
// Main keeps 360px: 1100 - 390 - 360 leaves 350 for the panel.
assert.equal(clampPanelWidth(480,200,480,1100,390),350);
assert.equal(clampPanelWidth(350,200,480,1100,390),350);
assert.equal(clampPanelWidth(480,200,480,1100,390,500),210);
// Too little space: the panel minimum wins over the main minimum.
assert.equal(clampPanelWidth(480,200,480,700,390),200);
for(const bad of [null,undefined,NaN,'300'])assert.equal(clampPanelWidth(bad,200,480,1600,390),200);
assert.equal(clampPanelWidth(300,200,480,NaN,390),300);
assert.equal(clampPanelWidth(900,200,480,undefined,390),480);
""")


@pytest.mark.parametrize("text,expected", [
    (None, {"facets": {"width": None, "collapsed": False}, "inspector": {"width": None, "collapsed": False}}),
    ("", {"facets": {"width": None, "collapsed": False}, "inspector": {"width": None, "collapsed": False}}),
    ("not json", {"facets": {"width": None, "collapsed": False}, "inspector": {"width": None, "collapsed": False}}),
    ("[1,2]", {"facets": {"width": None, "collapsed": False}, "inspector": {"width": None, "collapsed": False}}),
    ('{"facets":{"width":"300","collapsed":"yes"},"inspector":{"width":420,"collapsed":true}}',
     {"facets": {"width": None, "collapsed": False}, "inspector": {"width": 420, "collapsed": True}}),
])
def test_saved_panel_preferences_are_validated(text, expected):
    node(helpers() + "\nconst assert=require('node:assert/strict');assert.deepEqual(panelPrefs("
         + json.dumps(text) + ")," + json.dumps(expected) + ");")


@pytest.mark.parametrize("prelude", ["", THROWING_STORAGE, memory_storage()])
def test_collapse_and_keyboard_resize_work_when_storage_is_missing_throws_or_works(prelude):
    run_browser(r"""
const hash=location.hash,entries=historyEntries.slice(),layout=$('main-content'),toggle=$('toggleFacets'),splitter=$('facetsSplitter');
function key(target,name){let prevented=false;target.onkeydown({key:name,preventDefault(){prevented=true}});return prevented}
assert.equal(toggle.getAttribute('aria-expanded'),'true');assert.equal(toggle.getAttribute('aria-label'),'Hide filters');
toggle.onclick();assert.equal(toggle.getAttribute('aria-expanded'),'false');assert.equal(toggle.getAttribute('aria-label'),'Show filters');assert.equal(layout.getAttribute('data-facets'),'collapsed');assert.equal(layout.style['--facets-w'],'40px');
toggle.onclick();assert.equal(toggle.getAttribute('aria-expanded'),'true');assert.equal(layout.getAttribute('data-facets'),'expanded');assert.equal(layout.style['--facets-w'],undefined);
layout.clientWidth=1600;applyPanels();
assert.equal(key(splitter,'ArrowRight'),true);assert.equal(splitter.getAttribute('aria-valuenow'),'276');assert.equal(layout.style['--facets-w'],'276px');
key(splitter,'ArrowLeft');key(splitter,'ArrowLeft');assert.equal(splitter.getAttribute('aria-valuenow'),'244');
key(splitter,'Home');assert.equal(splitter.getAttribute('aria-valuenow'),'200');key(splitter,'ArrowLeft');assert.equal(splitter.getAttribute('aria-valuenow'),'200');
key(splitter,'End');assert.equal(splitter.getAttribute('aria-valuenow'),'480');assert.equal(splitter.getAttribute('aria-valuemax'),'480');
// The inspector splitter moves the other way: Right narrows the inspector.
key($('inspectorSplitter'),'ArrowRight');assert.equal($('inspectorSplitter').getAttribute('aria-valuenow'),'374');assert.equal(layout.style['--inspector-w'],'374px');
layout.clientWidth=1100;applyPanels();assert.equal(layout.style['--facets-w'],'366px');key(splitter,'End');assert.equal(splitter.getAttribute('aria-valuenow'),'366');
assert.equal(key(splitter,'Enter'),true);assert.equal(toggle.getAttribute('aria-expanded'),'false');assert.equal(splitter.getAttribute('aria-valuetext'),'Filters hidden');
key(splitter,'ArrowRight');assert.equal(toggle.getAttribute('aria-expanded'),'true');assert.equal(splitter.getAttribute('aria-valuenow'),'216');
assert.equal(key(splitter,'a'),false);
splitter.ondblclick();assert.equal(layout.style['--facets-w'],undefined);
$('toggleInspector').onclick();assert.equal($('toggleInspector').getAttribute('aria-label'),'Show selected photo');
$('gallery').children[1].onclick();assert.equal($('toggleInspector').getAttribute('aria-expanded'),'true');assert.equal(document.activeElement,$('selectedTitle'));
assert.equal(location.hash.includes('facets'),false);assert.equal(historyEntries.slice(0,entries.length).join(),entries.join());
""", prelude=prelude)


def test_saved_panels_restore_on_load_and_persist_changes():
    run_browser(r"""
const layout=$('main-content');
assert.equal(layout.getAttribute('data-facets'),'collapsed');assert.equal($('toggleFacets').getAttribute('aria-expanded'),'false');assert.equal(layout.style['--facets-w'],'40px');
assert.equal(layout.style['--inspector-w'],'420px');
$('toggleFacets').onclick();assert.equal(layout.style['--facets-w'],'300px');
assert.deepEqual(JSON.parse(stored.get('explorer-panels')),{facets:{width:300,collapsed:false},inspector:{width:420,collapsed:false}});
""", prelude=memory_storage('{"facets":{"width":300,"collapsed":true},"inspector":{"width":420}}') + "get('main-content').clientWidth=1600;")
