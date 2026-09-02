"""Direct tests for the rendering primitives in dashboard/assets.py.

Before this file the primitives were only exercised indirectly, through
test_pages.py regexing strings out of a fully built page. That leaves a bug in
a primitive to surface as a confusing whole-page assertion, and any primitive
whose output a page happens not to contain goes untested. These tests call
each primitive directly instead.

    .venv/bin/pytest tests/test_assets.py
"""

from __future__ import annotations

import re

import pytest

# A string carrying all four HTML metacharacters a caller-text argument has to
# survive: the raw angle brackets and ampersand must never reach the output.
INJECT = '<script>&"</script>'


def test_esc_escapes_html_metacharacters(assets):
    out = assets.esc(INJECT)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&amp;" in out


def test_esc_stringifies_non_string_input(assets):
    # Several callers pass ints and floats straight through esc(); it has to
    # coerce rather than assume a string.
    assert assets.esc(42) == "42"
    assert assets.esc(None) == "None"


def test_cap_uppercases_only_the_first_character(assets):
    assert assets.cap("hura crepitans") == "Hura crepitans"


def test_cap_of_empty_string_is_empty(assets):
    assert assets.cap("") == ""


@pytest.mark.parametrize("x,nd,expected", [
    (0.0, 1, "0.0%"),
    (1.0, 1, "100.0%"),
    (None, 1, "n/a"),
    (0.12345, 2, "12.35%"),
])
def test_pctf(assets, x, nd, expected):
    assert assets.pctf(x, nd) == expected


def test_slug_keeps_only_the_text_before_the_first_colon(assets):
    # A summary's live numbers sit after the colon, so the slug must not
    # depend on them.
    assert assets.slug("What to send first: 412 frames in the tail") == "what-to-send-first"


def test_slug_strips_tags_and_collapses_non_alnum(assets):
    assert assets.slug("<i>Hello</i> World!") == "hello-world"


def test_slug_of_empty_string_is_empty(assets):
    assert assets.slug("") == ""


def test_slug_keeps_only_the_first_eight_words(assets):
    long = "one two three four five six seven eight nine ten"
    assert assets.slug(long) == "one-two-three-four-five-six-seven-eight"


def test_panel_renders_summary_ask_and_body(assets):
    out = assets.panel("Overview", "Read this first", "<p>body</p>")
    assert '<details class="panel" id="overview">' in out
    assert "<summary>Overview</summary>" in out
    assert '<p class="ask">Read this first</p>' in out
    assert "<p>body</p>" in out
    assert "</details>" in out


def test_panel_open_adds_the_open_attribute(assets):
    out = assets.panel("Overview", "ask", "body", open_=True)
    assert "<details class=\"panel\" id=\"overview\" open>" in out


def test_panel_rejects_a_summary_whose_slug_carries_a_digit(assets):
    # A digit in the id means a live count leaked into the slug: a link to it
    # would break on the very next snapshot.
    with pytest.raises(SystemExit):
        assets.panel("Send first 412 frames", "ask", "body")


def test_panel_anchor_overrides_the_derived_id_and_skips_the_digit_check(assets):
    out = assets.panel("Send first 412 frames", "ask", "body", anchor="send-first")
    assert 'id="send-first"' in out


def test_section_wraps_title_lede_and_panels(assets):
    out = assets.section("Overview", "One line", "<panelhtml>")
    assert '<section class="grp" id="overview">' in out
    assert "<h2>Overview</h2>" in out
    assert '<p class="lede">One line</p>' in out
    assert "<panelhtml>" in out
    assert out.endswith("</section>")


def test_hero_marks_only_the_leading_card_as_first(assets):
    out = assets.hero([("E1", "V1", "L1", "N1"), ("E2", "V2", "L2", "N2")])
    assert '<div class="metric first">' in out
    assert out.count('class="metric first"') == 1
    assert "V1" in out and "V2" in out


def test_hero_of_no_cards_is_an_empty_shell(assets):
    assert assets.hero([]) == '<div class="hero"></div>'


def test_table_marks_numeric_columns_and_wraps_in_a_scroll_box(assets):
    out = assets.table([("Name", False), ("Count", True)], [["a", "1"], ["b", "2"]])
    assert '<div class="tscroll">' in out
    assert "<th>Name</th>" in out
    assert '<th class="num">Count</th>' in out
    assert '<td class="num">1</td>' in out
    # The non-numeric column's cells carry no class at all.
    assert "<td>a</td>" in out


def test_table_of_no_rows_still_renders_the_header(assets):
    out = assets.table([("Name", False)], [])
    assert "<th>Name</th>" in out
    assert "<tbody>\n</tbody>" in out


def test_table_sortable_from_marks_only_the_later_columns(assets):
    out = assets.table([("Name", False), ("Count", True)], [["a", "1"]], sortable_from=1)
    assert '<th>Name</th>' in out
    assert '<th class="num sortable">Count</th>' in out


def test_table_id_is_rendered_when_given(assets):
    out = assets.table([("Name", False)], [["a"]], tid="species-table")
    assert "id='species-table'" in out


def test_table_row_attrs_land_on_the_row_not_the_cells(assets):
    out = assets.table([("Name", False)], [["a"]], row_attrs=[' data-species="a"'])
    assert '<tr data-species="a">' in out


def test_filterable_table_wires_up_the_shared_element_ids(assets):
    out = assets.filterable_table([("Name", False)], [["a"]], options=[("hard", "Hard")])
    assert 'id="species-filter"' in out
    assert 'id="status-filter"' in out
    assert 'id="species-count"' in out
    assert "id='species-table'" in out
    assert '<option value="all">every status</option>' in out
    assert '<option value="hard">Hard</option>' in out


def test_filterable_table_with_no_statuses_ships_no_status_dropdown(assets):
    out = assets.filterable_table([("Name", False)], [["a"]], options=[])
    assert "<select" not in out, (
        "a select holding only 'every status' is a control that cannot change "
        "what the table shows")
    assert 'id="species-filter"' in out
    assert 'id="species-count"' in out


def test_the_sort_headings_can_be_reached_without_a_mouse(assets):
    """The pages tell the reader to click any heading to sort. A control a page
    names has to be reachable by whoever is reading it, so the headings carry a
    tab stop, a role, Enter/Space activation and an aria-sort the row order can
    be read off."""
    js = assets.JS
    for needed in ("th.tabIndex=0", "role','button'", "aria-sort",
                   "e.key==='Enter'", "e.key===' '"):
        assert needed in js, f"keyboard sorting lost {needed!r}"
    assert "th.sortable:focus-visible" in assets.CSS, (
        "a tab stop with no visible focus ring is a control a keyboard reader "
        "cannot find")


def test_an_empty_filter_result_says_so_in_words(assets):
    assert "No species matches that filter." in assets.JS, (
        "a bare '0 of 186' over an empty table reads as a broken page")


def test_filterable_table_escapes_option_value_and_label(assets):
    out = assets.filterable_table([("Name", False)], [], options=[(INJECT, INJECT)])
    assert "<script>&" not in out
    assert "&lt;script&gt;" in out


def test_funnel_list_of_no_steps_is_an_empty_list(assets):
    assert assets.funnel_list([]) == '<ul class="todo"></ul>'


def test_funnel_list_formats_the_count_with_thousands_separators(assets):
    out = assets.funnel_list([(1234, "frames")])
    assert '<span class="n">1,234</span> frames' in out


def test_funnel_list_of_a_zero_count(assets):
    out = assets.funnel_list([(0, "frames")])
    assert '<span class="n">0</span> frames' in out


def test_funnel_list_escapes_the_label(assets):
    out = assets.funnel_list([(1, INJECT)])
    assert "<script>&" not in out


def test_num_cell_omits_the_sort_attribute_when_the_cell_text_already_sorts(assets):
    """The sort falls back to the cell's own text, so an integer needs no
    attribute. Shipping one anyway cost 5KB across the 186-row species table."""
    assert assets.num_cell(392, "392") == "392"


def test_num_cell_keeps_the_sort_attribute_wherever_the_text_would_mislead(assets):
    """Three cases the fallback gets wrong: a rounded percentage hides the
    figure it was rounded from, a rounded decimal hides its tie-breaks, and
    JavaScript reads "1,204" as 1."""
    assert assets.num_cell("0.928571", "92.9%") == '<span data-sort="0.928571">92.9%</span>'
    assert assets.num_cell("0.859354", "0.86") == '<span data-sort="0.859354">0.86</span>'
    assert assets.num_cell(1204, "1,204") == '<span data-sort="1204">1,204</span>'


def test_status_tag_renders_class_and_label(assets):
    out = assets.status_tag("hard", "Hard")
    assert out == '<span class="tag hard">Hard</span>'


def test_status_tag_escapes_class_and_label(assets):
    out = assets.status_tag(INJECT, INJECT)
    assert "<script>&" not in out


def test_status_legend_lists_one_entry_per_status(assets):
    out = assets.status_legend([("hard", "Hard", "Escapes review")])
    assert out == ('<ul class="status-legend"><li><span class="tag hard">Hard</span> '
                   'Escapes review</li></ul>')


def test_status_legend_of_no_entries_is_an_empty_list(assets):
    assert assets.status_legend([]) == '<ul class="status-legend"></ul>'


def test_status_legend_escapes_the_reason(assets):
    out = assets.status_legend([("hard", "Hard", INJECT)])
    assert "<script>&" not in out


def test_svg_hbar_of_no_rows_is_empty(assets):
    assert assets.svg_hbar([]) == ""


def test_svg_hbar_renders_one_rect_pair_per_row(assets):
    out = assets.svg_hbar([("Big", 0.9, "90%", "#111"), ("Small", 0.1, "10%", "#222")])
    assert out.count("<rect") == 4  # a track rect and a fill rect per row
    assert "<svg" in out and out.strip().endswith("</svg>")


def test_svg_hbar_bar_width_is_a_function_of_frac(assets):
    # The relationship, not a pixel count, so a style tweak to row_h/label_w
    # cannot break this test.
    out = assets.svg_hbar([("Big", 0.9, "90%", "#111"), ("Small", 0.1, "10%", "#222")])
    fills = re.findall(r'<rect x="\d+" y="\d+" width="(\d+)" height="16" fill="#(?:111|222)"', out)
    assert len(fills) == 2
    assert int(fills[0]) > int(fills[1])


def test_svg_hbar_escapes_label_and_right_text(assets):
    out = assets.svg_hbar([(INJECT, 0.5, INJECT, "#111")])
    assert "<script>&" not in out


def test_svg_hbar_widens_to_fit_a_long_right_hand_label(assets):
    # right_w grows to fit the longest value label rather than clipping it,
    # so a much longer label should push the svg's own width out.
    short = assets.svg_hbar([("A", 0.5, "1%", "#111")])
    long = assets.svg_hbar(
        [("A", 0.5, "1,234,567,890,123 crowns much longer text here", "#111")])
    width = lambda svg: int(svg.split('width="')[1].split('"')[0])
    assert width(long) > width(short)


def test_svg_weight_pair_of_no_rows_is_empty(assets):
    assert assets.svg_weight_pair([], label_a="A", label_b="B") == ""


def test_svg_weight_pair_requires_each_column_to_sum_to_one(assets):
    with pytest.raises(ValueError):
        assets.svg_weight_pair([("a", 0.5, 0.6, "", "#111")], label_a="A", label_b="B")


def test_svg_weight_pair_top_bar_keeps_band_colour_and_widens_with_its_share(assets):
    # Swapping the two share columns, or reading a share off the wrong
    # denominator, would still draw *a* bar, just the wrong shape, and no
    # printed number would catch it -- so the geometry itself is the check.
    rows = [("a", 0.25, 0.75, "", "#111111"), ("b", 0.75, 0.25, "", "#222222")]
    svg = assets.svg_weight_pair(rows, label_a="A", label_b="B")
    got = re.findall(r'<rect x="([\d.]+)" y="(\d+)" width="([\d.]+)"[^>]*fill="(#\w+)"', svg)
    top = [g for g in got if g[1] == "8"]
    assert len(top) == 2
    assert top[0][3] == "#111111" and top[1][3] == "#222222"  # band keeps its colour
    assert float(top[0][2]) < float(top[1][2])  # a's 0.25 share draws narrower than b's 0.75
    assert float(top[0][0]) < float(top[1][0])  # a is still drawn first, starting further left


def test_svg_weight_pair_bottom_bar_mirrors_the_weight_moving_across(assets):
    # Same bands, same colours, but the shares are swapped between the two
    # bars -- the whole point of the pair is that the reader sees the weight
    # move from one bar to the other without doing arithmetic.
    rows = [("a", 0.25, 0.75, "", "#111111"), ("b", 0.75, 0.25, "", "#222222")]
    svg = assets.svg_weight_pair(rows, label_a="A", label_b="B")
    got = re.findall(r'<rect x="([\d.]+)" y="(\d+)" width="([\d.]+)"[^>]*fill="(#\w+)"', svg)
    bottom = [g for g in got if g[1] == "48"]
    assert len(bottom) == 2
    assert bottom[0][3] == "#111111" and bottom[1][3] == "#222222"  # band keeps its colour
    assert float(bottom[0][2]) > float(bottom[1][2])  # a's 0.75 share now wider than b's 0.25


def test_svg_weight_pair_escapes_the_axis_labels(assets):
    rows = [("a", 1.0, 1.0, "note", "#111111")]
    out = assets.svg_weight_pair(rows, label_a=INJECT, label_b="B")
    assert "<script>&" not in out
