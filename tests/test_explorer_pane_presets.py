"""Pane presets open a task's two panes for one visit and leave saved widths alone."""

import json

import pytest
from test_explorer_browser import helpers, node, run_browser

SPY = r"""
get('main-content').clientWidth=1400;const writes=[];global.localStorage={getItem:()=>null,setItem:(k,v)=>writes.push([k,v])};
"""


@pytest.mark.parametrize(
    "name, facets, inspector, width, layout",
    [
        ("review", "collapsed", "expanded", None, "table"),
        ("coverage", "expanded", "collapsed", 40, None),
        ("batch", "collapsed", "expanded", 600, None),
    ],
)
def test_each_preset_sets_its_pane_pair_without_saving(
    name, facets, inspector, width, layout
):
    run_browser(
        f"""
assert.equal(state.panes,'{name}');assert.equal(state.layout,{json.dumps(layout)}??undefined);
const layout=$('main-content');assert.equal(layout.getAttribute('data-facets'),'{facets}');assert.equal(layout.getAttribute('data-inspector'),'{inspector}');
assert.equal(layout.style['--inspector-w'],{json.dumps(f"{width}px" if width else None)}??undefined);
assert.match(location.hash,/panes={name}/);assert.equal(writes.length,0);
togglePanel('facets');assert.equal(layout.getAttribute('data-facets'),'{"expanded" if facets == "collapsed" else "collapsed"}');
const saved=JSON.parse(writes.at(-1)[1]);assert.equal(saved.facets.collapsed,{"false" if facets == "collapsed" else "true"});assert.equal(saved.inspector.collapsed,false);assert.equal(saved.inspector.width,null);
""",
        initial_hash=f"#source=prediction&panes={name}",
        prelude=SPY,
    )


def test_unknown_preset_is_ignored_and_old_params_still_parse():
    node(
        helpers()
        + r"""
const assert=require('node:assert/strict');
const s=readExplorerState('#source=recorded&taxon=f&status=compare&order=confidence-asc&minConfidence=0.5&layout=photos&panes=nope',[]);
assert.equal(s.panes,undefined);assert.equal(s.source,'recorded');assert.equal(s.status,'compare');assert.equal(s.order,'confidence-asc');assert.equal(s.minConfidence,'0.5');assert.equal(s.layout,'photos');
assert.equal(readExplorerState('#panes=constructor',[]).panes,undefined);assert.equal(readExplorerState('',[]).panes,undefined);
assert.equal(readExplorerState('#panes=review&layout=photos',[]).layout,'photos');
assert.equal(explorerHash(readExplorerState('#status=compare&panes=review',[])),'#source=recorded&status=compare&layout=table&panes=review');
"""
    )


def test_unknown_preset_leaves_panels_untouched():
    run_browser(
        "assert.equal($('main-content').getAttribute('data-facets'),'expanded');assert.equal(writes.length,0);",
        initial_hash="#panes=nope",
        prelude=SPY,
    )


def test_preset_is_skipped_on_stacked_phone_layout():
    run_browser(
        "assert.equal(state.panes,'coverage');assert.equal($('main-content').getAttribute('data-inspector'),'expanded');assert.equal(writes.length,0);",
        initial_hash="#panes=coverage",
        prelude=SPY + "window.matchMedia=()=>({matches:true,addEventListener(){}});",
    )
