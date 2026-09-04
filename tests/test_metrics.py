"""The confusion-matrix rates: precision, recall and F1, per species and per frame.

Three of these tests are gates rather than coverage. Precision, recall and F1
are easy to compute and easy to compute *wrongly*, and each wrong version is a
plausible number that no reader can catch by eye:

  1. Recall averaged over species has to come out equal to the per-species
     top-1 accuracy the page has published since August. They are the same
     quantity under two names, and they are counted here by two different
     routes, so an aggregation that drifts fails rather than quietly shipping
     two headline numbers that ought to agree.
  2. Per frame, precision, recall, F1 and top-1 accuracy are one number.
     Every evaluated frame carries exactly one label and exactly one first
     guess, so a wrong guess is one miss for one species and one false alarm
     for another. If the identity ever breaks, the population changed under
     the page and the sentence explaining it has gone stale.
  3. Per-species F1 is the harmonic mean of that row's own precision and
     recall. Averaging the two rates first and taking one F1 of the averages
     is the classic way this ships wrong: on this corpus it reads two points
     high.

The fourth is a decision, not arithmetic. "top-1" and "top-5" were banned on a
page on 2026-09-01 and brought back on 2026-09-03, and a reversal that nothing
checks is a reversal the next plain-English pass undoes by accident.

    .venv/bin/pytest tests/test_metrics.py
"""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture(scope="module")
def corpus(health):
    """The joined corpus, and the per-species rows built from it.

    Session-scoped loading would be nicer, but `load_health` is the expensive
    call on this repo and only this file needs the records themselves.
    """
    from conftest import require_buildable
    require_buildable()
    h = health.load_health(log=lambda *a, **k: None)
    return h


def _rates(figures, corpus):
    return figures._rates(corpus.sp_recs, corpus.per_species)


# ---------------------------------------------------------------------------
# Gate 1: recall per species is the published per-species top-1 accuracy
# ---------------------------------------------------------------------------

def test_recall_per_species_equals_the_published_per_species_accuracy(
        core, figures, corpus):
    now = _rates(figures, corpus)["now"]
    assert abs(now["macro_recall"] - now["macro_top1"]) < core.RATE_EPS, (
        f"recall averaged over species is {now['macro_recall']!r} and the "
        f"per-species top-1 accuracy is {now['macro_top1']!r}. They are the same "
        f"quantity, so one of the two aggregations is wrong. Fix the "
        f"aggregation, not this test.")


def test_the_two_counts_of_frames_labelled_a_species_agree(health, corpus):
    """`confusion_counts` counts labelled frames again, on purpose.

    `aggregate_per_species` already has that count, and taking it from there
    would make the test above true by construction rather than true. The two
    routes are checked against each other here instead.
    """
    _tp, _guessed, labelled = health.confusion_counts(corpus.sp_recs)
    from_rows = {d["species"]: d["n_labelled_frames"] for d in corpus.per_species}
    assert dict(labelled) == from_rows


# ---------------------------------------------------------------------------
# Gate 2: per frame, the three rates and top-1 accuracy are one number
# ---------------------------------------------------------------------------

def test_every_evaluated_frame_carries_one_label_and_one_first_guess(corpus):
    """The precondition the identity rests on, checked rather than assumed.

    `no-reject=true` means Pl@ntNet never abstains, so there is no frame with a
    label and no guess. If one ever appears, the identity below holds only over
    the guessed subset and the page has to say so with the count.
    """
    assert corpus.sp_recs, "no species-level frames to score"
    assert all(r["ranked"] and r["gt"] for r in corpus.sp_recs)


def test_precision_recall_f1_and_accuracy_are_one_number_per_frame(
        core, figures, corpus):
    now = _rates(figures, corpus)["now"]
    assert abs(now["micro_prf1"] - now["micro_top1"]) < core.RATE_EPS, (
        "per frame, precision, recall, F1 and top-1 accuracy are the same "
        "number. The page prints it once and says why, so a break here means "
        "the sentence beside it is now false.")


def test_the_page_prints_the_per_frame_figure_once_and_says_why(panels):
    """The identity is only safe to print as one card if the page explains it.

    Four identical percentages under four headings read as four findings.
    """
    src = pathlib.Path(panels.__file__).read_text(encoding="utf-8")
    assert "one botanist label and one first guess" in src
    assert "all three are the same number" in src


# ---------------------------------------------------------------------------
# Gate 3: per-species F1 is the harmonic mean of that row's own two rates
# ---------------------------------------------------------------------------

def test_per_species_f1_is_the_harmonic_mean_of_that_rows_own_rates(core, corpus):
    """Checked on the ten species carrying the most labelled frames.

    The heaviest rows are the ones a reader looks at, and they are the rows
    where precision and recall differ enough that the wrong formula would not
    happen to land on the right answer.
    """
    heaviest = sorted(corpus.per_species, key=lambda d: -d["n_labelled_frames"])[:10]
    assert len(heaviest) == 10
    for d in heaviest:
        p, r = d["precision"], d["recall"]
        want = 0.0 if not (p + r) else 2 * p * r / (p + r)
        assert abs(d["f1"] - want) < core.RATE_EPS, (
            f'{d["species"]}: F1 is {d["f1"]!r}, the harmonic mean of its own '
            f"precision {p!r} and recall {r!r} is {want!r}")


def test_f1_per_species_is_the_average_of_the_rows_not_the_f1_of_the_averages(
        core, figures, corpus):
    """The single most common way this metric ships wrong.

    On this corpus the wrong formula reads about two points high, which is
    exactly the size of error nobody catches by eye.
    """
    now = _rates(figures, corpus)["now"]
    rows = [d["f1"] for d in corpus.per_species]
    assert abs(now["macro_f1"] - sum(rows) / len(rows)) < core.RATE_EPS

    p, r = now["macro_precision"], now["macro_recall"]
    f1_of_the_averages = 2 * p * r / (p + r)
    assert abs(now["macro_f1"] - f1_of_the_averages) > core.RATE_EPS, (
        "the averaged F1 and the F1 of the two averages have come out equal. "
        "Either the corpus has changed shape or macro_f1 is being computed the "
        "wrong way round.")


# ---------------------------------------------------------------------------
# Precision's own denominator, and what it is and is not measured over
# ---------------------------------------------------------------------------

def test_precision_divides_by_frames_guessed_not_frames_labelled(health, corpus):
    tp, guessed, _labelled = health.confusion_counts(corpus.sp_recs)
    for d in corpus.per_species:
        sp = d["species"]
        assert d["n_guessed_frames"] == guessed[sp]
        want = (tp[sp] / guessed[sp]) if guessed[sp] else 0.0
        assert d["precision"] == want


def test_a_species_the_model_never_guesses_scores_zero_not_a_blank(corpus):
    """Reading an empty guess list as perfect precision would flatter the average.

    Every per-species row is averaged, so `None` here would either crash the
    average or quietly shrink its denominator.
    """
    never = [d for d in corpus.per_species if d["n_guessed_frames"] == 0]
    for d in never:
        assert d["precision"] == 0.0 and d["f1"] == 0.0


def test_the_page_says_precision_is_measured_on_the_frames_we_scored(panels):
    src = pathlib.Path(panels.__file__).read_text(encoding="utf-8")
    assert "not over the survey" in src


# ---------------------------------------------------------------------------
# The confidence distribution, which was a mean and nothing else
# ---------------------------------------------------------------------------

def test_a_single_frame_species_reports_its_one_value_rather_than_raising(health):
    """The commonest row in the species table carries one labelled frame.

    `statistics.quantiles` raises on one data point, so this is the case that
    would take the build down rather than the rare one.
    """
    assert health.confidence_spread([0.42]) == {
        "mean": 0.42, "median": 0.42, "p25": 0.42, "p75": 0.42, "iqr": 0.0}


def test_no_frames_is_no_confidence_rather_than_a_confidence_of_zero(health):
    assert all(v is None for v in health.confidence_spread([]).values())


def test_every_species_row_carries_the_spread_and_not_just_the_mean(corpus):
    keys = ("mean_top1_confidence", "median_top1_confidence", "p25_top1_confidence",
            "p75_top1_confidence", "iqr_top1_confidence",
            "mean_top1_confidence_when_correct")
    for d in corpus.per_species:
        for k in keys:
            assert k in d, f'{d["species"]} has no {k}'
        assert d["p25_top1_confidence"] <= d["median_top1_confidence"]
        assert d["median_top1_confidence"] <= d["p75_top1_confidence"]


# ---------------------------------------------------------------------------
# The naming reversal, which is a decision and so has to be written down
# ---------------------------------------------------------------------------

def test_the_page_names_the_metric_as_well_as_glossing_it(external_page):
    """The reviewer asked for the metric's own name back on the 2026-09-03 call.

    The plain-English sentence stayed underneath as the gloss, so this asserts
    both halves: a page that only names the metric has lost the botanist, and
    one that only glosses it makes a PI translate in their head.
    """
    html, _ = external_page
    assert "Top-1 accuracy" in html
    assert "The first guess is right" in html


def test_the_species_table_names_recall_in_the_column_that_holds_it(external_page):
    """Per species, recall and top-1 accuracy are one number (gate 1 above).

    The page said so in a paragraph above the table, and a reader scanning the
    column headings still found Precision and F1 with no recall and read it as a
    missing column. Both names are in the heading, so the identity is where the
    columns are.
    """
    html, _ = external_page
    assert "<th class=\"num sortable\">Top-1 accuracy (recall)</th>" in html


def test_context_md_no_longer_bans_the_metric_names():
    """CONTEXT.md is the source of record for what a page may say.

    It is gitignored, so it lives only in a working checkout and this test
    skips where it is absent. That is also why the reversal is recorded in
    `tests/test_plain_english.py` as well: that file is tracked.
    """
    from conftest import REPO

    path = REPO / "CONTEXT.md"
    if not path.exists():
        pytest.skip("CONTEXT.md not present (it is gitignored)")
    text = path.read_text(encoding="utf-8")
    assert 'Never "top-1" on a page' not in text
    assert 'Never "top-5" on a page' not in text
    assert "**top-1 accuracy**" in text


def test_the_plain_english_check_no_longer_retires_the_metric_names():
    from conftest import REPO

    text = (REPO / "tests" / "test_plain_english.py").read_text(encoding="utf-8")
    assert r'r"\btop-?1\b":' not in text
    assert r'r"\btop-?5\b":' not in text
