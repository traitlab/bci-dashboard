"""The landing page GitHub Pages serves.

The reviewer asked for one bookmarkable address rather than a file someone has to be
sent each time. A bookmark that lands on a directory listing is not that, and a
bookmark whose dates were typed by hand goes stale without anyone noticing.
"""
import pytest


@pytest.fixture()
def build_index():
    from conftest import REPO, load
    return load("_build_index_under_test", REPO / "dashboard" / "build_index.py")


def fake_build(tmp_path, subtitle="built 2026-09-04 &middot; snapshot 2026-08-27"):
    for name, _, _ in [(n, t, b) for n, t, b in _PAGES]:
        (tmp_path / name).write_text(
            f'<html><body><h1>x</h1><div class="subtitle">{subtitle}</div></body></html>',
            encoding="utf-8")
    return str(tmp_path)


_PAGES = [("model_health_dashboard.html", "", ""),
          ("label_queue_dashboard.html", "", "")]


def test_it_links_both_dashboards(build_index, tmp_path):
    out = build_index.build(fake_build(tmp_path))
    assert 'href="model_health_dashboard.html"' in out
    assert 'href="label_queue_dashboard.html"' in out


def test_it_names_every_page_it_ships(build_index):
    """A page added to the build without a card here is a page nobody can reach
    from the address that was bookmarked."""
    assert {n for n, _, _ in build_index.PAGES} == {
        "model_health_dashboard.html", "label_queue_dashboard.html"}


def test_the_date_is_read_off_the_pages_not_typed(build_index, tmp_path):
    """A rebuild moves the pages' own subtitle, so it moves this one too."""
    out = build_index.build(fake_build(tmp_path, "built 2027-01-01 &middot; snapshot 2026-12-31"))
    assert "built 2027-01-01" in out
    assert "2026-09" not in out


def test_only_the_build_date_crosses_over(build_index, tmp_path):
    """The pages' subtitle carries the snapshot date, the model tag and two
    counts. Each is a number with no provenance beside it here, and the page
    that can explain it is one click away, so none of them comes across."""
    out = build_index.build(fake_build(
        tmp_path, "built 2027-01-01 &middot; snapshot 2026-12-31 &middot; "
                  "Pl@ntNet model unknown &middot; 3,277 labelled frames &middot; "
                  "186 species"))
    assert "built 2027-01-01" in out
    for carried in ("snapshot", "Pl@ntNet model", "3,277", "186 species"):
        assert carried not in out, carried


def test_the_separator_never_reaches_the_reader_as_text(build_index, tmp_path):
    """It did. The subtitle was escaped a second time on the way in, and the
    front door read `built 2026-09-04 &middot; snapshot ...` literally."""
    out = build_index.build(fake_build(tmp_path))
    assert "middot" not in out
    assert "&amp;" not in out


def test_a_page_that_carries_no_subtitle_is_not_a_crash(build_index, tmp_path):
    """The index is a signpost. It must not be the thing that fails a publish."""
    for name, _, _ in build_index.PAGES:
        (tmp_path / name).write_text("<html><body>nothing</body></html>", encoding="utf-8")
    out = build_index.build(str(tmp_path))
    assert 'href="model_health_dashboard.html"' in out


def test_a_missing_page_stops_the_publish(build_index, tmp_path):
    """Better a failed publish than a live site with a dead link on it."""
    (tmp_path / "model_health_dashboard.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(OSError):
        build_index.build(str(tmp_path))


def test_it_claims_nothing_the_pages_have_to_back_up(build_index, tmp_path):
    """A signpost carries two links and a date. It used to carry a paragraph
    about the rebuild as well, which said nothing a reader could act on and
    described the pages instead of pointing at them."""
    out = build_index.build(fake_build(tmp_path)).lower()
    assert "over time" not in out
    assert "measurement pass" not in out
    assert "latest state" not in out
    assert "<p" not in out
