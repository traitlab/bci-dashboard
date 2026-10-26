"""The Tree view draws the matching photos' taxa as a radial tree beside a card of buttons."""

import copy
from html.parser import HTMLParser

from test_explorer_browser import catalogue, run_browser, template

RADIAL = r"""
const svg=$('radial'),dot=id=>svg.children.find(c=>c.tagName==='g'&&c.getAttribute('data-taxon')===id),shown=()=>svg.children.filter(c=>c.tagName==='g'&&c.getAttribute('data-taxon')).map(c=>c.getAttribute('data-taxon'));
const row=id=>$('taxonomy').querySelector('[data-taxon="'+id+'"]'),crumb=id=>$('treeCrumbs').children.find(c=>c.getAttribute('data-tree-crumb')===id),kid=name=>$('treeKids').children.find(b=>b.getAttribute('aria-label').startsWith(name+','));
const faded=()=>svg.children.filter(c=>c.tagName==='g'&&c.getAttribute('opacity')!=='1').map(c=>c.getAttribute('data-taxon')),hashLayout=()=>new URLSearchParams(location.hash.slice(1)).get('layout');
function find(n,tag){if(n.tagName===tag)return n;for(const c of n.children||[]){const f=find(c,tag);if(f)return f}return null}
"""


class TreeStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = {}
        self.order = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.targets[attrs['id']] = (tag, attrs)
            self.order.append(attrs['id'])


def group_catalogue():
    data = catalogue()
    names = {t['id']: t['name'] for t in data['taxa']}
    sample = data['photos'][0]

    def photo(key, recorded, predicted, score):
        p = copy.deepcopy(sample)
        p.update(key=key, label=names[recorded], recorded_taxon=recorded, recorded_status='ok', representation=None)
        p['prediction'].update(status='ok' if predicted else 'missing', name=names.get(predicted), taxon=predicted, score=score, tied=False)
        return p

    # Listed so the expected pick is never simply the first match in catalogue order.
    data['photos'] = [photo('no-score', 'g', 't', None), photo('unscored', 't', None, None), photo('t-guess', 't', 's', .3), photo('disagrees', 's', 't', .9), photo('agrees', 's', 's', .5), photo('genus-agrees', 'g', 's', .6), photo('lonely', 'other', None, None)]
    return data


def test_tree_is_a_third_view_with_a_labelled_radial_and_a_phone_toggle():
    page = TreeStructure()
    page.feed(template())
    assert page.targets['showTree'] == ('button', {'id': 'showTree', 'aria-pressed': 'false'})
    assert page.order.index('showTree') == page.order.index('showEvidence') + 1
    radial = page.targets['radial'][1]
    assert radial['role'] == 'img' and 'Keyboard users' in radial['aria-label'] and 'taxon outline' in radial['aria-label']
    assert page.targets['showRadial'][1]['aria-pressed'] == 'false' and page.targets['showRadial'][1]['aria-controls'] == 'radialFigure'
    assert '.radial-toggle[aria-pressed=false]+.radial-figure{display:none}' in template()
    run_browser(r"""
// The static template's svg is empty, so the tab-stop check must run on the drawn radial.
const drawn=n=>[n,...(n.children||[]).flatMap(drawn)],parts=$('radial').children.flatMap(drawn);
assert.ok(parts.length>10);assert.deepEqual(parts.filter(n=>n.getAttribute('tabindex')!==null).map(n=>n.tagName),[]);
$('showRadial').onclick();assert.equal($('showRadial').getAttribute('aria-pressed'),'true');
$('showRadial').onclick();assert.equal($('showRadial').getAttribute('aria-pressed'),'false');
""", initial_hash='#layout=tree')


def test_tree_layout_round_trips_through_the_hash_and_presses_one_view_button():
    run_browser(RADIAL + r"""
assert.equal(readExplorerState('#layout=tree',photos).layout,'tree');assert.equal(readExplorerState('#layout=bogus',photos).layout,'photos');
assert.equal(hashLayout(),null);assert.equal($('treeView').hidden,true);
$('showTree').onclick();
assert.equal(state.layout,'tree');assert.equal(hashLayout(),'tree');
for(const [id,pressed] of [['showPhotos','false'],['showEvidence','false'],['showTree','true']])assert.equal($(id).getAttribute('aria-pressed'),pressed);
assert.equal($('treeView').hidden,false);assert.equal($('gallery').hidden,true);assert.equal($('evidenceScroll').hidden,true);assert.equal($('pages').hidden,true);
$('showPhotos').onclick();assert.equal(hashLayout(),null);assert.equal($('treeView').hidden,true);assert.equal($('pages').hidden,false);
$('showEvidence').onclick();assert.equal(hashLayout(),'table');assert.equal($('showTree').getAttribute('aria-pressed'),'false');
location.hash='#layout=tree&source=prediction&taxon=g';listeners.hashchange();
assert.equal(state.layout,'tree');assert.equal(state.taxon,'g');assert.equal($('showTree').getAttribute('aria-pressed'),'true');assert.equal($('treeView').hidden,false);
location.hash='#layout=table&source=prediction';listeners.popstate();assert.equal(state.layout,'table');assert.equal($('treeView').hidden,true);
""")


def test_radial_nodes_select_taxa_in_sync_with_the_outline_and_card():
    run_browser(RADIAL + r"""
assert.deepEqual(shown(),['any','other','f','g','s','t']);
chooseTaxon('any');assert.deepEqual($('treeTitle').children.map(c=>c.textContent),['Any Pl@ntNet taxon']);assert.equal($('treeCount').textContent,'4 photos, 67% of matching photos.');assert.equal(crumb('any').getAttribute('aria-current'),'true');chooseTaxon('');
assert.equal($('treeUp').disabled,true);assert.deepEqual($('treeKids').children.map(b=>b.getAttribute('aria-label')),['Elseaceae, family, 1 photo','Forestaceae, family, 3 photos']);
dot('g').onclick();
assert.equal(state.taxon,'g');assert.equal(new URLSearchParams(location.hash.slice(1)).get('taxon'),'g');
assert.equal(row('g').getAttribute('aria-selected'),'true');assert.equal(row('f').getAttribute('aria-selected'),'false');
assert.deepEqual($('treeCrumbs').children.filter(c=>c.tagName==='button').map(b=>b.textContent),['Any Pl@ntNet taxon','Forestaceae','Canopia']);assert.equal(crumb('g').getAttribute('aria-current'),'true');
assert.deepEqual($('treeTitle').children.map(c=>c.tagName+':'+c.textContent),['em:Canopia','span:genus']);assert.equal($('treeCount').textContent,'3 photos, 100% of Forestaceae.');
assert.equal(dot('g').children[0].children.at(-1).getAttribute('stroke-width'),'3');
// The radial and the outline share one colour per taxon.
for(const id of ['other','f','g','s','t'])assert.equal(dot(id).children[0].children[1].getAttribute('fill'),row(id).children[0].style['--c']);
assert.equal(kid('Canopia alba').children.find(c=>c.className==='taxon-swatch').style.background,row('s').children[0].style['--c']);
crumb('f').focus();crumb('f').onclick();assert.equal(state.taxon,'f');assert.equal(document.activeElement,crumb('f'));assert.equal($('treeCount').textContent,'3 photos, 50% of matching photos.');
kid('Canopia').onclick();assert.equal(state.taxon,'g');assert.equal(document.activeElement,$('treeTitle'));
kid('Canopia lutea').onclick();assert.equal(state.taxon,'t');assert.equal($('treeKidsHeading').textContent,'No groups below this one');assert.deepEqual($('treeKids').children,[]);
crumb('any').onclick();assert.equal(state.taxon,'any');assert.equal(row('any'),null);
""", initial_hash='#layout=tree')


CARD = r"""
const card=()=>({title:$('treeTitle').children.map(c=>c.tagName+':'+c.textContent),count:$('treeCount').textContent,current:$('treeCrumbs').children.filter(c=>c.getAttribute('aria-current')).length});
// Show photos is the other half of the claim: the card's number is the number it lists.
function listed(expected){const text=$('treeCount').textContent;$('treeShowPhotos').onclick();const n=$('gallery').children.length;$('showTree').onclick();assert.equal(n,expected);assert.ok(text.startsWith(n+(n===1?' photo, ':' photos, ')),text)}
"""


def test_card_for_no_taxon_counts_every_photo_and_marks_no_crumb():
    run_browser(RADIAL + CARD + r"""
assert.equal(state.taxon,'');assert.deepEqual(card(),{title:['span:All photos'],count:'6 photos, 100% of matching photos.',current:0});listed(6);
chooseTaxon('any');assert.deepEqual(card(),{title:['span:Any Pl@ntNet taxon'],count:'4 photos, 67% of matching photos.',current:1});listed(4);
""", initial_hash='#layout=tree')


def test_card_for_unassigned_counts_the_unassigned_photos_and_marks_no_crumb():
    run_browser(RADIAL + CARD + r"""
chooseTaxon('unassigned');assert.deepEqual(card(),{title:['span:No Pl@ntNet prediction or unresolved name'],count:'2 photos, 33% of matching photos.',current:0});listed(2);
""", initial_hash='#layout=tree')


def test_card_for_a_filtered_out_taxon_names_it_instead_of_its_ancestor():
    run_browser(RADIAL + CARD + r"""
chooseTaxon('s');setState({search:'lutea',page:0});assert.deepEqual(shown(),['any','f','g','t']);assert.deepEqual(faded(),['t']);
assert.deepEqual(card(),{title:['em:Canopia alba','span:species'],count:'0 photos, 0% of matching photos.',current:0});listed(0);
chooseTaxon('g');assert.deepEqual(card(),{title:['em:Canopia','span:genus'],count:'1 photo, 100% of Forestaceae.',current:1});assert.equal(crumb('g').getAttribute('aria-current'),'true');listed(1);
""", initial_hash='#layout=tree')


def test_only_taxa_outside_the_selected_lineage_and_subtree_fade():
    run_browser(RADIAL + r"""
for(const id of ['','any','unassigned','missing-taxon']){chooseTaxon(id);assert.deepEqual(faded(),[],id)}
chooseTaxon('g');assert.deepEqual(faded(),['other']);
assert.deepEqual(svg.children.filter(c=>c.tagName==='path'&&c.getAttribute('data-taxon')&&c.getAttribute('opacity')!=='1').map(c=>c.getAttribute('data-taxon')),['other']);
chooseTaxon('s');assert.deepEqual(faded(),['other','t']);
chooseTaxon('other');assert.deepEqual(faded(),['f','g','s','t']);
""", initial_hash='#layout=tree')


def test_focus_here_and_up_recentre_without_touching_the_url():
    run_browser(RADIAL + r"""
chooseTaxon('g');const before=location.hash;$('treeFocusHere').onclick();
assert.deepEqual(shown(),['g','s','t']);assert.equal($('treeUp').disabled,false);assert.equal(location.hash,before);
chooseTaxon('s');assert.deepEqual(shown(),['g','s','t']);
$('treeFocusHere').onclick();assert.deepEqual(shown(),['g','s','t']);
$('treeUp').onclick();assert.deepEqual(shown(),['f','g','s','t']);
$('treeUp').focus();$('treeUp').onclick();assert.deepEqual(shown(),['any','other','f','g','s','t']);
assert.equal($('treeUp').disabled,true);assert.equal(document.activeElement,$('treeFocusHere'));
chooseTaxon('g');$('treeFocusHere').onclick();chooseTaxon('other');assert.deepEqual(shown(),['any','other','f','g','s','t']);
chooseTaxon('g');$('treeFocusHere').onclick();chooseTaxon('f');assert.equal(shown()[0],'any');
""", initial_hash='#layout=tree')


def test_group_photo_prefers_agreeing_guesses_for_labels_and_top_scores_for_guesses():
    run_browser(RADIAL + r"""
const pick=()=>Object.fromEntries([...groupPhotos()].map(([id,best])=>[id,best.p.key]));
assert.deepEqual(pick(),{any:'genus-agrees',f:'genus-agrees',g:'genus-agrees',s:'agrees',t:'t-guess',other:'lonely'});
assert.deepEqual($('treeKids').children.map(b=>b.children[0].tagName+':'+(b.children[0].src??'')),['img:thumbs/480/lonely.webp','img:thumbs/480/genus-agrees.webp']);
assert.equal(find(dot('s'),'image').getAttribute('href'),'thumbs/480/agrees.webp');assert.equal(find(dot('other'),'image').getAttribute('href'),'thumbs/480/lonely.webp');
const img=$('treeKids').children[1].children[0];img.onerror();assert.equal(img.hidden,true);
const image=find(dot('t'),'image');image.onerror();assert.equal(image.removed,true);
setState({source:'prediction'});
assert.deepEqual(pick(),{any:'disagrees',f:'disagrees',g:'disagrees',s:'genus-agrees',t:'disagrees'});
assert.equal(find(dot('t'),'image').getAttribute('href'),'thumbs/480/disagrees.webp');
""", payload=group_catalogue(), initial_hash='#layout=tree&source=recorded')


def test_show_photos_switches_to_the_gallery_keeping_the_taxon():
    run_browser(RADIAL + r"""
dot('g').onclick();$('treeShowPhotos').onclick();
assert.equal(state.layout,'photos');assert.equal(state.taxon,'g');assert.equal(hashLayout(),null);
assert.equal($('gallery').hidden,false);assert.equal($('treeView').hidden,true);assert.equal($('showPhotos').getAttribute('aria-pressed'),'true');
assert.deepEqual($('gallery').children.map(c=>c.getAttribute('data-frame')),['a & ä /?.JPG','b','d']);assert.equal(document.activeElement,$('resultCount'));
""", initial_hash='#layout=tree')
