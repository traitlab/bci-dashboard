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
    assert "model predictions need expert confirmation" in low
    assert "each page describes its own snapshot" in low
    for term in ("Recorded label", "Pl@ntNet top prediction", "Labelled frame"):
        assert f"<dt>{term}</dt>" in about
    assert "crownfirst" not in about
    assert 'href="explorer.html"' in about
    # Labelbox is named as the annotators' tool; no Labelbox link or data.
    assert not re.search(r"\d{4}-\d{2}-\d{2}|labelbox\.com|\d,\d{3}", low)
    (tmp_path / "crownfirst-atlas.html").write_text("<html>x</html>")
    assert 'href="crownfirst-atlas.html#view=models"' in build_index.build_about(
        build_index.available_names(str(tmp_path)))


def _write(tmp_path, name, header, *rows):
    (tmp_path / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


def _scope_tables(tmp_path):
    """36 frames, 17 labelled, 10 scored; 13 carry a checked label (10 scored, 2 with no
    usable answer, 1 whose label stops above species), 4 a Labelbox label not yet checked."""
    _write(tmp_path, "scope.csv",
           "mission,site,n_frames,n_labelled,n_scored,n_correct_top1,n_reviewed,n_no_answer,"
           "n_above_species,first_capture,last_capture",
           "20240911_sitea_w_m3e,sitea,20,12,6,3,9,2,1,20240911,20250101",
           "20250101_siteb_w_m3e,siteb,6,0,0,0,0,0,0,,",
           "20260114_sitea_x_m3e,sitea,10,5,4,2,4,0,0,20260114,20260322")
    _write(tmp_path, "per_species_health.csv", "species,n_labelled_frames", "a,6", "b,4")


def _outgoing_tables(tmp_path, sent=1, no_species=2):
    """11 photos in no project: 1 sent, 3 ready (batches 1-2, one from a priority mission),
    2 packed after them (batch 3), 3 kept out (1 pushed down, 2 predicted liana), 2 with no species.
    frames.csv marks every unbatched frame no_answer, so the kept-out ones are told apart by the queue."""
    _write(tmp_path, "frames.csv", "global_key,status,priority_mission",
           "a1,batched,True", *[f"{k},batched,False" for k in ("a2", "b1", "c1", "c2")],
           "w1,no_answer,True", "l1,no_answer,False", "l2,no_answer,False",
           *[f"s{i},already_sent,False" for i in range(sent)],
           *[f"n{i},no_answer,False" for i in range(no_species)])
    _write(tmp_path, "send_batches.csv", "batch_id,global_key,handed_out",
           "1,a1,True", "1,a2,True", "2,b1,True", "3,c1,False", "3,c2,False")
    _write(tmp_path, "send_first_queue.csv", "global_key,batch_id,no_batch_reason",
           "a1,1,", "a2,1,", "b1,2,", "c1,3,", "c2,3,", "w1,,pushed_down", "l1,,predicted_liana", "l2,,predicted_liana")


EVALUATION = (
    '<p>Frames in the Pl@ntNet evaluation: <a href="scope.csv">36</a> &middot; 3 missions &middot; 2 sites '
    '&middot; flown 2024-09-11 to 2026-03-22</p>'
    '<ul><li><a href="scope.csv">17 labelled</a>: a botanist outlined the crowns in the frame; the label is '
    'the species covering the most crown area<ul>'
    '<li><a href="per_species_health.csv">10 scored on Model health</a> (2 species): since 2026-09-29, '
    'only frames whose species name was checked for the official BCI data publication, and with a Pl@ntNet '
    'answer naming at least one species</li>'
    '<li>7 not scored: 4 with a Labelbox label not yet checked for publication, 2 with no usable Pl@ntNet '
    'answer, 1 with a label that stops above species</li></ul></li>'
    '<li><a href="scope.csv">19 not yet labelled</a>, already in the botanists\' Labelbox project</li></ul>'
    '<p>The reference labels changed on 2026-09-29; scores before then used the Labelbox labels.</p>')
def outgoing(apart=""):
    return (
        '<p>Photos going out for labelling: 11 photos in the 2024_bci Labelbox dataset '
        f'that are not yet in a Labelbox project, the workspace where botanists label.{apart}</p>'
        '<ul><li>1 sent to the botanists\' Labelbox project so far</li>'
        '<li>5 in batches of up to 100<ul>'
        '<li><a href="send_batches.csv">3</a> ready to send (batches 1-2, handed to the labelling coordinator; '
        'they do not change), 1 of them from priority missions: their crowns were also identified on the ground, so a label can be '
        'checked twice</li>'
        '<li>2 packed after them (batch 3, these can still change)</li></ul></li>'
        '<li><a href="send_first_queue.csv">3</a> in no batch<ul><li>1 pushed down the queue: Pl@ntNet is already '
        'confident and the species has enough labels, so they wait until Pl@ntNet\'s model changes. The current '
        'model is from 20 March 2026 (release 7.5)</li>'
        '<li>2 predicted liana, which are not sent: since 2026-10-29 only predicted trees go out, and the liana '
        'call is a Pl@ntNet guess</li></ul></li>'
        '<li>2 left out: the Pl@ntNet answer names no species</li></ul>')


OUTGOING = outgoing()
LEAD = ("<p>Drone photos of tree crowns only. A tree whose crown was not photographed is not here. "
        "A frame is one drone photo.</p>")


def test_scope_breakdown_matches_the_target_wording_off_the_tables(build_index, tmp_path):
    _scope_tables(tmp_path)
    _outgoing_tables(tmp_path)
    _write(tmp_path, "pool_overlap.csv", "global_key")
    s = build_index.scope_breakdown(str(tmp_path))
    assert s == LEAD + EVALUATION + outgoing(" None of them is among the frames in the evaluation above.")
    # The words the page must not use.
    assert not re.search(r"close-up|queued|can_wait|Antoine", s, re.IGNORECASE)
    fake_build(tmp_path)
    (tmp_path / "embedding-atlas.html").write_text("<html>Atlas</html>")
    about = build_index.build_about(build_index.available_names(str(tmp_path)), build_index.scope_breakdown(str(tmp_path)))
    assert '<h2 id="scope">Data scope</h2>' in about and s in about
    assert 'href="embedding-atlas.html#view=locations">See the map' in about
    # Nested lists, not a table or a wall of text, so a phone reads them in order.
    assert about.count("<ul>") - build_index.build_about({"about.html"}).count("<ul>") == 5
    assert s not in build_index.build(str(tmp_path))


def test_each_branch_is_left_out_when_its_table_is_absent(build_index, tmp_path):
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD
    assert "Data scope" not in build_index.build_about({"about.html"})
    _scope_tables(tmp_path)
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD + EVALUATION
    (tmp_path / "per_species_health.csv").unlink()
    # With no species table the scored figure comes off scope.csv alone, without a species count.
    assert "<a href=\"per_species_health.csv\">10 scored on Model health</a>: since" in build_index.scope_breakdown(str(tmp_path))
    _write(tmp_path, "scope.csv", "mission,site,n_frames,n_labelled", ",,3,1")
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD + (
        '<p>Frames in the Pl@ntNet evaluation: <a href="scope.csv">3</a></p>'
        '<ul><li><a href="scope.csv">1 labelled</a>: a botanist outlined the crowns in the frame; the label is '
        'the species covering the most crown area</li><li><a href="scope.csv">2 not yet labelled</a>, '
        'already in the botanists\' Labelbox project</li></ul>')
    (tmp_path / "scope.csv").unlink()
    _outgoing_tables(tmp_path)
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD + OUTGOING
    # A queue file from before the reason column is the main pool's, not the catalog's.
    _write(tmp_path, "send_first_queue.csv", "global_key,batch_id", "a1,1")
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD
    (tmp_path / "frames.csv").unlink()


def test_empty_tables_leave_their_branch_out_and_zero_rows_are_not_printed(build_index, tmp_path):
    _write(tmp_path, "scope.csv", "mission,site,n_frames,n_labelled")
    _write(tmp_path, "frames.csv", "global_key,status,priority_mission")
    _write(tmp_path, "send_batches.csv", "batch_id,global_key,handed_out")
    _write(tmp_path, "send_first_queue.csv", "global_key,batch_id,no_batch_reason")
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD
    _outgoing_tables(tmp_path, sent=0, no_species=0)
    s = build_index.scope_breakdown(str(tmp_path))
    assert "<li>0 sent to the botanists' Labelbox project so far" in s and "names no species" not in s
    # Nothing kept out, nothing from a priority mission: those clauses go, not "0 ...".
    _write(tmp_path, "frames.csv", "global_key,status,priority_mission", "a1,batched,False", "b1,batched,False")
    _write(tmp_path, "send_batches.csv", "batch_id,global_key,handed_out", "1,a1,True", "2,b1,False")
    _write(tmp_path, "send_first_queue.csv", "global_key,batch_id,no_batch_reason", "a1,1,", "b1,2,")
    s = build_index.scope_breakdown(str(tmp_path))
    assert "in no batch" not in s and "priority" not in s and "1</a> ready to send (batch 1, handed" in s
    assert "1 packed after them (batch 2, these can still change)" in s


@pytest.mark.parametrize("header, rows, gap", [
    ("mission,site,n_frames,n_labelled,n_scored,n_reviewed,n_no_answer,n_above_species",
     [",,10,6,4,6,1,0"], "6 frames with a checked label are not 4 scored + 1 with no usable answer"),
    ("mission,site,n_frames,n_labelled", [",,3,5"], "more labelled frames than frames"),
    ("mission,site,n_frames,n_labelled,n_scored", [",,10,6,7"], "7 frames are scored but only 6 are labelled"),
    ("mission,site,n_frames,n_labelled,n_scored,n_reviewed,n_no_answer,n_above_species",
     [",,10,3,3,5,2,0"], "5 frames have a checked label but only 3 are labelled"),
    ("mission,site,n_frames,n_labelled,n_scored", [",,36,17,9"], "scope.csv scores 9 frames, per_species_health.csv 10"),
])
def test_an_evaluation_branch_that_does_not_sum_to_its_parent_stops_the_build(
        build_index, tmp_path, header, rows, gap):
    _scope_tables(tmp_path)
    _write(tmp_path, "scope.csv", header, *rows)
    if "per_species_health" not in gap:  # the other gaps must show without the species table to catch them
        (tmp_path / "per_species_health.csv").unlink()
    with pytest.raises(SystemExit, match=r"VERIFY FAIL: the About scope does not add up, .*" + re.escape(gap)):
        build_index.scope_breakdown(str(tmp_path))


def test_a_photo_no_branch_accounts_for_stops_the_build(build_index, tmp_path):
    _outgoing_tables(tmp_path)
    with open(tmp_path / "frames.csv", "a", encoding="utf-8") as fh:
        fh.write("x,no_prediction,False\n")
    with pytest.raises(SystemExit, match=r"the About scope does not add up, the 12 photos in no project are not "
                                         r"1 sent \+ 3 ready \+ 2 packed \+ 1 pushed_down \+ 2 liana \+ 2 no_species"):
        build_index.scope_breakdown(str(tmp_path))


def test_scope_byline_links_each_count_to_its_table(build_index, tmp_path):
    full = ' <a href="about.html#scope">Full scope</a>.'
    line = build_index.scope_byline(str(tmp_path), {"index.html"})
    assert line == f'<div class="subtitle">Drone-photographed crowns only.{full}</div>'
    _scope_tables(tmp_path)
    _outgoing_tables(tmp_path)
    line = build_index.scope_byline(str(tmp_path), {"embedding-atlas.html"})
    assert line == ('<div class="subtitle">Drone-photographed crowns only. '
                    '<a href="scope.csv">36 frames</a> in the evaluation: <a href="scope.csv">17 labelled</a>, '
                    '<a href="per_species_health.csv">10 scored</a>. '
                    '<a href="send_batches.csv">3 photos</a> ready to send.'
                    f' <a href="embedding-atlas.html#view=locations">See the map</a>.{full}</div>')
    # No scored figure and one ready photo: each part is left out or singular on its own.
    (tmp_path / "per_species_health.csv").unlink()
    _write(tmp_path, "scope.csv", "mission,site,n_frames,n_labelled", ",,1,0")
    _write(tmp_path, "send_batches.csv", "batch_id,global_key,handed_out", "1,a1,True", "2,a2,False")
    _write(tmp_path, "send_first_queue.csv", "global_key,batch_id,no_batch_reason",
           "a1,1,", "a2,2,", "w1,,pushed_down", "l1,,predicted_liana", "l2,,predicted_liana")
    _write(tmp_path, "frames.csv", "global_key,status,priority_mission", *[f"{k},batched,False" for k in ("a1", "a2")],
           "w1,batched,False", "l1,batched,False", "l2,batched,False")
    assert build_index.scope_byline(str(tmp_path), set()) == (
        '<div class="subtitle">Drone-photographed crowns only. <a href="scope.csv">1 frame</a> in the evaluation: '
        '<a href="scope.csv">0 labelled</a>. <a href="send_batches.csv">1 photo</a> ready to send.'
        f'{full}</div>')


def test_scope_breakdown_dates_come_from_capture_stamps_not_folder_names(build_index, tmp_path):
    # A 2025 mission holds March 2026 photos; a row with no stamp falls back to its folder date.
    _write(tmp_path, "scope.csv", "mission,site,n_frames,n_labelled,first_capture,last_capture",
           "20250811_sitea_w_m3e,sitea,2,1,20250811,20260322", "20240911_siteb_w_m3e,siteb,1,0,,")
    assert "flown 2024-09-11 to 2026-03-22" in build_index.scope_breakdown(str(tmp_path))
    _write(tmp_path, "scope.csv", "mission,site,n_frames,n_labelled", "20240911_sitea_w_m3e,sitea,1,0")
    s = build_index.scope_breakdown(str(tmp_path))
    assert "1 mission &middot; 1 site &middot; flown on 2024-09-11" in s
    _write(tmp_path, "scope.csv", "mission,site,n_frames,n_labelled", ",,3,2", "site_a,a,2,0")
    assert "flown" not in build_index.scope_breakdown(str(tmp_path))


def test_intro_names_the_audience_and_the_limits(build_index, tmp_path):
    out = build_index.build(fake_build(tmp_path))
    intro = out[out.index('<p class="intro">'):out.index("</p>", out.index('<p class="intro">'))]
    assert "project leads and the labelling coordinator" in intro
    assert "Annotators label in Labelbox, where the predictions are hidden" in intro
    assert "does not yet suggest where to fly" in intro
    assert intro.count(". ") <= 2 and 'href="about.html#audience"' in intro
    # The longer account sits on About, under the anchor the intro links.
    about = build_index.build_about({"about.html"})
    audience = about[about.index('<h2 id="audience">'):about.index("<h2>What each page")]
    assert "Annotators work in Labelbox" in audience and "hidden on purpose" in audience
    assert "do not bias identifications" in audience
    assert "does not yet suggest where to fly the drone" in audience


def test_about_glossary_defines_the_data_terms(build_index):
    about = build_index.build_about({"about.html"})
    assert [t for t, _ in build_index.GLOSSARY] == [
        "Close-up", "Crown", "Centre crown", "Segmentation version", "Mission"]
    for term, meaning in build_index.GLOSSARY:
        assert f"<dt>{term}</dt><dd>{meaning}</dd>" in about
    assert "The labelling team calls it a close-up" in about


def test_scope_breakdown_states_the_pool_overlap_only_as_measured(build_index, tmp_path):
    _scope_tables(tmp_path)
    _outgoing_tables(tmp_path)
    assert build_index.scope_breakdown(str(tmp_path)) == LEAD + EVALUATION + OUTGOING
    _write(tmp_path, "pool_overlap.csv", "global_key", "a1", "b1")
    assert build_index.scope_breakdown(str(tmp_path)) == (
        LEAD + EVALUATION + outgoing(" 2 of them are also frames in the evaluation above."))
