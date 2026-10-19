"""Review signals compare resolved lineage branches without claiming label errors."""

import copy

import pytest
from test_explorer_browser import SELECTED, catalogue, run_browser


def test_compare_filter_counts_compose_and_restore_from_history():
    run_browser(r"""
const first=state.frame;
assert.equal($('labelStatus').options.at(-1).textContent,'Label and guess differ (1)');
$('labelStatus').value='compare';$('labelStatus').onchange();
assert.equal(state.status,'compare');assert.match(location.hash,/status=compare/);
assert.equal($('browseTitle').textContent,'Label and guess differ');
assert.deepEqual(matchingPhotoKeys(catalogue,state),[first]);
assert.equal($('stateNotice').textContent,'');assert.match($('resultCount').textContent,/1 of 6/);
setState({source:'recorded',taxon:'s',search:'flight-a'});
assert.equal($('browseTitle').textContent,'Canopia alba: Label and guess differ');
assert.deepEqual(labelStatusCounts(catalogue,state),{all:1,with:1,without:0,compare:1});
assert.equal(taxonCounts(catalogue,state).get('s'),1);
const saved=location.hash;setState({status:'without',source:'prediction',taxon:'',search:''});
location.hash=saved;listeners.popstate();
assert.equal(state.status,'compare');assert.equal(state.source,'recorded');assert.equal(state.taxon,'s');assert.equal(state.search,'flight-a');assert.equal(state.frame,first);
assert.equal($('labelStatus').value,'compare');
setState({source:'prediction',taxon:'s'});
assert.deepEqual(matchingPhotoKeys(catalogue,state),[]);
assert.deepEqual(labelStatusCounts(catalogue,state),{all:2,with:1,without:1,compare:0});
assert.equal($('gallery').children.length,0);assert.match($('outsideNotice').textContent,/outside/);
location.hash='#source=prediction&status=compare&frame=b';listeners.hashchange();
assert.equal(state.status,'compare');assert.equal(state.frame,'b');assert.deepEqual(matchingPhotoKeys(catalogue,state),[first]);
$('allPhotos').onclick();assert.equal(state.status,'all');
""", initial_hash=SELECTED)


@pytest.mark.parametrize("recorded,predicted,expected", [
    ("s", "t", True), ("s", "other", True),
    ("s", "s", False), ("g", "s", False), ("s", "g", False),
    ("f", "s", False), ("s", "f", False),
    (None, "s", False), ("s", None, False),
    ("unknown", "s", False), ("s", "unknown", False),
])
def test_compare_requires_separate_resolved_branches(recorded, predicted, expected):
    data = catalogue()
    sample = data["photos"][0]
    sample["recorded_taxon"] = recorded
    sample["prediction"]["taxon"] = predicted
    data["photos"] = [sample]
    run_browser("assert.equal(matchingPhotoKeys(catalogue,{...state,status:'compare'}).length," + str(int(expected)) + ");", payload=data)


@pytest.mark.parametrize("mutation", ["recorded_unresolved", "prediction_unresolved", "no_label", "no_guess", "predictions_unavailable", "empty"] )
def test_compare_excludes_unavailable_or_unresolved_evidence(mutation):
    data = catalogue()
    data["photos"] = [copy.deepcopy(data["photos"][0])]
    sample = data["photos"][0]
    if mutation == "recorded_unresolved":
        sample["recorded_status"] = "unresolved"
    elif mutation == "prediction_unresolved":
        sample["prediction"]["status"] = "unresolved"
    elif mutation == "no_label":
        sample["label"] = " \t "
    elif mutation == "no_guess":
        sample["prediction"]["name"] = ""
    elif mutation == "predictions_unavailable":
        data["provenance"]["predictions"]["available"] = False
    else:
        data["photos"] = []
    run_browser(r"""
for(const source of ['prediction','recorded']){
setState({source,status:'compare'});
assert.deepEqual(matchingPhotoKeys(catalogue,state),[]);
assert.equal(labelStatusCounts(catalogue,state).compare,0);
assert.equal(Array.from(taxonCounts(catalogue,state).values()).reduce((a,b)=>a+b,0),0);
if(catalogue.provenance.predictions.available===false)assert.match($('stateNotice').textContent,/Label comparison unavailable/);
}
""", payload=data)


def test_similar_photo_links_name_their_evidence_origin_without_changing_rank():
    data = catalogue()
    data["photos"][0]["representation"]["neighbours"] = [
        {"key": "z", "score": .9}, {"key": "d", "score": .8}, {"key": "c", "score": .7}, {"key": "e", "score": .6},
    ]
    data["photos"][2]["label"] = None
    run_browser(r"""
const names=$('similar').children.map(n=>n.children[0].textContent);
assert.deepEqual(names,['Recorded label: Elseaceae · cosine 0.9','Pl@ntNet first guess: Canopia alba · cosine 0.8','No recorded label or Pl@ntNet first guess · cosine 0.7','Recorded label: Old unresolved name · cosine 0.6']);
$('similar').children[1].children[0].onclick();assert.equal(state.frame,'d');
""", payload=data)


def test_global_similarity_task_retains_the_photo_when_matches_are_unavailable():
    run_browser(r"""
const task=$('similarPhotosTask');
assert.equal(new URLSearchParams(new URL(task.href,'https://example.org').hash.slice(1)).get('frame'),state.frame);
setState({frame:'b'});const fallback=new URL(task.href,'https://example.org');assert.equal(fallback.pathname,'/embedding-atlas.html');assert.equal(new URLSearchParams(fallback.hash.slice(1)).get('frame'),'b');assert.ok(new URLSearchParams(fallback.hash.slice(1)).get('browse'));
assert.match(task.getAttribute('aria-label'),/Find similar photos with Pl@ntNet/);
assert.equal($('plantnetResearch').getAttribute('aria-disabled'),null);
setState({frame:'a & ä /?.JPG'});assert.match(task.getAttribute('aria-label'),/Find similar photos/);
assert.equal(new URLSearchParams(new URL(task.href,'https://example.org').hash.slice(1)).get('frame'),state.frame);
""")


def test_cards_show_both_evidence_names_in_a_fixed_order_in_every_view():
    run_browser(r"""
function copy(key){return $('gallery').children.find(card=>card.getAttribute('data-frame')===key).children[1].children.filter(n=>n.className!=='card-selection').map(n=>[n.className,n.textContent])}
const first=state.frame,expected=[['card-name','Canopia alba'],['card-evidence','Recorded label'],['card-name','Canopia lutea'],['card-evidence','Pl@ntNet first guess']];
assert.deepEqual(copy(first).slice(0,4),expected);
for(const patch of [{status:'compare'},{source:'recorded'},{status:'all'}]){setState(patch);assert.deepEqual(copy(first).slice(0,4),expected)}
const unlabelled=photos.find(p=>!hasRecordedLabel(p)&&matchingPhotoKeys(catalogue,state).includes(p.key));
assert.deepEqual(copy(unlabelled.key)[0],['card-name card-missing','No recorded label']);
""")


def test_review_help_explains_branch_scope_only_while_comparing():
    run_browser(r"""
assert.equal($('labelStatusHelp').hidden,true);
setState({status:'compare'});
assert.match($('labelStatusHelp').textContent,/resolved taxa on different branches/);
assert.match($('labelStatusHelp').textContent,/coarser labels on the same lineage are excluded/);
assert.match($('labelStatusHelp').textContent,/not verified errors/);
assert.match($('labelStatusHelp').textContent,/different crowns/);
setState({status:'without'});assert.equal($('labelStatusHelp').hidden,true);
assert.match($('similarPhotosTask').getAttribute('aria-label'),/^Similar photos\./);
""")


def test_selected_guess_confidence_is_rounded_in_place_without_changing_evidence():
    data = catalogue()
    data['photos'][0]['prediction']['score'] = .34568
    data['photos'][1]['prediction']['score'] = .97412
    run_browser(r"""
const evidence=JSON.stringify(photos);
assert.equal($('recordedLabel').children[0].textContent,'Canopia alba');
assert.equal($('recordedLabel').children.length,1);
assert.equal($('predictionLabel').children[0].textContent,'Canopia lutea');
assert.equal($('predictionLabel').children[1].textContent,'Pl@ntNet confidence in this guess: 0.35 / 1');
assert.equal($('predictionLabel').children[2].textContent,'Higher scores indicate stronger model confidence. This does not confirm the identification.');
setState({frame:'b'});
assert.equal($('recordedLabel').children[0].textContent,'Canopia');
assert.equal($('predictionLabel').children[0].textContent,'Canopia alba');
assert.equal($('predictionLabel').children[1].textContent,'Pl@ntNet confidence in this guess: 0.97 / 1 Tied first score.');
setState({frame:'c'});
assert.equal($('predictionLabel').children[0].textContent,'No cached first guess');
assert.equal($('predictionLabel').children[1].textContent,'Pl@ntNet confidence unavailable: no first guess.');
assert.equal(JSON.stringify(photos),evidence);
""", payload=data)


@pytest.mark.parametrize('score,display', [(0, '0.00'), (1, '1.00'), (.34568, '0.35'), (.004, '0.00'), (.999, '1.00')])
def test_selected_guess_confidence_uses_two_decimals_including_score_boundaries(score, display):
    data = catalogue()
    data['photos'][0]['prediction']['score'] = score
    run_browser("assert.equal($('predictionLabel').children[1].textContent," + repr('Pl@ntNet confidence in this guess: ' + display + ' / 1') + ");", payload=data)


@pytest.mark.parametrize('score', ['undefined', 'null', "''", "'0.35'", 'NaN', 'Infinity', '-Infinity', '-.01', '1.01', 'true'])
def test_selected_guess_confidence_rejects_missing_nonfinite_and_invalid_scores_without_coercion(score):
    run_browser(r"""
const prediction=photos[0].prediction;
prediction.score=__SCORE__;
const original=prediction.score;
renderInspector();
assert.equal($('predictionLabel').children[1].textContent,'Pl@ntNet confidence in this guess: unavailable');
assert.equal($('predictionLabel').children[2].textContent,'Higher scores indicate stronger model confidence. This does not confirm the identification.');
assert.ok(Object.is(prediction.score,original));
""".replace('__SCORE__', score))


@pytest.mark.parametrize('name', [None, '', ' \t '])
def test_confidence_cannot_be_associated_with_a_recorded_label_when_guess_is_missing(name):
    data = catalogue()
    data['photos'][0]['prediction'].update(name=name, status='missing', score=.34568)
    run_browser(r"""
assert.equal($('recordedLabel').children[0].textContent,'Canopia alba');
assert.equal($('predictionLabel').children[0].textContent,'No cached first guess');
assert.equal($('predictionLabel').children[1].textContent,'Pl@ntNet confidence unavailable: no first guess.');
assert.equal($('predictionLabel').children.length,2);
assert.equal(photos[0].prediction.score,.34568);
""", payload=data)
