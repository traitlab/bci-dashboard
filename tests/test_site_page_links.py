"""Status buttons wait for the table they drive; species names open the explorer."""
import json
import subprocess
from types import SimpleNamespace

NODE = r"""
const src = process.argv[1];
const ready = [];
let tableBuilt = false, changed = 0;
const select = {value: "all", dispatchEvent() { changed++; }, closest: () => null};
const button = {getAttribute: () => process.argv[2], addEventListener(_, f) { this.click = f; }};
global.Event = function () {};
global.document = {
  addEventListener(name, f) { ready.push(f); },
  getElementById: id => (tableBuilt && id === "status-filter" ? select : null),
  querySelectorAll: () => [button],
};
new Function(src)();           // runs while the select does not exist yet
tableBuilt = true;             // the parser reaches the table
ready.forEach(f => f());       // DOMContentLoaded
if (button.click) button.click();
console.log(JSON.stringify({value: select.value, changed}));
"""


def test_status_buttons_filter_the_table_that_comes_after_them(panels):
    import landing
    from status_words import STATUS
    key = next(iter(STATUS))
    c = SimpleNamespace(n_sp=2, status={"a": key, "b": key})
    html = landing.status_bar(c)
    script = html.split("<script>")[1].split("</script>")[0]
    out = subprocess.run(["node", "-e", NODE, script, key], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == {"value": key, "changed": 1}


def test_explorer_link_encodes_the_name_and_needs_the_explorer(assets):
    c = SimpleNamespace(available_pages={"explorer.html"})
    html = assets.explorer_link(c, "Ficus a&b/c d", "recorded", "label")
    assert html == '<a href="explorer.html#source=recorded&amp;search=Ficus%20a%26b%2Fc%20d">label</a>'
    assert assets.explorer_link(SimpleNamespace(), "x", "recorded", "label") == "label"


def test_review_table_links_both_names(panels):
    r = {"gt": "ficus insipida", "ranked": [("ficus maxima", 0.9)], "global_key": "k"}
    c = SimpleNamespace(available_pages={"explorer.html"})
    html = panels._review_table(c, [(("ficus insipida", "ficus maxima"), [r])], {})
    assert 'href="explorer.html#source=recorded&amp;search=ficus%20insipida"' in html
    assert 'href="explorer.html#source=prediction&amp;search=ficus%20maxima"' in html


def test_queue_preview_links_the_guess_to_the_explorer(queue_panels, monkeypatch):
    monkeypatch.setattr(queue_panels.hc, "labelbox_urls", dict)
    c = SimpleNamespace(queue_rows=[("long_tail", "DJI_a.JPG", "species a", 0.1, 1, "0.500")],
                        support={}, selection_audit=None, n_batch1=1,
                        available_pages={"explorer.html"})
    html = queue_panels.send_preview_table(c)
    assert 'href="explorer.html#source=prediction&amp;search=species%20a"' in html
