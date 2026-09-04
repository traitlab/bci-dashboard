"""The field sample has to redraw, or it is a sample chosen afterwards.

Every number on the model-health page today is read off frames a botanist chose
to label. This set is the one population that is not: it was drawn at random
from the unlabelled pool before the next round shipped. The only thing that
makes that claim checkable later is that the committed list reproduces from its
seed and its committed pool, so the reproduction is a test rather than a habit.

Nothing here reaches Labelbox. The pool manifest is committed, and the draw is
arithmetic over it.

    .venv/bin/pytest tests/test_field_sample_draw.py
"""

from __future__ import annotations

import collections
import csv
import hashlib
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FIELD = REPO / "input" / "field_sample_2026-09.csv"
POOL = REPO / "input" / "field_sample_pool_2026-09.csv"
SHA256 = "8f181c7dcc5e990c3d07c0e9d7fccf3815648a25f3480580b018865dfc94fbf0"


def rows_of(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def a_pool(n=1000, sites=8):
    return [{"global_key": f"comb_DJI_{i:05d}.JPG", "site": f"s{i % sites}",
             "queue": "long_tail", "predicted_species": "x",
             "confidence": "0.1"} for i in range(n)]


class TestTheDrawIsReproducible:
    def test_the_same_seed_draws_the_same_frames(self, draw_field_sample):
        first, _ = draw_field_sample.draw(a_pool(), n=50, seed=1)
        second, _ = draw_field_sample.draw(a_pool(), n=50, seed=1)
        other, _ = draw_field_sample.draw(a_pool(), n=50, seed=2)
        keys = [r["global_key"] for r in first]
        assert keys == [r["global_key"] for r in second]
        assert keys != [r["global_key"] for r in other]

    def test_frames_come_back_sorted_unique_and_only_in_the_declared_columns(
            self, draw_field_sample):
        """`base_image` is aliased in to reuse the confirmatory draw. It is not a
        column of this set, and a leaked alias would put a second name for the
        same frame in a committed file."""
        rows, _ = draw_field_sample.draw(a_pool(), n=30, seed=7)
        keys = [r["global_key"] for r in rows]
        assert keys == sorted(keys)
        assert len(set(keys)) == 30
        assert all(set(r) == set(draw_field_sample.FIELDS) for r in rows)

    def test_no_site_may_carry_more_than_the_cap(self, draw_field_sample):
        pool = a_pool(2000, sites=5)          # every site well over a quarter
        _, quota = draw_field_sample.draw(pool, n=100, seed=3, cap=0.25)
        assert max(quota.values()) <= 25


class TestThePoolIsTheFramesThatCanActuallyBeLabelledNext:
    def test_a_frame_already_spoken_for_by_another_evaluation_is_left_out(
            self, draw_field_sample, tmp_path):
        """A frame carrying a split is held out of sends, so it cannot be
        labelled next round and must not be drawn into this set as well."""
        queue = tmp_path / "queue.csv"
        queue.write_text(
            "queue,global_key,split,predicted_species,confidence\n"
            "long_tail,keep.JPG,,a,0.1\n"
            "long_tail,taken.JPG,confirmatory,b,0.2\n", encoding="utf-8")
        inventory = tmp_path / "rows.jsonl"
        inventory.write_text(
            '{"global_key":"keep.JPG","row_data":"http://x/20240912_bciarmour_1_v/a.JPG"}\n'
            '{"global_key":"taken.JPG","row_data":"http://x/20240912_bciarmour_1_v/b.JPG"}\n',
            encoding="utf-8")
        pool = draw_field_sample.eligible(queue, inventory)
        assert [r["global_key"] for r in pool] == ["keep.JPG"]

    def test_a_frame_with_no_readable_site_stops_the_draw(
            self, draw_field_sample, tmp_path):
        """The draw is stratified by site. A frame with no site would be drawn
        under a stratum name that means "we did not look", so an unreadable
        inventory is a stop and not a quiet empty stratum."""
        queue = tmp_path / "queue.csv"
        queue.write_text(
            "queue,global_key,split,predicted_species,confidence\n"
            "long_tail,orphan.JPG,,a,0.1\n", encoding="utf-8")
        inventory = tmp_path / "rows.jsonl"
        inventory.write_text(
            '{"global_key":"orphan.JPG","row_data":"http://x/no-mission-folder.JPG"}\n',
            encoding="utf-8")
        with pytest.raises(SystemExit, match="no readable site"):
            draw_field_sample.eligible(queue, inventory)


class TestTheCommittedListIsTheOneThatWasDrawn:
    def test_the_file_matches_the_recorded_sha256(self, draw_field_sample):
        if not FIELD.exists():
            pytest.skip("the drawn list is not present")
        assert hashlib.sha256(FIELD.read_bytes()).hexdigest() == SHA256

    def test_the_committed_list_redraws_from_the_committed_pool(
            self, draw_field_sample):
        """What `--verify` proves, proven in the suite as well: the pair on disk
        is what the seed produces, not a list edited afterwards."""
        if not (FIELD.exists() and POOL.exists()):
            pytest.skip("the pool and the drawn list are not both present")
        rows, _ = draw_field_sample.draw(draw_field_sample.read_pool(POOL))
        assert draw_field_sample.to_csv_text(rows) == FIELD.read_text(encoding="utf-8")

    def test_every_drawn_frame_came_out_of_the_committed_pool(self, draw_field_sample):
        if not (FIELD.exists() and POOL.exists()):
            pytest.skip("the pool and the drawn list are not both present")
        pool = {r["global_key"] for r in rows_of(POOL)}
        drawn = [r["global_key"] for r in rows_of(FIELD)]
        assert len(drawn) == draw_field_sample.N
        assert set(drawn) <= pool

    def test_the_size_the_docstring_claims_is_the_size_of_the_pool(
            self, draw_field_sample):
        """The docstring says the set is 7.7% of 3,875 queue frames. That share
        is the argument for the size being worth a botanist's month, and the
        confirmatory draw has already had one such sentence go stale against its
        own manifest. The manifest is committed, so the sentence can be
        counted."""
        import re
        if not POOL.exists():
            pytest.skip("the pool manifest is not present")
        pool = rows_of(POOL)
        module = pathlib.Path(draw_field_sample.__file__).read_text(encoding="utf-8")
        m = re.search(r"([\d.]+)% of the\n# ([\d,]+) frames in the queue", module)
        assert m, "the module no longer says how big a share of the queue this is"
        assert int(m.group(2).replace(",", "")) == len(pool)
        assert float(m.group(1)) == round(100 * draw_field_sample.N / len(pool), 1)

    def test_no_site_carries_more_than_the_cap_in_the_committed_list(
            self, draw_field_sample):
        if not FIELD.exists():
            pytest.skip("the drawn list is not present")
        counts = collections.Counter(r["site"] for r in rows_of(FIELD))
        assert max(counts.values()) <= draw_field_sample.CAP * draw_field_sample.N
