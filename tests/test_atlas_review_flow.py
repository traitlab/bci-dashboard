"""Similar photos review flow: image priority, keyboard, enlarge dialog, dead ends, notes, plot entry."""

import runpy

from test_atlas_mission_view import ROOT, photo, run_atlas
from test_atlas_plot_explore import plot_photos

HTML = runpy.run_path(ROOT / "dashboard/embedding_atlas_assets.py")["HTML"]
KEY = r"""
const key=(name,extra={})=>{const e={key:name,target:element('body'),defaultPrevented:false,preventDefault(){this.defaultPrevented=true},...extra};listeners['document:keydown'](e);return e};
"""


def strip_photos():
    return [
        photo("query", "flight-a", [[1, .9], [2, .8], [3, .7]]),
        photo("one", "flight-b", [[0, .9]]),
        photo("two", "flight-b", [[0, .8]]),
        photo("three", "flight-b", [[0, .7]]),
    ]


def test_main_pair_loads_first_and_strip_thumbnails_wait_for_it():
    assert '<img id="photo" alt="" fetchpriority="high"' in HTML
    assert '<img id="workspaceCandidateImage" alt="" fetchpriority="high"' in HTML
    run_atlas(strip_photos(), r"""
const thumbs=()=>$('neighbors').children.map(li=>li.children[0].children[0]);
assert.equal(thumbs().length,3);assert.equal(thumbs().every(t=>t.src===undefined&&/^thumbs\/480\//.test(t.getAttribute('data-src'))),true);
$('photo').onload();assert.equal(thumbs().every(t=>t.src===undefined),true);
$('workspaceCandidateImage').onerror();assert.deepEqual(thumbs().map(t=>t.src),['thumbs/480/one.webp','thumbs/480/two.webp','thumbs/480/three.webp']);
""")


def test_keyboard_moves_matches_opens_enlarge_and_respects_focus_and_modifiers():
    for button, shortcut in [("workspacePreviousCandidate", "ArrowLeft"), ("workspaceNextCandidate", "ArrowRight"), ("previousComparison", "ArrowLeft"), ("nextComparison", "ArrowRight")]:
        assert f'id="{button}" aria-keyshortcuts="{shortcut}"' in HTML
    run_atlas(strip_photos(), KEY + r"""
assert.equal(photoPair.rank,0);assert.equal(key('ArrowRight').defaultPrevented,true);assert.equal(photoPair.rank,1);key('ArrowLeft');assert.equal(photoPair.rank,0);key('ArrowLeft');assert.equal(photoPair.rank,0);
for(const tagName of ['INPUT','SELECT','TEXTAREA']){assert.equal(key('ArrowRight',{target:{tagName}}).defaultPrevented,false);assert.equal(photoPair.rank,0)}
for(const modifier of ['altKey','ctrlKey','metaKey','shiftKey'])key('ArrowRight',{[modifier]:true});assert.equal(photoPair.rank,0);
key('E',{shiftKey:true});assert.notEqual($('photoComparison').open,true);
key('e');assert.equal($('photoComparison').open,true);assert.equal(photoComparison,photoPair);
key('ArrowRight');assert.equal(photoComparison.rank,1);assert.match($('photoComparisonRank').textContent,/Candidate 2 of 3/);
key('e');assert.equal(photoComparison.rank,1);
imageDetails.get('comparisonCandidate').mode='crop';key('ArrowRight',{target:$('comparisonCandidateViewport')});assert.equal(photoComparison.rank,1);
imageDetails.get('comparisonCandidate').mode='fit';key('ArrowRight',{target:$('comparisonCandidateViewport')});assert.equal(photoComparison.rank,2);
$('closePhotoComparison').onclick();assert.equal($('photoComparison').open,false);
showAtlasView('locations');key('ArrowLeft');key('e');assert.equal(photoPair.rank,2);assert.equal($('photoComparison').open,false);showAtlasView('photos');
const items=()=>$('neighbors').children.map(li=>li.children[0]);
assert.deepEqual(items().map(b=>b.getAttribute('tabindex')),['-1','-1','0']);
let e={key:'ArrowLeft',target:items()[2],preventDefault(){this.defaultPrevented=true}};$('neighbors').onkeydown(e);assert.equal(e.defaultPrevented,true);assert.equal(photoPair.rank,1);assert.equal(document.activeElement,items()[1]);assert.deepEqual(items().map(b=>b.getAttribute('tabindex')),['-1','0','-1']);
listeners['document:keydown'](e);assert.equal(photoPair.rank,1);
$('neighbors').onkeydown({key:'Home',target:items()[1],preventDefault(){}});assert.equal(photoPair.rank,0);assert.equal(document.activeElement,items()[0]);
$('neighbors').onkeydown({key:'ArrowLeft',target:items()[0],preventDefault(){}});assert.equal(photoPair.rank,0);
$('neighbors').onkeydown({key:'End',target:items()[0],preventDefault(){}});assert.equal(photoPair.rank,2);
""")


def test_enlarge_dialog_keeps_candidate_nav_in_sticky_top_and_links_pan():
    top = HTML.split('<div class="photo-dialog-top"><h2 id="photoComparisonTitle">')[1].split("</div>")[0]
    for control in ["previousComparison", "photoComparisonRank", "nextComparison", 'linkPan" aria-pressed="true"']:
        assert f'id="{control}' in top
    assert ".photo-comparison-panel a+a{margin-left:16px}" in HTML
    run_atlas(strip_photos(), r"""
$('workspaceEnlarge').onclick();const q=$('comparisonQueryViewport'),c=$('comparisonCandidateViewport');
Object.assign(q,{scrollWidth:4000,scrollHeight:3000,scrollLeft:1000,scrollTop:600});Object.assign(c,{scrollWidth:2000,scrollHeight:1500,scrollLeft:0,scrollTop:0});
q.onscroll({currentTarget:q});assert.equal(c.scrollLeft,0);
imageDetails.get('comparisonQuery').mode='crop';imageDetails.get('comparisonCandidate').mode='crop';
q.onscroll({currentTarget:q});assert.equal(c.scrollLeft,500);assert.equal(c.scrollTop,300);
q.scrollLeft=1200;c.onscroll({currentTarget:c});assert.equal(q.scrollLeft,1200);
c.scrollLeft=1000;c.onscroll({currentTarget:c});assert.equal(q.scrollLeft,2000);assert.equal(q.scrollTop,600);
$('linkPan').onclick();assert.equal($('linkPan').getAttribute('aria-pressed'),'false');q.scrollLeft=0;q.onscroll({currentTarget:q});assert.equal(c.scrollLeft,1000);
$('linkPan').onclick();assert.equal($('linkPan').getAttribute('aria-pressed'),'true');
$('closePhotoComparison').onclick();$('inspectPhoto').onclick();assert.equal($('photoComparisonNav').hidden,true);assert.equal($('photoComparisonActions').hidden,true);
""")


def test_photos_without_matches_get_a_badge_and_sort_last_deterministically():
    points = [
        photo("query", "flight-a", [[2, .9]]),
        photo("dead-model", "flight-a", model_available=False),
        photo("live-b", "flight-b", [[0, .9]]),
        photo("dead-empty", "flight-b"),
        photo("live-d", "flight-b", [[1, .9], [2, .8]]),
    ]
    run_atlas(points, r"""
assert.deepEqual(visible,[0,2,4,1,3]);assert.deepEqual(matchingBrowseFrames(P,'','All frames',null,false),[0,2,4,1,3]);
const cards=$('results').children,badges=cards.map(card=>card.children[1].children.find(child=>child.className==='browse-photo-badge')?.textContent??null);
assert.deepEqual(cards.map(card=>card.getAttribute('data-frame')),['query','live-b','live-d','dead-model','dead-empty']);
assert.deepEqual(badges,[null,null,null,'No similar photos','No similar photos']);
assert.match(cards[3]['aria-label'],/dead-model\. No similar photos$/);assert.doesNotMatch(cards[0]['aria-label'],/No similar photos/);
$('search').value='dead';$('search').oninput();assert.deepEqual(visible,[1,3]);$('search').value='flight-b';$('search').oninput();assert.deepEqual(visible,[2,4,3]);
assert.deepEqual(matchingBrowseFrames([],'','All frames',null,false),[]);
""")


def test_unsaved_notes_guard_unload_until_downloaded():
    run_atlas(strip_photos(), r"""
location.href='https://example.org/embedding-atlas.html';let downloads=0;downloadReviewJson=()=>{downloads++};const note=$('workspaceReviewNote');
assert.equal(listeners.beforeunload,undefined);
note.value='   ';note.oninput();assert.equal(listeners.beforeunload,undefined);
note.value='Crown looks different';note.oninput();const event={preventDefault(){this.prevented=true}};listeners.beforeunload(event);assert.equal(event.prevented,true);assert.equal(event.returnValue,'');
note.value='';note.oninput();assert.equal(listeners.beforeunload,undefined);
note.value='First pair';note.oninput();setWorkspaceCandidate(1);assert.equal(typeof listeners.beforeunload,'function');
note.value='Second pair';note.oninput();$('workspaceDownloadReview').onclick();assert.equal(downloads,1);assert.equal(typeof listeners.beforeunload,'function');
$('workspaceDownloadAllNotes').onclick();assert.equal(downloads,2);assert.equal(listeners.beforeunload,undefined);
$('workspaceEnlarge').onclick();$('reviewNote').value='Second pair, edited';$('reviewNote').oninput();assert.equal(typeof listeners.beforeunload,'function');
$('downloadReviewRecord').onclick();assert.equal(downloads,3);assert.equal(listeners.beforeunload,undefined);
""")


def test_plot_click_compares_without_changing_selection_and_marker_keeps_label_colour():
    assert ".selected-key{background:#fff;border:3px solid #06283b;box-shadow:0 0 0 3px #f6bd4f}" in HTML
    assert "Selected photo, ringed" in HTML
    run_atlas(plot_photos(), r"""
const click=index=>{const [x,y]=plotHits.find(h=>h[2]===index);plot.onpointerdown({offsetX:x,offsetY:y,pointerId:1});plot.onpointerup({offsetX:x,offsetY:y})};
assert.equal(PLOT_COLOURS.includes(mapPointColour(P[0],0,0,'locations',new Map(),null)),false);assert.equal(PLOT_COLOURS.map(c=>c.toLowerCase()).includes('#f6bd4f'),false);
const pc=context('plot');pc.fills=[];draw();assert.equal(pc.fills.at(-1),PLOT_COLOURS[0]);
click(7);assert.equal($('photoComparison').open,true);assert.equal(selected,0);assert.equal(photoPair.rank,0);assert.equal(photoComparison.plotPoint,true);assert.deepEqual(photoComparison.candidates,[[7,null]]);
assert.equal($('comparisonCandidate').hidden,false);assert.equal($('photoComparisonRank').textContent,'Plot point');assert.match($('photoComparisonScore').textContent,/not a stored match/);
assert.equal($('previousComparison').disabled,true);assert.equal($('nextComparison').disabled,true);assert.equal($('reviewNote').disabled,true);assert.equal($('downloadReviewRecord').disabled,true);assert.match($('reviewDownloadStatus').textContent,/stored matches only/);
$('chooseComparison').onclick();assert.equal($('photoComparison').open,false);assert.equal(selected,7);
select(0);click(3);assert.equal($('photoComparison').open,true);assert.equal(photoComparison,photoPair);assert.equal(photoPair.rank,1);assert.equal(selected,0);$('closePhotoComparison').onclick();
click(0);assert.equal($('photoComparison').open,true);assert.equal(photoComparison.rank,null);assert.equal(selected,0);$('closePhotoComparison').onclick();
const [x,y]=plotHits.find(h=>h[2]===7);plot.onpointerdown({offsetX:x,offsetY:y,pointerId:1});plot.onpointermove({offsetX:x+30,offsetY:y});plot.onpointerup({offsetX:x+30,offsetY:y});assert.equal($('photoComparison').open,false);
""")


def test_plot_legend_counts_drawn_points_names_selected_other_label_and_fits_filters():
    run_atlas(plot_photos(), r"""
const names=()=>$('plotLegend').children.map(b=>b.children[1].textContent);
select(12);assert.deepEqual(names(),['A (3)','B (2)','C (1)','D (1)','E (1)','F (1)','G (1)','H (1)','Other families (2)','No recorded family (2)','Selected: J (other family)']);assert.equal(plotClass(P[12]),8);
const own=$('plotLegend').children.at(-1);assert.equal(own.children[0].style.background,'#8c8c8c');assert.equal(own.onclick,undefined);assert.equal(own.getAttribute('aria-pressed'),null);
select(0);assert.deepEqual(names().slice(7),['H (1)','Other families (2)','No recorded family (2)']);
assert.deepEqual(plotView,{k:1,x:0,y:0});
$('group').value='Without recorded label';$('group').onchange();assert.deepEqual(visible,[13,14]);assert.deepEqual(names(),['A (1)','No recorded family (2)']);
assert.deepEqual(plotHits.map(h=>h[2]).sort((a,b)=>a-b),[0,13,14]);
$('plotLegend').children[1].onclick();assert.equal(plotFocus,9);
select(13);$('search').value='p1';$('search').oninput();assert.deepEqual(visible,[13,14]);assert.deepEqual(names(),['No recorded family (2)']);assert.equal(plotFocus,9);assert.equal($('plotLegend').children[0].getAttribute('aria-pressed'),'true');
assert.equal(plotView.k,2);for(const [x,y] of plotHits){assert.ok(x>=24.99&&x<=640-24.99&&y>=24.99&&y<=520-24.99,`${x},${y}`)}
$('search').value='p13';$('search').oninput();assert.deepEqual(names(),['No recorded family (1)']);assert.equal(plotFocus,9);assert.equal(plotView.k,64);
$('clearBrowseFilters').onclick();assert.deepEqual(plotView,{k:1,x:0,y:0});assert.equal(names().length,10);assert.equal(plotFocus,9);
""")


def test_visual_relationships_nav_opens_plot_as_its_own_view():
    nav = HTML.split('<nav class="workspace-nav"')[1].split("</nav>")[0]
    assert nav.index('id="showLocationsView"') < nav.index('id="showPlotView" aria-controls="plotView" aria-pressed="false">Visual relationships</button>')
    run_atlas(plot_photos(), r"""
const pressed=()=>['showPhotosView','showLocationsView','showPlotView'].map(id=>$(id).getAttribute('aria-pressed'));const entries=historyEntries.length;
$('showPlotView').onclick();assert.equal(atlasView,'plot');assert.equal($('plotView').hidden,false);assert.equal($('locationsView').hidden,false);assert.deepEqual(pressed(),['false','false','true']);assert.equal(location.hash,'#frame=query&view=plot');assert.equal(historyEntries.length,entries+1);assert.equal($('togglePlot').getAttribute('aria-expanded'),'true');assert.equal(document.activeElement,$('plotView'));assert.match($('workspaceTitle').textContent,/visual relationships/i);
$('showPlotView').onclick();assert.equal(historyEntries.length,entries+1);
$('showPhotosView').onclick();assert.deepEqual(pressed(),['true','false','false']);assert.equal($('locationsView').hidden,true);assert.equal($('plotView').hidden,true);
$('showLocationsView').onclick();assert.equal($('plotView').hidden,true);assert.deepEqual(pressed(),['false','true','false']);assert.equal($('togglePlot').textContent,'Explore visual relationships');assert.doesNotMatch(location.hash,/view=/);
$('togglePlot').onclick();assert.equal(atlasView,'plot');assert.equal($('plotView').hidden,false);assert.deepEqual(pressed(),['false','false','true']);assert.equal($('togglePlot').textContent,'Hide visual relationships');assert.match(location.hash,/view=plot/);
$('closePlot').onclick();assert.equal(atlasView,'locations');assert.equal($('plotView').hidden,true);assert.deepEqual(pressed(),['false','true','false']);assert.doesNotMatch(location.hash,/view=/);assert.equal(document.activeElement,$('mapView'));
$('togglePlot').onclick();$('togglePlot').onclick();assert.equal(atlasView,'locations');assert.equal($('plotView').hidden,true);
location.hash='#frame=query&view=photos';listeners.popstate();assert.equal(atlasView,'photos');assert.deepEqual(pressed(),['true','false','false']);
location.hash='#frame=query';listeners.popstate();assert.equal(atlasView,'locations');assert.deepEqual(pressed(),['false','true','false']);assert.equal($('plotView').hidden,true);
location.hash='#frame=query&view=plot';listeners.popstate();assert.deepEqual(pressed(),['false','false','true']);assert.equal($('plotView').hidden,false);
""")
