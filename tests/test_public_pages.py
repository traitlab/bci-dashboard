"""Public offline page contracts, run with synthetic inputs on every clone."""

from __future__ import annotations

import csv
import re

import public_snapshot as fixture
import pytest
import test_pages as contracts
from conftest import PAGES, species_rows


@pytest.fixture(scope="module")
def public_snapshot(tmp_path_factory):
    root = fixture.write_inputs(tmp_path_factory.mktemp("public-snapshot"))
    proc = fixture.measure(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return root


@pytest.fixture(scope="module", params=sorted(PAGES))
def synthetic_page(request, public_snapshot):
    script, name, carries, _ = PAGES[request.param]
    proc = fixture.build(public_snapshot, script, name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = (public_snapshot / "pages" / name).read_text(encoding="utf-8")
    return html, proc.stdout, carries


# Reuse the page-shape contracts against both independent input populations.
# The original suite still checks the actual private snapshot when selected.
STRUCTURAL = (
    contracts.test_no_page_shows_interval_notation,
    contracts.test_the_byline_gives_one_readable_date_not_two_unlabelled_ones,
    contracts.test_build_verifies_clean_against_the_snapshot,
    contracts.test_a_page_gates_on_exactly_the_send_queue_it_reports,
    contracts.test_page_has_no_external_asset_references,
    contracts.test_tags_balance,
    contracts.test_a_page_opens_only_the_panels_that_are_its_deliverable,
    contracts.test_every_row_status_has_a_matching_legend_entry,
    contracts.test_the_floor_correction_matches_the_frozen_result_file,
    contracts.test_the_level_the_gap_came_from_stays_off_the_page,
    contracts.test_no_unrendered_template_residue,
    contracts.test_only_the_internal_page_renders_the_queue,
    contracts.test_a_page_styles_every_class_it_renders,
    contracts.test_a_page_counting_the_field_sites_counts_the_ones_the_frame_list_holds,
)


@pytest.mark.parametrize("contract", STRUCTURAL, ids=lambda fn: fn.__name__)
def test_public_page_structure(synthetic_page, contract):
    contract(synthetic_page)


def test_public_page_numbers_have_an_independent_oracle(synthetic_page):
    html, _, carries = synthetic_page
    assert "33 frames scored against the reviewed publication labels" in html
    if "species_status" not in carries:
        assert not species_rows(html)
        assert re.findall(r'<code class="key">([^<]+)</code>', html) == [
            "queued_rare_tele.JPG",
            "queued_low_zoom.JPG",
            "queued_normal_tele.JPG",
        ]
        assert "2 of the queue frames (66.7%)" in html
        assert "1 unlabelled photos got no answer at all" in html
        assert "1 frames are kept out of this queue" in html
        return
    # 22 + 2 + 0 correct over 28 + 4 + 1 reviewed species-level frames.
    # These literals are derived from the observations described in the fixture,
    # never from the implementation's own tables or computed figure namespace.
    expected_headlines = {
        "Top-1 accuracy, per species": "42.9%",
        "Top-1 accuracy, per frame": "72.7%",
        "Top-5 accuracy, per species": "66.7%",
        "Top-5 accuracy, per frame": "97.0%",
    }
    for label, expected in expected_headlines.items():
        values = re.findall(
            rf'<div class="e">{re.escape(label)}</div><div class="row"><div class="v">([^<]+)</div>',
            html,
        )
        assert values == [expected], f"{label}: expected {expected}, got {values}"
    rows = species_rows(html)
    assert len(rows) == 3
    for row, name, n, rate in zip(
        rows, fixture.SPECIES, (28, 4, 1), ("78.6%", "50.0%", "0.0%"), strict=True
    ):
        assert f"<td>{name}</td>" in row
        assert f"<td>{n}</td>" in row
        assert f">{rate}</td>" in row
    assert "right on 69.2% of the 13 test frames" in html
    assert "9 confident disagreements" in html
    assert "9 of 9 frames link to their row in Labelbox" in html


def test_an_incorrect_headline_is_rejected_even_when_other_rates_are_correct(
    synthetic_page,
):
    html, stdout, carries = synthetic_page
    if "species_status" not in carries:
        return
    needle = (
        '<div class="e">Top-1 accuracy, per frame</div>'
        '<div class="row"><div class="v">72.7%</div>'
    )
    assert html.count(needle) == 1
    mutated = html.replace(needle, needle.replace("72.7%", "99.9%"))
    assert (
        "72.7%" in mutated
    )  # Other correct mentions must not mask the wrong headline.
    with pytest.raises(AssertionError):
        test_public_page_numbers_have_an_independent_oracle((mutated, stdout, carries))


def test_linked_tables_travel_with_each_public_page(public_snapshot, synthetic_page):
    html, _, _ = synthetic_page
    linked = set(re.findall(r'href="([\w.-]+\.csv)"', html))
    assert linked
    for name in linked:
        assert (public_snapshot / "pages" / name).read_bytes() == (
            public_snapshot / "tables" / name
        ).read_bytes()


def test_measurement_matches_independent_observation_counts(public_snapshot):
    with (public_snapshot / "tables" / "per_species_health.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert [
        (r["species"], int(r["n_labelled_frames"]), int(r["n_correct_top1"]))
        for r in rows
    ] == [
        ("hura crepitans", 28, 22),
        ("ceiba pentandra", 4, 2),
        ("swartzia simplex", 1, 0),
    ]


@pytest.mark.parametrize(
    "script,name",
    [("build_external.py", "bad-health.html"), ("build_internal.py", "bad-queue.html")],
)
def test_changed_measurement_aborts_the_actual_build(tmp_path, script, name):
    root = fixture.write_inputs(tmp_path)
    measured = fixture.measure(root)
    assert measured.returncode == 0, measured.stdout + measured.stderr
    table = root / "tables" / "per_species_health.csv"
    table.write_text(
        table.read_text(encoding="utf-8").replace("0.7857", "0.1000"), encoding="utf-8"
    )
    proc = fixture.build(root, script, name)
    assert proc.returncode != 0
    assert "VERIFY FAIL" in proc.stderr + proc.stdout
    assert "top1_accuracy for 'hura crepitans'" in proc.stderr + proc.stdout
    assert not (root / "pages" / name).exists()
