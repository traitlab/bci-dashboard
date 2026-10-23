"""The landing page GitHub Pages serves.

The reviewer asked for one bookmarkable address rather than a file someone has to be
sent each time. A bookmark that lands on a directory listing is not that, and a
bookmark whose dates were typed by hand goes stale without anyone noticing.
"""
import re

import pytest


@pytest.fixture()
def build_index():
    from conftest import REPO, load
    return load("_build_index_under_test", REPO / "dashboard" / "build_index.py")


def fake_build(tmp_path, subtitle="built 2026-09-04 &middot; snapshot 2026-08-27"):
    for name in _PAGES:
        (tmp_path / name).write_text(
            f'<html><body><h1>x</h1><div class="subtitle">{subtitle}</div></body></html>',
            encoding="utf-8")
    return str(tmp_path)


_PAGES = ["model_health_dashboard.html", "label_queue_dashboard.html"]


def test_it_links_every_dashboard(build_index, tmp_path):
    out = build_index.build(fake_build(tmp_path))
    for name in _PAGES:
        assert f'href="{name}"' in out


def test_two_tiles_and_no_team_card(build_index, tmp_path):
    """Two tiles, one audience. The labelling team's commands are a closed
    block on the queue page, so the old team copy gets no card of its own: its
    address only redirects to that block."""
    out = build_index.build(fake_build(tmp_path))
    assert out.count('class="card"') == 2
    assert out.index('class="card" href="label_queue_dashboard.html"') < out.index('class="card" href="model_health_dashboard.html"')
    assert "label_queue_team.html" not in out
    assert "<em>" not in out


def test_it_names_every_page_it_ships(build_index):
    """A page added to the build without a card here is a page nobody can reach
    from the address that was bookmarked."""
    assert {card[0] for card in build_index.PAGES} == set(_PAGES)


def test_the_date_is_read_off_the_pages_not_typed(build_index, tmp_path):
    """A rebuild moves the pages' own subtitle, so it moves this one too."""
    out = build_index.build(fake_build(tmp_path, "built 2027-01-01 &middot; snapshot 2026-12-31"))
    assert "built 2027-01-01" in out
    assert "2026-09" not in out


def test_build_and_label_dates_stay_distinct_without_evaluation_figures(build_index, tmp_path):
    """A fresh interface must not make an old label snapshot appear current."""
    out = build_index.build(fake_build(
        tmp_path, "built 2027-01-01 &middot; snapshot 2026-12-31 &middot; "
                  "Pl@ntNet model unknown &middot; 3,277 labelled frames &middot; "
                  "186 species"))
    assert "built 2027-01-01" in out
    assert "snapshot 2026-12-31" in out
    for carried in ("Pl@ntNet model unknown", "3,277", "186 species"):
        assert carried not in out, carried


def test_the_separator_never_reaches_the_reader_as_text(build_index, tmp_path):
    """It did. The subtitle was escaped a second time on the way in, and the
    front door read `built 2026-09-04 &middot; snapshot ...` literally."""
    out = build_index.build(fake_build(tmp_path))
    assert "middot" not in out
    assert "&amp;" not in out


def test_a_page_that_carries_no_subtitle_is_not_a_crash(build_index, tmp_path):
    """The index is a signpost. It must not be the thing that fails a publish."""
    for card in build_index.PAGES:
        name = card[0]
        (tmp_path / name).write_text("<html><body>nothing</body></html>", encoding="utf-8")
    out = build_index.build(str(tmp_path))
    assert 'href="model_health_dashboard.html"' in out


def test_a_missing_page_stops_the_publish(build_index, tmp_path):
    """Better a failed publish than a live site with a dead link on it."""
    (tmp_path / "model_health_dashboard.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(OSError):
        build_index.build(str(tmp_path))


def test_it_claims_nothing_the_pages_have_to_back_up(build_index, tmp_path):
    """A signpost carries two links and a date, and no prose describing the
    pages instead of pointing at them."""
    out = build_index.build(fake_build(tmp_path)).lower()
    assert "over time" not in out
    assert "measurement pass" not in out
    assert "latest state" not in out
    assert 'class="intro"' in out
    assert "tree abundance" not in out, "caveats live on the About page"


def test_optional_atlas_links_only_when_built(build_index, tmp_path):
    fake_build(tmp_path)
    out = build_index.build(str(tmp_path))
    assert 'href="embedding-atlas.html' not in out
    (tmp_path / 'embedding-atlas.html').write_text('<html>Atlas</html>')
    out = build_index.build(str(tmp_path))
    assert 'href="embedding-atlas.html#view=photos"' in out
    assert 'href="embedding-atlas.html#view=locations"' in out
    (tmp_path / 'crownfirst-atlas.html').write_text('<html>Canopy</html>')
    assert 'href="crownfirst' not in build_index.build(str(tmp_path)), "the experiment is linked from About only"


def test_taxonomy_explorer_is_first_when_built(build_index, tmp_path):
    fake_build(tmp_path)
    (tmp_path / "explorer.html").write_text("<html>Photos</html>")
    (tmp_path / "embedding-atlas.html").write_text("<html>Research</html>")
    out = build_index.build(str(tmp_path))
    assert out.index('class="card" href="explorer.html"') < out.index('class="card" href="label_queue_dashboard.html"')
    assert out.index('class="card" href="label_queue_dashboard.html"') < out.index('class="card" href="model_health_dashboard.html"')
    assert out.index('class="card" href="model_health_dashboard.html"') < out.index('<a href="embedding-atlas.html#view=photos">')
    assert "<details" not in out, "tasks must be visible without opening a disclosure"


def test_one_shared_stamp_is_shown_once_under_the_grid(build_index, tmp_path):
    out = build_index.build(fake_build(tmp_path))
    assert out.count("built 2026-09-04") == 1
    assert '<p class="scope">built 2026-09-04. snapshot 2026-08-27</p>' in out
    assert "<small>" not in out


def test_dates_stay_with_the_page_they_describe(build_index, tmp_path):
    fake_build(tmp_path)
    (tmp_path / "label_queue_dashboard.html").write_text(
        '<div class="subtitle">labels as of 2026-10-15 &middot; model unknown</div>')
    out = build_index.build(str(tmp_path))
    assert '<small>built 2026-09-04. snapshot 2026-08-27</small></a>' in out
    assert '<small>labels as of 2026-10-15</small></a>' in out
    assert 'class="subtitle"' not in out


def test_home_exposes_camera_locations_and_landmarks(build_index, tmp_path):
    fake_build(tmp_path)
    (tmp_path / "embedding-atlas.html").write_text("<html>Canopy</html>")
    out = build_index.build(str(tmp_path))
    assert 'href="embedding-atlas.html#view=locations"' in out
    assert 'href="index.html" aria-current="page"' in out
    assert 'href="#main-content">Skip to content</a>' in out
    assert '<main id="main-content" tabindex="-1">' in out
    assert 'href="explorer.html"' not in out
    assert 'class="card" href="embedding-atlas.html' not in out, "the map is a plain link, not a tile"


def test_experiment_only_build_keeps_research_access_on_about_without_ordinary_map(build_index, tmp_path):
    fake_build(tmp_path)
    (tmp_path / "crownfirst-atlas.html").write_text("<html>Experiment</html>")
    out = build_index.build(str(tmp_path))
    assert 'href="crownfirst-atlas.html' not in out
    assert "embedding-atlas.html" not in out
    assert 'id="cameraMapTask"' not in out
    about = build_index.build_about(build_index.available_names(str(tmp_path)))
    assert 'href="crownfirst-atlas.html#view=models"' in about
    assert "embedding-atlas.html" not in about


def test_refreshed_measurement_keeps_the_older_label_date(build_index, tmp_path):
    out = build_index.build(fake_build(
        tmp_path, "refreshed 2026-10-16 &middot; labels as of 2026-08-27 &middot; "
                  "Pl@ntNet model unknown &middot; 2,554 frames scored"))
    assert "refreshed 2026-10-16. labels as of 2026-08-27" in out
    assert "2,554 frames" not in out


def test_plantnet_map_and_similar_photos_are_plain_links_after_the_tiles(build_index, tmp_path):
    fake_build(tmp_path)
    for name in ("embedding-atlas.html", "crownfirst-atlas.html"):
        (tmp_path / name).write_text("<html>Recorded atlas</html>")
    out = build_index.build(str(tmp_path))
    row = out[out.index('<p class="more">'):out.index('<p class="scope">')]
    assert 'href="embedding-atlas.html#view=locations">Drone map' in row
    assert 'href="embedding-atlas.html#view=photos">Similar photos' in row
    assert out.index('class="tasks"') < out.index('<p class="more">')


def queue_build(tmp_path, tile='3,875 unlabelled photos'):
    fake_build(tmp_path)
    (tmp_path / "label_queue_dashboard.html").write_text(
        f'<div class="subtitle">Labelbox labels merged 2026-10-15 &middot; x</div>'
        f'<div class="hero wide" data-tile="{tile}"><div>Queued 9</div></div>')


def test_queue_figure_is_read_off_the_page_and_sits_with_its_dates(build_index, tmp_path):
    queue_build(tmp_path)
    out = build_index.build(str(tmp_path))
    queue_tile = out[out.index('<a class="card" href="label_queue_dashboard.html"'):].split("</a>")[0]
    assert "3,875 unlabelled photos" in queue_tile
    assert "Labelbox labels merged 2026-10-15" in queue_tile
    assert out.count("unlabelled photos") == 1, "only the queue tile carries a figure"


def test_queue_hero_names_its_figure_for_the_index():
    from conftest import load, REPO
    assets = load("_assets_tile", REPO / "dashboard" / "assets.py")
    card = ("Queued", "3,875", "unlabelled photos", "note")
    assert 'class="hero wide" data-tile="3,875 unlabelled photos"' in assets.hero([card], cls="wide", tile="3,875 unlabelled photos")
    assert "data-tile" not in assets.hero([card])


def test_about_carries_caveats_glossary_and_no_data(build_index, tmp_path):
    fake_build(tmp_path)
    (tmp_path / "explorer.html").write_text("<html>Photos</html>")
    about = build_index.build_about(build_index.available_names(str(tmp_path)))
    low = about.lower()
    assert "photo counts do not measure tree abundance" in low
    assert "model guesses need expert confirmation" in low
    assert "each page describes its own snapshot" in low
    for term in ("Recorded label", "Pl@ntNet first guess", "Labelled frame"):
        assert f"<dt>{term}</dt>" in about
    assert "crownfirst" not in about
    assert 'href="explorer.html"' in about
    assert not re.search(r"\d{4}-\d{2}-\d{2}|labelbox|\d,\d{3}", low)
    (tmp_path / "crownfirst-atlas.html").write_text("<html>x</html>")
    assert 'href="crownfirst-atlas.html#view=models"' in build_index.build_about(
        build_index.available_names(str(tmp_path)))


def _scope_tables(tmp_path):
    (tmp_path / "per_species_health.csv").write_text(
        "species,n_labelled_frames\na,10\nb,5\n", encoding="utf-8")
    keys = ["DJI_20240911145743_0030_V_1zoom.JPG", "DJI_20260322092500_0001_V_2zoom.JPG",
            "DJI_20250101000000_0002_V_3zoom.JPG"]
    missions = ["20240911_a", "20260114_b", "20240911_a"]
    (tmp_path / "send_batches.csv").write_text(
        "global_key,image_url,mission\n" + "".join(f"{k},,{m}\n" for k, m in zip(keys, missions)),
        encoding="utf-8")


def test_scope_sentence_numbers_equal_the_table_counts(build_index, tmp_path):
    fake_build(tmp_path)
    _scope_tables(tmp_path)
    (tmp_path / "embedding-atlas.html").write_text("<html>Atlas</html>")
    s = build_index.scope_sentence(str(tmp_path))
    assert "15 labelled frames across 2 species are scored on Model health" in s
    assert "3 unlabelled photos from 2 missions are queued for labelling, photographed 2024-09-11 to 2026-01-14" in s
    assert "Drone-photographed crowns only" in s
    home = build_index.build(str(tmp_path))
    about = build_index.build_about(build_index.available_names(str(tmp_path)), s)
    for out in (home, about):
        assert s in out
        assert 'href="embedding-atlas.html#view=locations">See the map' in out


def test_scope_sentence_omits_span_when_no_mission_has_a_date(build_index, tmp_path):
    (tmp_path / "send_batches.csv").write_text(
        "global_key,image_url,mission\nDJI_20260322092500_0001_V_2tele.JPG,,\nDJI_20260322092501_0002_V_3tele.JPG,,site_a\nDJI_20260322092502_0003_V_4tele.JPG,,site_b\n",
        encoding="utf-8")
    s = build_index.scope_sentence(str(tmp_path))
    assert "3 unlabelled photos from 2 missions are queued for labelling." in s
    assert "photographed" not in s.replace("Drone-photographed", "")


def test_scope_sentence_omits_what_the_tables_cannot_give(build_index, tmp_path):
    assert build_index.scope_sentence(str(tmp_path)) == "Drone-photographed crowns only, not every tree."
    assert "Data scope" not in build_index.build_about({"about.html"})


def test_intro_names_the_audience_and_the_limits(build_index, tmp_path):
    out = build_index.build(fake_build(tmp_path))
    intro = out[out.index('<p class="intro">'):out.index("</p>", out.index('<p class="intro">'))]
    assert "project leads and the labelling coordinator" in intro
    assert "Annotators work in Labelbox" in intro and "hidden on purpose" in intro
    assert "does not yet suggest where to fly the drone" in intro


def test_about_glossary_defines_the_data_terms(build_index):
    about = build_index.build_about({"about.html"})
    assert [t for t, _ in build_index.GLOSSARY] == [
        "Close-up", "Crown", "Centre crown", "Segmentation version", "Mission"]
    for term, meaning in build_index.GLOSSARY:
        assert f"<dt>{term}</dt><dd>{meaning}</dd>" in about
    assert "A frame is the same thing" in about
