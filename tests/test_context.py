"""CONTEXT.md quotes numbers too, and nothing was comparing them.

`tests/test_plain_english.py` already holds the glossary's *words* to the
pages: every term it retires is checked for, and it re-reads this file rather
than trusting a hand-copy, because a hand-copy drifts. Its numbers had no such
check. A frame size, a crop size, a site count, a sample size: each is written
here in Markdown and defined once in code, and the two were free to disagree.

Same shape as `tests/test_readme.py`, and for the same reason. Each test names
the one definition it checks against, so a failure says which setting moved.
"""

from __future__ import annotations

import csv
import inspect
import os
import re
import statistics

import pytest


@pytest.fixture(scope="session")
def context(core):
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    with open(os.path.join(root, "CONTEXT.md"), encoding="utf-8") as fh:
        return fh.read()


def test_the_frame_size(context, crop_overlap):
    """What a frame is, in pixels. Every share of a frame is worked out from
    these two, so a glossary that names another size makes every percentage on
    every page unreadable."""
    size = f"{crop_overlap.FRAME_W}x{crop_overlap.FRAME_H}"
    assert f"One {size} drone photo" in context, (
        f"crop_overlap.FRAME_W and FRAME_H say a frame is {size}; the glossary "
        f"calls it something else.")


def test_the_centre_crop_and_its_share_of_the_frame(context, crop_overlap, panels):
    """The crop the old path sends to Pl@ntNet, and how little of the frame it
    is. `panels.CROP_SHARE` is the same figure worked out for the page."""
    size = f"{crop_overlap.CROP_SIZE}x{crop_overlap.CROP_SIZE}"
    assert f"The fixed {size} square" in context, (
        f"crop_overlap.CROP_SIZE is {crop_overlap.CROP_SIZE}; the glossary names "
        f"a different centre crop.")
    assert f"{panels.CROP_SHARE} of it" in context, (
        f"panels.CROP_SHARE is {panels.CROP_SHARE} and the glossary says another "
        f"share. Both come from CROP_SIZE over FRAME_W times FRAME_H.")


def test_how_many_sites_the_corpus_has(context, crown, draw_confirmatory):
    """The site count is the reason a range is worked out by drawing whole
    sites, so it is worth having right. Counted the way the code counts it:
    `draw_confirmatory.site_of` applied to the frame list in
    `crown.FRAMES_CSV`, which is what defines the population."""
    with open(crown.FRAMES_CSV, encoding="utf-8") as fh:
        sites = {draw_confirmatory.site_of(row["image_url"])
                 for row in csv.DictReader(fh)}
    sites.discard("")
    assert f"There are {len(sites)};" in context, (
        f"{crown.FRAMES_CSV.name} holds frames from {len(sites)} sites by "
        f"draw_confirmatory.site_of, and the glossary says another number.")


def test_how_many_names_we_ask_plantnet_for(context, core):
    """Our request setting, quoted twice in one row: once in words and once as
    the parameter. `config.yaml` sends it and `core.N_CANDIDATES` scores it."""
    words = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}
    assert f"the {words[core.N_CANDIDATES]} candidates" in context, (
        f"core.N_CANDIDATES is {core.N_CANDIDATES}; the glossary's term for the "
        f"candidate list names another length.")
    assert f"nb-results={core.N_CANDIDATES}" in context, (
        f"the glossary quotes an nb-results that is not core.N_CANDIDATES "
        f"({core.N_CANDIDATES}). The page says the request setting is ours, so "
        f"it has to be the one we send.")


def test_the_range_is_the_confidence_level_the_scorer_uses(context, score_confirmatory):
    """"95%" is not a constant anywhere: it is the z the Wilson interval
    defaults to. Read the default off the signature and turn it back into a
    level, the way `tests/snapshot_harness.py` reads `close`'s tolerance."""
    z = inspect.signature(score_confirmatory.wilson).parameters["z"].default
    level = round(100 * (2 * statistics.NormalDist().cdf(z) - 1))
    assert f"The {level}% interval" in context, (
        f"score_confirmatory.wilson defaults to z={z}, a {level}% interval, and "
        f"the glossary names another level.")
    assert f"we are {level}% sure" in context, (
        f"the wording a page uses has to be the same {level}% the scorer "
        f"computes.")


def test_how_many_times_the_count_is_re_run(context, score_confirmatory):
    """The glossary bans the word bootstrap from a page and prescribes the
    sentence that replaces it. That sentence quotes the draw count."""
    draws = f"{score_confirmatory.BOOTSTRAP_DRAWS:,}"
    assert f"re-ran the count {draws} times" in context, (
        f"score_confirmatory.BOOTSTRAP_DRAWS is {draws} and the sentence the "
        f"glossary prescribes for a page says another number.")


def test_the_frozen_sample_size_and_the_date_it_was_fixed(context, score_confirmatory):
    """The size is countable. The date is not: nothing in the tree stores the
    day. What the tree does have is two prose copies of it, here and on the
    page, plus the month in the file name, so compare those three."""
    with open(score_confirmatory.FROZEN, encoding="utf-8") as fh:
        n = sum(1 for _ in csv.DictReader(fh))
    m = re.search(r"The (\d+) frames fixed on (\d{4}-\d{2})-(\d{2})", context)
    assert m, "the glossary no longer says how big the frozen sample is"
    assert int(m.group(1)) == n, (
        f"{score_confirmatory.FROZEN.name} holds {n} frames and the glossary "
        f"says {m.group(1)}. That count is the sample size behind the headline.")
    assert m.group(2) in score_confirmatory.FROZEN.name, (
        f"the glossary says the sample was fixed in {m.group(2)} and the file "
        f"holding it is called {score_confirmatory.FROZEN.name}.")
    page = os.path.join(os.path.dirname(os.path.abspath(score_confirmatory.__file__)),
                        "confirmatory_panels.py")
    with open(page, encoding="utf-8") as fh:
        assert m.group(0).split(" on ")[1] in fh.read(), (
            "confirmatory_panels.py tells a reader what was knowable on the day "
            "the sample was fixed, and names a different day than the glossary.")


def test_how_many_queues_the_pool_is_sorted_into(context, queues):
    """A queue is one of a fixed set, and the set is a list in one module."""
    words = {3: "three", 4: "four", 5: "five", 6: "six"}
    assert f"One of {words[len(queues.QUEUE_ORDER)]} groups" in context, (
        f"queues.QUEUE_ORDER has {len(queues.QUEUE_ORDER)} queues and the "
        f"glossary says another number: {', '.join(queues.QUEUE_ORDER)}.")


def test_every_status_is_named_in_the_glossary(context, status_words):
    """The glossary spells the statuses out rather than pointing at the module,
    so it carries both the count and all six labels. Commas are dropped from
    both sides: the glossary runs them into one sentence."""
    words = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    n = len(status_words.STATUS)
    assert f"One of {words[n]} plain verdicts" in context, (
        f"status_words.STATUS has {n} statuses and the glossary says another "
        f"number.")
    flat = context.replace(",", "").lower()
    for key, (label, _) in status_words.STATUS.items():
        assert label.replace(",", "").lower() in flat, (
            f"status_words.STATUS[{key!r}] is called {label!r} and the glossary "
            f"lists another wording for it.")
