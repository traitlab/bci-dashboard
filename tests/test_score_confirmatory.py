"""The rules in docs/hypothesis.md, checked against the code that applies them.

The preregistration is only worth something if the scorer implements it
literally. Each test below names the clause it holds the code to, so a later
edit that quietly changes an aggregation rule fails here rather than changing a
published number.

    .venv/bin/pytest tests/test_score_confirmatory.py
"""

import csv


def frame(base, gt, site="a", day="1", **arms):
    row = {"base": base, "gt": gt, "site": site, "day": day,
           "tiles": None, "crown": None, "photo": None,
           "n_crowns": 1, "labelled_area": 0.5, "gt_area": 0.5}
    row.update(arms)
    return row


class TestTilesRanksByShareOfTheFrame:
    def test_top_1_is_the_largest_coverage_not_the_best_score(
            self, score_confirmatory):
        # Ground truth is largest summed area, so the tiles arm has to pool by
        # area too. A confident single tile must not outrank a broad canopy.
        doc = {"results": {"species": [
            {"binomial": "Broad tree", "coverage": 0.6, "max_score": 0.30},
            {"binomial": "Sharp tree", "coverage": 0.1, "max_score": 0.99},
        ]}}
        assert score_confirmatory.rank_tiles(doc) == ["Broad tree", "Sharp tree"]

    def test_a_coverage_tie_breaks_on_the_best_tile_then_alphabetically(
            self, score_confirmatory):
        doc = {"results": {"species": [
            {"binomial": "Zeta", "coverage": 0.4, "max_score": 0.5},
            {"binomial": "Alpha", "coverage": 0.4, "max_score": 0.5},
            {"binomial": "Mid", "coverage": 0.4, "max_score": 0.9},
        ]}}
        assert score_confirmatory.rank_tiles(doc) == ["Mid", "Alpha", "Zeta"]

    def test_a_species_with_no_binomial_is_not_a_candidate(
            self, score_confirmatory):
        doc = {"results": {"species": [
            {"binomial": None, "coverage": 0.9, "max_score": 0.9},
            {"binomial": "Real tree", "coverage": 0.1, "max_score": 0.1},
        ]}}
        assert score_confirmatory.rank_tiles(doc) == ["Real tree"]


class TestCrownsVoteTheirOwnArea:
    def test_one_large_crown_outvotes_several_small_ones(
            self, score_confirmatory):
        # (area, top-1, score). Three small crowns agreeing do not outweigh the
        # tree that actually dominates the frame, because the label does not
        # count crowns either.
        crowns = [(900_000, "Big", 0.4)] + [(100_000, "Small", 0.99)] * 3
        assert score_confirmatory.rank_crowns(crowns)[0] == "Big"

    def test_an_area_tie_breaks_on_the_best_crown_then_alphabetically(
            self, score_confirmatory):
        crowns = [(100, "Zeta", 0.5), (100, "Alpha", 0.5), (100, "Mid", 0.9)]
        assert score_confirmatory.rank_crowns(crowns) == ["Mid", "Alpha", "Zeta"]

    def test_a_crown_the_api_could_not_name_does_not_vote(
            self, score_confirmatory):
        crowns = [(10_000, None, 0.0), (10, "Named", 0.1)]
        assert score_confirmatory.rank_crowns(crowns) == ["Named"]


class TestThePhotoArmIsUnchanged:
    def test_top_1_is_still_the_highest_max_score(self, score_confirmatory):
        doc = {"results": {"species": [
            {"binomial": "Second", "max_score": 0.4},
            {"binomial": "First", "max_score": 0.8},
        ]}}
        assert score_confirmatory.rank_photo(doc)[0] == "First"


class TestTheIntervalsSayWhatTheyClaim:
    def test_the_cluster_bootstrap_is_wider_than_wilson(
            self, score_confirmatory):
        # The whole reason both are printed: 300 frames from 12 sites do not
        # carry 300 frames' worth of information, and Wilson pretends they do.
        # Sites differ from each other, which is the situation clustering
        # exists for: eight sites the model reads well and four it does not.
        rows = [frame(f"f{i}", "X", site=f"s{i % 12}",
                      tiles=["X"] if i % 12 < 8 else ["Y"])
                for i in range(300)]
        w_lo, w_hi = score_confirmatory.wilson(200, 300)
        c_lo, c_hi = score_confirmatory.cluster_bootstrap(
            rows, "site", lambda x: score_confirmatory.accuracy(x, "tiles"),
            draws=400)
        assert (c_hi - c_lo) > (w_hi - w_lo)

    def test_the_bootstrap_is_reproducible_from_its_seed(
            self, score_confirmatory):
        # Twelve graded sites rather than a few extreme ones, so the 2.5 and
        # 97.5 percentiles are not pinned to 0 and 1 whatever the seed does.
        rows = [frame(f"f{i}", "X", site=f"s{i % 12}",
                      tiles=["X"] if (i % 12) > (i // 12) else ["Y"])
                for i in range(144)]

        def acc(sample):
            return score_confirmatory.accuracy(sample, "tiles")

        first = score_confirmatory.cluster_bootstrap(rows, "site", acc, 200, 7)
        again = score_confirmatory.cluster_bootstrap(rows, "site", acc, 200, 7)
        other = score_confirmatory.cluster_bootstrap(rows, "site", acc, 200, 8)
        assert first == again
        assert first != other


class TestTheTest:
    def test_no_discordant_pairs_is_no_evidence(self, score_confirmatory):
        assert score_confirmatory.mcnemar_exact(0, 0) == 1.0

    def test_a_lopsided_split_is_significant_and_a_even_one_is_not(
            self, score_confirmatory):
        assert score_confirmatory.mcnemar_exact(20, 2) < 0.05
        assert score_confirmatory.mcnemar_exact(11, 10) > 0.05

    def test_only_the_pairs_both_arms_answered_are_counted(
            self, score_confirmatory):
        rows = [frame("both", "X", tiles=["X"], crown=["Y"]),
                frame("half", "X", tiles=["X"])]
        pairs, crown_only, tiles_only = score_confirmatory.discordance(
            rows, "crown", "tiles")
        assert (pairs, crown_only, tiles_only) == (1, 0, 1)


class TestTheStoppingRuleHolds:
    def test_a_set_missing_an_aligned_arm_is_stamped_exploratory(
            self, score_confirmatory, capsys, tmp_path):
        rows = [frame("a", "X", crown=["X"], photo=["X"])]
        score_confirmatory.report(rows, {"tiles": ["a"], "crown": [], "photo": []},
                                  complete=False, draws=50)
        assert "EXPLORATORY" in capsys.readouterr().out

    def test_the_adjudication_sheet_is_refused_before_the_set_is_complete(
            self, score_confirmatory, tmp_path, monkeypatch):
        frozen = tmp_path / "frozen.csv"
        frozen.write_text("base_image,site,flight_day,gt_species,n_crowns\n")
        monkeypatch.setattr(score_confirmatory, "canonicaliser", lambda: str)
        monkeypatch.setattr(score_confirmatory, "load_boxes", lambda *a: {})
        monkeypatch.setattr(score_confirmatory, "build_rows",
                            lambda *a: ([frame("a", "X", crown=["X"])],
                                        {"tiles": ["a"], "crown": [], "photo": ["a"]}))
        code = score_confirmatory.main(
            ["--frozen", str(frozen), "--draws", "20",
             "--adjudication", str(tmp_path / "adj.csv")])
        assert code == 1
        assert not (tmp_path / "adj.csv").exists()


class TestTheAdjudicationSheetIsBlind:
    def test_the_arm_names_are_in_the_key_file_and_not_the_sheet(
            self, score_confirmatory, tmp_path):
        rows = [frame(f"f{i}", "X", crown=["X"], tiles=["Y"]) for i in range(20)]
        sheet = tmp_path / "adj.csv"
        assert score_confirmatory.write_adjudication(rows, sheet) == 20

        text = sheet.read_text()
        assert "crown" not in text
        assert "tiles" not in text

        # Blind means both orders actually occur, not that a fixed order was
        # relabelled A and B.
        with open(sheet.with_name("adj_key.csv"), encoding="utf-8") as fh:
            key = list(csv.DictReader(fh))
        assert {r["answer_A_arm"] for r in key} == {"crown", "tiles"}

    def test_frames_the_two_arms_agree_on_are_not_adjudicated(
            self, score_confirmatory, tmp_path):
        rows = [frame("same", "X", crown=["X"], tiles=["X"])]
        assert score_confirmatory.write_adjudication(
            rows, tmp_path / "adj.csv") == 0
