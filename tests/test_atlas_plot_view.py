"""Visual relationships is a linkable view whose family colours never depend on rank, filter or selection."""

import re
import runpy
from pathlib import Path

from test_atlas_mission_view import run_atlas
from test_atlas_plot_explore import plot_photos

HTML = runpy.run_path(Path(__file__).resolve().parents[1] / "dashboard/embedding_atlas_assets.py")["HTML"]


def test_view_plot_round_trips_through_reload_links_and_history():
    run_atlas(plot_photos(), r"""
assert.equal(atlasView,'plot');assert.equal($('plotView').hidden,false);assert.equal($('locationsView').hidden,false);assert.equal(document.activeElement,$('plotView'));assert.equal(location.hash,'#frame=query&view=plot');
assert.equal($('showPlotView').getAttribute('aria-pressed'),'true');assert.equal(frameHash('query','plot'),'#frame=query&view=plot');
for(const link of navLinks.filter(link=>link.getAttribute('data-site-task')))assert.equal(link.getAttribute('aria-current'),null);
const back=location.hash;navLinks[4].onclick({button:0,preventDefault(){}});assert.equal(atlasView,'locations');assert.equal($('plotView').hidden,true);assert.equal(historyEntries.at(-1),'#frame=query');
location.hash=back;listeners.popstate();assert.equal(atlasView,'plot');assert.equal($('plotView').hidden,false);
select(3);assert.equal(location.hash,'#frame=p3&view=plot');
select(0);$('inspectPhoto').focus();assert.equal(openPhotoComparison(0,$('inspectPhoto')),true);$('chooseComparison').onclick();assert.equal(atlasView,'plot');assert.equal(selected,1);assert.equal(document.activeElement,$('plotView'));
""", initial_hash="#frame=query&view=plot", page="embedding-atlas.html")


def test_plantnet_return_link_keeps_plot_view():
    run_atlas(plot_photos(), r"""
const link=$('ordinaryMatchingLink');assert.equal(link.getAttribute('data-atlas-view'),'plot');assert.equal(link.textContent,'Back to Pl@ntNet visual relationships');assert.equal(link.getAttribute('href'),'embedding-atlas.html#frame=query&view=plot');
""", initial_hash="#frame=query&view=plot", page="crownfirst-atlas.html")


def test_old_view_links_still_open_their_views():
    for view, panel in [("photos", "photosView"), ("locations", "locationsView"), ("models", "modelComparisonView"), ("unknown", "locationsView")]:
        run_atlas(plot_photos(), r"""
assert.equal(atlasView,__VIEW__);assert.equal($(__PANEL__).hidden,false);assert.equal($('plotView').hidden,true);assert.equal($('showPlotView').getAttribute('aria-pressed'),'false');
""".replace("__VIEW__", repr("locations" if view == "unknown" else view)).replace("__PANEL__", repr(panel)), initial_hash="#frame=query&view=" + view)


def test_label_colours_are_fixed_from_full_data_across_filter_and_selection():
    run_atlas(plot_photos(), r"""
const colours=()=>P.map(p=>PLOT_COLOURS[plotClass(p)]),before=colours(),swatch=name=>$('plotLegend').children.find(b=>b.children[1].textContent.startsWith(name+' ('))?.children[0].style.background;
assert.deepEqual(plotTop,['A','B','C','D','E','F','G','H']);assert.equal(swatch('B'),'#56B4E9');
select(12);assert.deepEqual(colours(),before);assert.equal(swatch('B'),'#56B4E9');
const pc=context('plot');pc.fills=[];draw();assert.equal(pc.fills.at(-1),'#8c8c8c');
select(4);$('search').value='p4';$('search').oninput();assert.equal(visible.includes(0),false);assert.deepEqual(plotTop,['A','B','C','D','E','F','G','H']);assert.deepEqual(colours(),before);
assert.equal(swatch('B'),'#56B4E9');assert.equal(swatch('A'),undefined);pc.fills=[];draw();assert.equal(pc.fills.at(-1),'#56B4E9');
$('plotLegend').children[0].onclick();assert.equal(plotFocus,1);
""")


def test_no_labels_and_fewer_than_eight_labels():
    run_atlas(plot_photos()[:3], r"""
assert.deepEqual(plotTop,['A']);assert.deepEqual($('plotLegend').children.map(b=>b.children[1].textContent),['A (3)']);
""")
    points = plot_photos()
    for p in points:
        p["label"] = p["family"] = None
    run_atlas(points, r"""
assert.deepEqual(plotTop,[]);assert.deepEqual($('plotLegend').children.map(b=>b.children[1].textContent),['No recorded family (15)']);
""")


def test_plot_colours_by_recorded_family_not_by_label():
    points = plot_photos()
    for p in points:
        p["family"] = None if p["label"] is None else "Fam1" if p["label"] in ("A", "B") else "Fam2"
    run_atlas(points, r"""
assert.deepEqual(plotTop,['Fam2','Fam1']);assert.deepEqual($('plotLegend').children.map(b=>b.children[1].textContent),['Fam2 (8)','Fam1 (5)','No recorded family (2)']);
assert.equal(plotClass(P[0]),1);assert.equal(plotClass(P[5]),0);assert.equal(plotClass(P[13]),9);
const pc=context('plot');pc.fills=[];draw();assert.equal(pc.fills.at(-1),'#56B4E9');assert.equal(pc.fills.filter(f=>f==='#E69F00').length,8);
$('plotLegend').children[0].onclick();assert.equal(plotFocus,0);
""")


def test_plot_hover_rings_the_same_photo_on_the_map():
    run_atlas(plot_photos(), r"""
const mc=context('map'),[tx,ty,index]=plotHits.find(h=>h[2]===7);
assert.equal(plotHover,null);mc.arcs=[];draw();assert.equal(mc.arcs.includes(13),false);
plot.onpointermove({offsetX:tx,offsetY:ty});assert.equal(plotHover,index);assert.equal(mc.arcs.at(-1),13);
mc.arcs=[];draw();assert.equal(mc.arcs.filter(r=>r===13).length,1);
plot.onpointerleave();assert.equal(plotHover,null);mc.arcs=[];draw();assert.equal(mc.arcs.includes(13),false);
""")


def test_wide_screens_put_map_and_plot_in_two_columns_and_narrow_ones_stack():
    css = re.search(r"@media\(min-width:1100px\)\{#locationsView:has\(#plotView:not\(\[hidden\]\)\)\{(.*?)\}", HTML).group(1)
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css
    assert "#locationsView:has(#plotView:not([hidden]))>#plotView{grid-column:2" in HTML
    assert "#closePlot{display:none}" not in HTML
    assert HTML.index('id="mapView"') < HTML.index('id="plotView"') < HTML.index('id="mapHelp"')
    assert HTML.index('id="plotView"') < HTML.index('id="modelComparisonView"')
