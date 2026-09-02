"""The export-only page, which is the one page with no snapshot behind it.

`build_export_only.py` scores a single Labelbox export on its own and answers
"how did this batch do", nothing else. That makes it the page whose inputs are
hardest to test: no NDJSON export is tracked in the repo, and inventing fixture
data would test the fixture rather than the merge. So the export these tests
build comes from the repo's own real inputs, and the first test here calls the
real merge script on it to prove the shape is one that script accepts.

The three page-shape invariants every page shares are in `tests/test_pages.py`,
which runs them against this page too.

    .venv/bin/pytest tests/test_export_only_page.py
"""

from __future__ import annotations

import pathlib
import re

from conftest import (
    GT_KEY_PREFIX,
    PAGES,
    build_page,
    corpus_keys_with_species_gt,
    require_buildable,
    write_export_ndjson,
)

REPO = pathlib.Path(__file__).resolve().parents[1]



def _gt_from_export():
    """Import labelling/gt_from_export.py by path, the same trick
    build_export_only.py's own `_load_gt_from_export` uses: labelling/ is not
    a package on the normal import path."""
    import importlib.util
    path = REPO / "labelling" / "gt_from_export.py"
    spec = importlib.util.spec_from_file_location("_gt_from_export", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_generated_export_is_in_the_shape_export_dominants_parses(export_fixture):
    """The hard part this suite exists to get right: nothing guarantees the
    NDJSON shape invented above is the shape the real merge script accepts.
    This calls `export_dominants` on the generated file directly and checks it
    recovers exactly the species that were put in, rather than trusting the
    shape by construction."""
    path, keys, gt = export_fixture
    dominants, _, _ = _gt_from_export().export_dominants(path)
    assert dominants, "export_dominants returned nothing -- the NDJSON shape is wrong"
    for gk in keys:
        stem = gk[len(GT_KEY_PREFIX):]
        assert dominants.get(stem) == gt[gk], (
            f"export_dominants did not recover the species put in for {gk}")


def test_build_renders_the_no_score_note_when_nothing_joins(tmp_path_factory):
    """The branch nothing else here covers: every labelled key in the export
    has no cached Pl@ntNet prediction, so nothing can be scored. Real keys
    again -- the corpus's own GT rows with no file under
    data/predictions/cache -- not a fabricated gap."""
    require_buildable()
    _, without_cache, gt = corpus_keys_with_species_gt()
    assert without_cache, (
        "no GT key on this machine lacks a cached prediction -- nothing to build this from")
    path = tmp_path_factory.mktemp("export_nocache") / "export.ndjson"
    write_export_ndjson(path, without_cache, gt)
    html, _ = build_page(tmp_path_factory, *PAGES["export_only_page"][:2], export=str(path))
    assert ("No photo in this export both carries a species label and has a "
            "cached Pl@ntNet prediction") in html
    assert not re.search(r"\d+\.\d%", html), "an accuracy percentage was printed anyway"


def _funnel_counts(html):
    """The numbers off the funnel, in the order the page lists them."""
    funnel = re.search(r'<ul class="todo">(.*?)</ul>', html, re.DOTALL)
    assert funnel, "the export page rendered no funnel"
    counts = [int(x.replace(",", ""))
              for x in re.findall(r'<span class="n">([\d,]+)</span>', funnel.group(1))]
    assert len(counts) == 7, f"expected seven funnel steps, got {counts}"
    return counts


def _assert_funnel_adds_up(counts):
    """Rows, labelled, cached, species, genus, empty answer, no cached answer.
    Every labelled row ends in exactly one of the last four."""
    rows, labelled, cached, species, genus, empty, no_cache = counts
    assert labelled <= rows
    assert cached + no_cache == labelled, (
        f"labelled {labelled} is not cached {cached} plus un-cached {no_cache}")
    assert species + genus + empty == cached, (
        f"cached {cached} is not species {species} plus genus-only {genus} "
        f"plus empty answers {empty}")


def test_the_export_funnel_accounts_for_every_row(export_only_page):
    """The funnel exists to say where the rows that are not in the accuracy
    rate went. It once dropped the genus-only frames, then the frames whose
    cached answer names nothing: both times the counts on screen did not add
    up, and a reader who checked found rows missing."""
    html, _ = export_only_page
    _assert_funnel_adds_up(_funnel_counts(html))


def test_the_funnel_still_adds_up_when_rows_fall_into_every_step(tmp_path_factory):
    """The fixture export above is 48 keys that all score, so four of the
    seven steps are zero there and the arithmetic is never really tested.
    This one is built to put real rows in all of them: keys that score, keys
    with no cached answer at all, and keys whose cached answer is an empty
    list of names. The last group is the one the funnel used to drop."""
    require_buildable()
    with_cache, without_cache, gt = corpus_keys_with_species_gt()
    empty = _keys_whose_cached_answer_names_nothing(with_cache)
    assert without_cache and empty, (
        "this machine's cache has no un-cached and no empty-answer key, "
        "so there is nothing to build the mixed export from")
    keys = sorted(set(with_cache[:48]) | set(without_cache) | set(empty))
    path = tmp_path_factory.mktemp("export_mixed") / "export.ndjson"
    write_export_ndjson(path, keys, gt)
    html, _ = build_page(tmp_path_factory, *PAGES["export_only_page"][:2], export=str(path))
    counts = _funnel_counts(html)
    _assert_funnel_adds_up(counts)
    assert counts[5] == len(empty), (
        f"{len(empty)} keys have an empty cached answer, the funnel says {counts[5]}")
    assert counts[6] == len(without_cache), (
        f"{len(without_cache)} keys have no cached answer, the funnel says {counts[6]}")


def _keys_whose_cached_answer_names_nothing(keys):
    """The keys whose cache file parses but holds no ranked name, read through
    `health.scan_cache` so this agrees with the builder by construction rather
    than by a second reading of the JSON."""
    import sys
    sys.path.insert(0, str(REPO / "dashboard"))
    import health as hl
    predictions = hl.scan_cache(str(REPO / "data" / "predictions" / "cache")).predictions
    return [gk for gk in keys if not predictions.get(gk[len(GT_KEY_PREFIX):])]


def test_the_export_only_page_links_no_csv(export_only_page):
    """It scores one export and has no snapshot, so nothing could be copied.

    The other two builders put every CSV they link next to the page they
    write. This one runs its own main(), with no --verify-against and no
    folder to copy from, so a panel that starts linking a CSV would ship a
    dead link here while both other pages stayed correct.
    """
    html, _ = export_only_page
    assert not re.findall(r'href="([A-Za-z0-9_]+\.csv)"', html)
