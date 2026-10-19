"""Visual relationships plot: recorded-label colours, matches, zoom, pan and hover."""

from test_atlas_mission_view import photo, run_atlas


def plot_photos():
    labels = ["A", "A", "A", "B", "B", "C", "D", "E", "F", "G", "H", "I", "J", None, None]
    points = [photo(f"p{i}", "flight-b", label=label, xy=[i, i % 3]) for i, label in enumerate(labels)]
    points[0] = photo("query", "flight-a", [[1, .9], [3, .8]], label="A", xy=[0, 0], other_mission_neighbours=[[5, .7]])
    return points


def test_plot_colours_by_label_draws_ranked_matches_and_supports_zoom_pan_hover():
    run_atlas(plot_photos(), r"""
const legend=$('plotLegend').children;
assert.deepEqual(legend.map(b=>b.children[1].textContent),['A (3)','B (2)','C (1)','D (1)','E (1)','F (1)','G (1)','H (1)','Other recorded label (2)','No recorded label (2)']);
assert.equal(plotClass(P[11]),8);assert.equal(plotClass(P[13]),9);assert.equal(legend[8].children[0].style.background,'#8c8c8c');
const pc=context('plot');pc.fills=[];pc.arcs=[];pc.texts=[];pc.lines=[];draw();
assert.deepEqual(pc.fills.slice(0,2),['#cfd8dd','#cfd8dd']);assert.deepEqual(pc.arcs.slice(0,2),[2,2]);assert.equal(pc.fills.at(-1),'#06283b');assert.deepEqual(pc.arcs.slice(-3),[10,10,7]);
assert.deepEqual(pc.fills.slice(-3,-1),['#E69F00','#56B4E9']);assert.deepEqual(pc.texts.map(t=>t[0]),['1','2']);
const q=plotHits.find(h=>h[2]===0);assert.deepEqual(pc.lines,[[q[0],q[1]],plotHits.find(h=>h[2]===1).slice(0,2),[q[0],q[1]],plotHits.find(h=>h[2]===3).slice(0,2)]);
assert.match($('plotExplanation').textContent,/two PCA components.*retained variance is not recorded.*recorded frame label, not independently verified ground truth.*not prove they are the same species/);
data.provenance.pca_explained_variance=[.2,.1,.05];draw();assert.match($('plotExplanation').textContent,/retain 30.0% of embedding variance/);
legend[1].onclick();assert.equal(plotFocus,1);assert.deepEqual(legend.map(b=>b.getAttribute('aria-pressed')),legend.map((_,i)=>String(i===1)));
pc.fills=[];draw();assert.equal(pc.fills.filter(f=>f==='#56B4E9').length,2);assert.equal(pc.fills.filter(f=>f==='#E69F00').length,1);assert.equal(pc.fills.filter(f=>f==='#dde4e8').length,11);
legend[1].onclick();assert.equal(plotFocus,null);assert.equal(legend.every(b=>b.getAttribute('aria-pressed')==='false'),true);
$('mapMissionMode').value='other';$('mapMissionMode').onchange();pc.texts=[];draw();assert.deepEqual(pc.texts.map(t=>t[0]),['1']);$('mapMissionMode').value='all';$('mapMissionMode').onchange();
const target=plotHits.find(h=>h[2]===7),[tx,ty]=target;
plot.onwheel({deltaY:-1,offsetX:tx,offsetY:ty,preventDefault(){}});assert.equal(plotView.k,1.25);const after=plotHits.find(h=>h[2]===7);assert.ok(Math.abs(after[0]-tx)<1e-9&&Math.abs(after[1]-ty)<1e-9);
$('plotZoomIn').onclick();assert.equal(plotView.k,2);$('plotZoomOut').onclick();$('plotZoomOut').onclick();$('plotZoomOut').onclick();assert.equal(plotView.k,1);
$('plotReset').onclick();assert.deepEqual(plotView,{k:1,x:0,y:0});
plot.onpointermove({offsetX:tx+3,offsetY:ty});assert.equal($('plotTip').hidden,false);assert.equal($('plotTip').textContent,'E · p7');
const blank=plotHits.find(h=>h[2]===13);plot.onpointermove({offsetX:blank[0],offsetY:blank[1]});assert.equal($('plotTip').textContent,'No recorded label · p13');
plot.onpointerleave();assert.equal($('plotTip').hidden,true);
plot.onpointerdown({offsetX:tx,offsetY:ty,pointerId:1});plot.onpointermove({offsetX:tx+40,offsetY:ty});plot.onpointerup({offsetX:tx+40,offsetY:ty});assert.equal(selected,0);assert.equal(plotView.x,40);assert.equal(plotDrag,null);
$('plotReset').onclick();plot.onpointerdown({offsetX:tx,offsetY:ty,pointerId:1});plot.onpointerup({offsetX:tx,offsetY:ty});assert.equal(selected,0);assert.equal($('photoComparison').open,true);assert.deepEqual(photoComparison.candidates,[[7,null]]);
""")
