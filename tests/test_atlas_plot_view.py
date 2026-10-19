"""Visual relationships is a linkable view whose label colours never depend on rank, filter or selection."""

from test_atlas_mission_view import run_atlas
from test_atlas_plot_explore import plot_photos


def test_view_plot_round_trips_through_reload_links_and_history():
    run_atlas(plot_photos(), r"""
assert.equal(atlasView,'plot');assert.equal($('plotView').hidden,false);assert.equal($('locationsView').hidden,false);assert.equal(document.activeElement,$('plotView'));assert.equal(location.hash,'#frame=query&view=plot');
assert.equal($('showPlotView').getAttribute('aria-pressed'),'true');assert.equal(frameHash('query','plot'),'#frame=query&view=plot');
for(const link of navLinks.filter(link=>link.getAttribute('data-site-task')))assert.equal(link.getAttribute('aria-current'),null);
const back=location.hash;navLinks[4].onclick({button:0,preventDefault(){}});assert.equal(atlasView,'locations');assert.equal($('plotView').hidden,true);assert.equal(historyEntries.at(-1),'#frame=query&view=locations');
location.hash=back;listeners.popstate();assert.equal(atlasView,'plot');assert.equal($('plotView').hidden,false);
select(3);assert.equal(location.hash,'#frame=p3&view=plot');
select(0);$('inspectPhoto').focus();assert.equal(openPhotoComparison(0,$('inspectPhoto')),true);$('chooseComparison').onclick();assert.equal(atlasView,'plot');assert.equal(selected,1);assert.equal(document.activeElement,$('plotView'));
""", initial_hash="#frame=query&view=plot", page="embedding-atlas.html")


def test_plantnet_return_link_keeps_plot_view():
    run_atlas(plot_photos(), r"""
const link=$('ordinaryMatchingLink');assert.equal(link.getAttribute('data-atlas-view'),'plot');assert.equal(link.textContent,'Back to Pl@ntNet visual relationships');assert.equal(link.getAttribute('href'),'embedding-atlas.html#frame=query&view=plot');
""", initial_hash="#frame=query&view=plot", page="crownfirst-atlas.html")


def test_old_view_links_still_open_their_views():
    for view, panel in [("photos", "photosView"), ("locations", "locationsView"), ("models", "modelComparisonView"), ("unknown", "photosView")]:
        run_atlas(plot_photos(), r"""
assert.equal(atlasView,__VIEW__);assert.equal($(__PANEL__).hidden,false);assert.equal($('plotView').hidden,true);assert.equal($('showPlotView').getAttribute('aria-pressed'),'false');
""".replace("__VIEW__", repr("photos" if view == "unknown" else view)).replace("__PANEL__", repr(panel)), initial_hash="#frame=query&view=" + view)


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
        p["label"] = None
    run_atlas(points, r"""
assert.deepEqual(plotTop,[]);assert.deepEqual($('plotLegend').children.map(b=>b.children[1].textContent),['No recorded label (15)']);
""")
