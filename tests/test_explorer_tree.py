"""The taxon outline is a WAI-ARIA tree: one tab stop, arrow keys move, Enter and Space select."""

import json
import re

from test_explorer_browser import ROOT, catalogue, helpers, node, run_browser

TREE = r"""
const host=$('taxonomy'),tree=()=>host.children.at(-1),row=id=>host.querySelector('[data-taxon="'+id+'"]');
function rows(){const out=[];(function visit(n){if(n.getAttribute?.('role')==='treeitem')out.push(n);for(const child of n.children||[])visit(child)})(host);return out}
const tabbable=()=>rows().filter(r=>r.getAttribute('tabindex')==='0').map(r=>r.getAttribute('data-taxon')),chevron=id=>row(id).children[0].children[0],share=id=>row(id).children[0].style;
function press(key,extra={}){let prevented=false;tree().onkeydown({key,target:document.activeElement,...extra,preventDefault(){prevented=true}});return prevented}
"""


def test_rows_carry_tree_roles_levels_expansion_and_selection():
    run_browser(TREE + r"""
chooseTaxon('s');
assert.equal(tree().getAttribute('role'),'tree');assert.equal(tree().getAttribute('aria-label'),'Taxon groups');assert.equal(host.children[0].getAttribute('aria-label'),'Group by');assert.equal(rows().includes(host.children[0]),false);
for(const [id,level,expanded] of [['unassigned','1',null],['other','1',null],['f','1','true'],['g','2','true'],['s','3',null],['t','3',null]]){assert.equal(row(id).getAttribute('role'),'treeitem');assert.equal(row(id).getAttribute('aria-level'),level);assert.equal(row(id).getAttribute('aria-expanded'),expanded);assert.equal(row(id).getAttribute('aria-selected'),String(id==='s'))}
assert.deepEqual(rows().map(r=>r.getAttribute('data-taxon')),['unassigned','other','f','g','s','t']);
const group=row('f').children[1];assert.equal(group.getAttribute('role'),'group');assert.equal(group.children[0],row('g'));
assert.equal(row('f').children[0].children[2].children[0].tagName,'span');assert.equal(row('g').children[0].children[2].children[0].tagName,'em');assert.equal(row('s').children[0].children[2].children[0].tagName,'em');
assert.equal(row('g').getAttribute('aria-label'),'Canopia, genus, 3 photos, 100% of Forestaceae, 2 confirmed by a recorded label');
assert.equal(row('f').getAttribute('aria-label'),'Forestaceae, family, 3 photos, 50% of matching photos, 2 confirmed by a recorded label');
assert.equal(row('t').getAttribute('aria-label'),'Canopia lutea, species, 1 photo, 33% of Canopia, 0 confirmed by a recorded label');
assert.equal(share('g')['--s'],'100.00%');assert.equal(share('g')['--k'],'66.67%');assert.equal(share('f')['--s'],'50.00%');assert.equal(share('t')['--k'],'0.00%');
assert.equal(host.children[2].textContent,'Bar: share of the group above. Dark: a recorded label agrees.');
setState({source:'recorded'});assert.equal(host.children.length,3);assert.equal(row('f').getAttribute('aria-label'),'Forestaceae, family, 3 photos, 50% of matching photos');assert.equal(share('f')['--k'],share('f')['--s']);
""")


def test_exactly_one_row_is_tabbable_and_follows_the_selection():
    run_browser(TREE + r"""
assert.deepEqual(tabbable(),['unassigned']);
chooseTaxon('s');assert.deepEqual(tabbable(),['s']);
chevron('f').onclick();assert.equal(row('s'),null);assert.deepEqual(tabbable(),['unassigned']);
setState({taxon:'any'});assert.deepEqual(tabbable(),['unassigned']);
setState({search:'no photo matches'});assert.deepEqual(rows(),[]);assert.deepEqual(tabbable(),[]);
""")


def test_arrow_home_and_end_keys_move_focus_without_selecting():
    run_browser(TREE + r"""
const taxon=state.taxon,entries=historyEntries.length;row('unassigned').focus();
const at=()=>document.activeElement.getAttribute('data-taxon');
assert.equal(press('ArrowUp'),true);assert.equal(at(),'unassigned');
press('ArrowDown');assert.equal(at(),'other');press('ArrowDown');assert.equal(at(),'f');assert.deepEqual(tabbable(),['f']);
press('ArrowRight');assert.equal(at(),'f');assert.equal(row('f').getAttribute('aria-expanded'),'true');
press('ArrowRight');assert.equal(at(),'g');press('ArrowRight');assert.equal(row('g').getAttribute('aria-expanded'),'true');assert.equal(at(),'g');
press('ArrowRight');assert.equal(at(),'s');press('ArrowRight');assert.equal(at(),'s');
press('ArrowLeft');assert.equal(at(),'g');press('ArrowLeft');assert.equal(at(),'g');assert.equal(row('s'),null);press('ArrowLeft');assert.equal(at(),'f');press('ArrowLeft');assert.equal(row('g'),null);press('ArrowLeft');assert.equal(at(),'f');
press('End');assert.equal(at(),'f');press('ArrowRight');press('End');assert.equal(at(),'g');press('ArrowDown');assert.equal(at(),'g');press('Home');assert.equal(at(),'unassigned');assert.deepEqual(tabbable(),['unassigned']);
assert.equal(state.taxon,taxon);assert.equal(historyEntries.length,entries);
for(const extra of [{altKey:true},{ctrlKey:true},{metaKey:true}])assert.equal(press('ArrowDown',extra),false);assert.equal(press('a'),false);assert.equal(at(),'unassigned');
""")


def test_enter_and_space_select_the_focused_row_and_keep_focus():
    run_browser(TREE + r"""
row('other').focus();assert.equal(press('Enter'),true);assert.equal(state.taxon,'other');assert.equal(document.activeElement,row('other'));assert.equal(row('other').getAttribute('aria-selected'),'true');
press('Home');assert.equal(press(' '),true);assert.equal(state.taxon,'unassigned');assert.equal(document.activeElement,row('unassigned'));assert.deepEqual(tabbable(),['unassigned']);
""")


def test_chevron_toggles_without_selecting_and_expansion_survives_rerenders():
    run_browser(TREE + r"""
const entries=historyEntries.length;let stopped=false;chevron('f').onclick({stopPropagation(){stopped=true}});assert.equal(stopped,true);
assert.equal(row('f').getAttribute('aria-expanded'),'true');assert.ok(row('g'));assert.equal(state.taxon,'');assert.equal(historyEntries.length,entries);
setState({search:'flight'});assert.ok(row('g'));chevron('f').onclick();assert.equal(row('g'),null);
chooseTaxon('s');assert.equal(row('f').getAttribute('aria-expanded'),'true');assert.equal(row('g').getAttribute('aria-expanded'),'true');
chevron('f').onclick();setState({search:'flight-a'});assert.equal(row('f').getAttribute('aria-expanded'),'false');assert.equal(state.taxon,'s');
chooseTaxon('t');assert.equal(row('f').getAttribute('aria-expanded'),'true');assert.equal(chevron('t').onclick,undefined);
""")


def test_family_colours_match_the_atlas_palette_and_ranking():
    data = catalogue()
    run_browser(TREE + r"""
chooseTaxon('s');assert.equal(row('f').children[0].children[1].style.background,'#E69F00');assert.equal(row('other').children[0].children[1].style.background,'#8c8c8c');assert.equal(share('s')['--c'],'#E69F00');assert.equal(row('unassigned').children[0].children[1].style.background,'#cfd8dd');
assert.equal(shade('#E69F00',0),'#E69F00');assert.equal(shade('#E69F00',0.45),'rgb(233,170,29)');assert.match(shade('#E69F00',-0.35),/^rgb\(/);
""", payload=data)
    # Counts 10 down to 1; "tie" draws with fam7 and wins on name; fam8's unplotted photos must not lift it.
    taxa = [{"id": f"fam{i}", "name": f"Family {chr(75 - i)}", "rank": "family", "parent": None} for i in range(10)] + [{"id": "tie", "name": "Family A", "rank": "family", "parent": None}]
    counts = {f"fam{i}": 10 - i for i in range(10)} | {"tie": 3}
    photos = [{"key": f"{taxon}-{n}", "recorded_taxon": taxon, "representation": {}} for taxon, total in counts.items() for n in range(total)]
    photos += [{"key": f"unplotted-{n}", "recorded_taxon": "fam8", "representation": None} for n in range(5)]
    node(helpers() + "\nconst c=" + json.dumps({"photos": photos, "taxa": taxa}) + r""";
const assert=require('node:assert/strict'),palette=familyPalette(c);
assert.deepEqual([...palette],[['fam0','#E69F00'],['fam1','#56B4E9'],['fam2','#009E73'],['fam3','#A0A000'],['fam4','#0072B2'],['fam5','#D55E00'],['fam6','#CC79A7'],['tie','#882255']]);
assert.equal(familyPalette({photos:[],taxa:[]}).size,0);
""")


def test_atlas_and_explorer_share_one_palette():
    lists = [re.search(r"(?:PLOT|TAXON)_COLOURS=(\[[^\]]+\])", (ROOT / name).read_text()).group(1) for name in ["dashboard/embedding_atlas_assets.py", "dashboard/explorer_assets.py"]]
    assert lists[0] == lists[1]


def test_confirmed_counts_need_the_recorded_lineage_to_hold_the_taxon():
    data = catalogue()
    data["photos"].append({**data["photos"][1], "key": "y", "recorded_taxon": "other", "prediction": {**data["photos"][1]["prediction"], "taxon": "s"}})
    node(helpers() + "\nconst c=" + json.dumps(data) + r""";
const assert=require('node:assert/strict'),s={...readExplorerState('#source=prediction',c.photos)},confirmed=new Map(),counts=taxonCounts(c,s,confirmed);
assert.equal(counts.get('f'),4);assert.equal(confirmed.get('f'),2);assert.equal(counts.get('g'),4);assert.equal(confirmed.get('g'),2);
assert.equal(counts.get('s'),3);assert.equal(confirmed.get('s'),undefined);assert.equal(counts.get('t'),1);assert.equal(confirmed.get('t'),undefined);
assert.equal(confirmed.get('other'),1);assert.equal(confirmed.has('unassigned'),false);
const none=new Map();taxonCounts(c,{...s,search:'no photo matches'},none);assert.equal(none.size,0);assert.deepEqual([...taxonCounts(c,s)],[...counts]);
""")
