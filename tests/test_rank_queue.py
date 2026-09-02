"""The ranker that decides which photo in a queue is sent first.

`labelling/rank_queue.py` needs numpy and labelfirst, which live in the
speciesfirst virtualenv and not in this one, so the behaviour tests skip on a
plain checkout and the contract tests, which only read source text, always run.

    .venv/bin/pytest tests/test_rank_queue.py
    "$SPECIESFIRST/.venv/bin/pytest" tests/test_rank_queue.py
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


def _source(*parts: str) -> str:
    return REPO.joinpath(*parts).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# contracts, read off the source: these run everywhere
# ---------------------------------------------------------------------------

def test_the_backtest_reads_the_column_the_label_writers_write():
    """The command in rank_queue.py's own header has to run as printed. The
    same slip that made rank_unsent.py's documented backtest exit on a missing
    column."""
    default = re.search(r'"--species-col", default="(\w+)"',
                        _source("labelling", "rank_queue.py")).group(1)
    written = re.search(r'writerow\(\["global_key", "(\w+)"\]\)',
                        _source("labelling", "gt_from_export.py")).group(1)
    assert default == written, (
        f"rank_queue.py reads {default!r} and gt_from_export.py writes "
        f"{written!r}, so --species-csv on the merged labels stops the run.")


def test_the_file_it_writes_carries_the_column_the_queue_reads():
    """`dashboard/queues.load_novelty` looks up two column names by hand. A
    renamed column there would leave every frame unranked and nothing would
    fail, since an unreadable file is a supported state."""
    header = re.search(r'w\.writerow\(\["global_key", "novelty_rank".*?\]\)',
                       _source("labelling", "rank_queue.py"), re.DOTALL)
    assert header, "rank_queue.py no longer writes global_key and novelty_rank first"
    reader = _source("dashboard", "queues.py")
    assert 'row.get("global_key"), row.get("novelty_rank")' in reader


def test_the_two_cameras_are_named_the_same_way_on_both_sides():
    """The ranker prints the camera mix at the head of the queue and the page
    counts the cameras of the queue. Two spellings would make those two numbers
    look like a disagreement about the data."""
    pattern = r'for c in \("zoom", "tele"\):'
    for module in (("labelling", "rank_queue.py"), ("dashboard", "figures.py")):
        assert re.search(pattern, _source(*module)), f"{module[1]} names other cameras"


def test_the_curve_files_carry_the_columns_the_page_reads():
    """`figures._read_curve` asks for its columns by name and raises when one is
    missing, so a rename here is a build failure, not a silent empty chart. This
    catches it in the file that writes them instead."""
    writer = _source("labelling", "rank_queue.py")
    reader = _source("dashboard", "figures.py")
    for header in (r'\["photos_named", "species_directed", "species_random"\]',
                   r'\["novelty_rank", "mean_distance_to_nearest_labelled"'):
        assert re.search(header, writer), f"rank_queue.py no longer writes {header}"
    assert '("photos_named", "species_directed", "species_random")' in reader
    assert '"novelty_rank", "mean_distance_to_nearest_labelled"' in reader


def test_the_head_of_the_queue_is_the_same_slice_on_both_sides():
    """The ranker prints the camera mix of the head and the page publishes it.
    Two different shares would be two different claims about the same photos."""
    ranker = re.search(r"TOP_DECILE = ([\d.]+)", _source("labelling", "rank_queue.py"))
    page = re.search(r"QUEUE_HEAD_SHARE = ([\d.]+)", _source("dashboard", "core.py"))
    assert ranker and page, "one side no longer names the share it calls the head"
    assert float(ranker.group(1)) == float(page.group(1)), (
        f"the ranker calls the first {ranker.group(1)} of the queue its head and "
        f"the page calls it {page.group(1)}.")


def test_the_page_reads_thumbnails_from_where_the_fetcher_writes_them():
    """The fetcher puts a size directory under the thumbnail root; the page
    builds the same path from the same two constants. A mismatch shows up as a
    panel with no pictures and nothing else."""
    fetcher = _source("labelling", "fetch_thumbs.py")
    core = _source("dashboard", "core.py")
    assert 'args.out_dir / str(args.size)' in fetcher
    assert 'os.path.join(BASE, "thumbs", str(THUMB_PX))' in core
    assert re.search(r'"--size", type=int, default=112', fetcher), (
        "the fetcher's default size no longer matches core.THUMB_PX")
    assert "THUMB_PX = 112" in core


# ---------------------------------------------------------------------------
# behaviour, on the speciesfirst interpreter
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rank_queue():
    pytest.importorskip("numpy", reason="numpy is not in this virtualenv")
    pytest.importorskip("labelfirst", reason="labelfirst is not in this virtualenv")
    from conftest import load
    return load("_rank_queue_under_test", REPO / "labelling" / "rank_queue.py")


def _pool(np):
    """Three photos on a circle. `anchors` sits on one of them, so the far side
    is unambiguously the least like anything labelled."""
    anchors = np.array([[1.0, 0.0]])
    pool = np.array([[1.0, 0.05],   # near the labelled photo
                     [-1.0, 0.0],   # the opposite side
                     [0.0, 1.0]])   # a right angle away
    return anchors, pool


def test_the_photo_furthest_from_every_labelled_one_is_ranked_first(rank_queue):
    import numpy as np

    anchors, pool = _pool(np)
    order, distance = rank_queue.rank_pool(anchors, pool)
    assert order[0] == 1
    assert distance[1] > distance[2] > distance[0]


def test_the_order_is_every_photo_once(rank_queue):
    import numpy as np

    rng = np.random.default_rng(0)
    order, distance = rank_queue.rank_pool(rng.normal(size=(5, 8)), rng.normal(size=(11, 8)))
    assert sorted(order) == list(range(11))
    assert distance.shape == (11,)


def test_two_runs_give_the_same_order(rank_queue):
    """There is no seed in play while the labelled set is not empty, and the
    queue is rebuilt on every refresh, so an order that moved on its own would
    reorder the page for no reason a reader could see."""
    import numpy as np

    rng = np.random.default_rng(1)
    anchors, pool = rng.normal(size=(4, 6)), rng.normal(size=(9, 6))
    assert rank_queue.rank_pool(anchors, pool)[0] == rank_queue.rank_pool(anchors, pool)[0]


def test_a_vector_of_all_zeros_stops_the_run(rank_queue):
    """It has no direction, so its distance to everything is the same number,
    and it would take a place in the queue that means nothing."""
    import numpy as np

    with pytest.raises(SystemExit):
        rank_queue.rank_pool(np.array([[1.0, 0.0]]), np.array([[0.0, 0.0]]))


def test_the_distance_is_to_the_labelled_set_and_not_to_the_picks_before_it(rank_queue):
    """The column is named "distance to the nearest labelled photo". The greedy
    order shrinks its own working distance as it goes, so reporting that number
    under this name would report a different quantity."""
    import numpy as np

    anchors = np.array([[1.0, 0.0]])
    pool = np.array([[-1.0, 0.0], [-1.0, 0.001]])
    _, distance = rank_queue.rank_pool(anchors, pool)
    assert distance[0] == pytest.approx(distance[1], abs=1e-5)
    assert distance[0] == pytest.approx(2.0, abs=1e-5)


def test_the_thinned_curve_keeps_the_points_the_page_prints_a_number_for(rank_queue):
    """The page names the photo count where each line crosses half the species.
    Read off an evenly thinned curve that lands on the next sampled photo, so
    the crossing is kept as an exact point and the page and the report agree."""
    idx = rank_queue.sample_curve(list(range(1000)), points=10, keep=[128, 328])
    assert 128 in idx and 328 in idx
    assert idx[-1] == 999, "the total is the number a reader checks last"
    assert idx == sorted(set(idx))


def test_a_curve_shorter_than_the_sample_is_kept_whole(rank_queue):
    assert rank_queue.sample_curve([1, 2, 3], points=10) == [0, 1, 2]


def test_the_distance_curve_averages_its_bins_rather_than_sampling_them(rank_queue):
    """Distance falls with rank but is noisy frame to frame. Sampling would draw
    that noise as the trend; the mean of a slice is the trend."""
    values = [1.0, 0.0] * 50  # every bin has the same mean and no sampled point does
    bins = rank_queue.bin_means(values, points=5)
    assert [n for _, _, n in bins] == [20] * 5
    assert all(mean == pytest.approx(0.5) for _, mean, _ in bins)
    assert [rank for rank, _, _ in bins] == [20, 40, 60, 80, 100]


def test_an_empty_pool_has_no_distance_curve(rank_queue):
    assert rank_queue.bin_means([]) == []
