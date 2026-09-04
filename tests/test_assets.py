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


def test_a_hero_card_can_link_the_csv_its_figure_comes_off(assets):
    """The card is where a reader meets the number, so it is where the rows
    behind it should be reachable from. The link carries the filename as its
    text: a bare arrow or the word "CSV" hides which file arrives."""
    out = assets.hero([("E1", "V1", "L1", "N1", "send_batches.csv")])
    assert '<a class="src" href="send_batches.csv">send_batches.csv</a>' in out
    # Inside the row, beside the figure, not below the note: the row's flex rule
    # is what puts it on the right of the number.
    assert '<div class="v">V1</div><a class="src"' in out


def test_a_hero_card_with_no_source_renders_no_link(assets):
    """Most cards have no single file behind them, and an empty href would be a
    link back to the page itself."""
    out = assets.hero([("E1", "V1", "L1", "N1")])
    assert "<a" not in out


def test_a_hero_card_of_the_wrong_shape_stops_the_build(assets):
    """A card short of its note, or carrying a sixth item, is a call site that
    has drifted from the renderer. It fails here rather than rendering a card
    with the note in the label's place."""
    for card in [("E1", "V1", "L1"), ("E1", "V1", "L1", "N1", "a.csv", "extra")]:
        with pytest.raises(SystemExit, match="hero card 0"):
            assets.hero([card])


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


def test_the_sort_headings_can_be_reached_without_a_mouse(style):
    """The pages tell the reader to click any heading to sort. A control a page
    names has to be reachable by whoever is reading it, so the headings carry a
    tab stop, a role, Enter/Space activation and an aria-sort the row order can
    be read off."""
    js = style.JS
    for needed in ("th.tabIndex=0", "role','button'", "aria-sort",
                   "e.key==='Enter'", "e.key===' '"):
        assert needed in js, f"keyboard sorting lost {needed!r}"
    assert "th.sortable:focus-visible" in style.CSS, (
        "a tab stop with no visible focus ring is a control a keyboard reader "
        "cannot find")


def test_an_empty_filter_result_says_so_in_words(style):
    assert "No species matches that filter." in style.JS, (
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


def test_an_identified_table_aligns_its_numbers_by_column_not_by_cell(assets):
    """class="num" on every cell of the 187-row species table was 9KB of the
    same six characters. With an id there is a selector to say it once."""
    out = assets.table([("Species", False), ("Frames", True), ("Right", True)],
                       [["a", "1", "2"]], tid="t")
    assert '<style>#t td:nth-child(2),#t td:nth-child(3){' in out
    assert 'class="num"' not in out.split("<tbody>")[1]
    # The heading keeps its class: the sort arrow and the alignment of the
    # heading itself are styled off it.
    assert '<th class="num sortable">Frames</th>' in out or '<th class="num">Frames</th>' in out


def test_an_anonymous_table_still_marks_its_numeric_cells(assets):
    """No id means no selector to write the rule against, and these tables are
    a handful of rows, so the per-cell class is the cheaper of the two."""
    out = assets.table([("Species", False), ("Frames", True)], [["a", "1"]])
    assert "<style>" not in out
    assert '<td class="num">1</td>' in out


def test_num_cell_omits_the_sort_attribute_when_the_cell_text_already_sorts(assets):
    """The sort falls back to the cell's own text, so an integer needs no
    attribute. Shipping one anyway cost 5KB across the 186-row species table."""
    assert assets.num_cell(392, "392") == ("392", "")


def test_num_cell_keeps_the_sort_attribute_wherever_the_text_would_mislead(assets):
    """Three cases the fallback gets wrong: a rounded percentage hides the
    figure it was rounded from, a rounded decimal hides its tie-breaks, and
    JavaScript reads "1,204" as 1."""
    assert assets.num_cell("0.928571", "92.9%") == ("92.9%", ' data-sort="0.928571"')
    assert assets.num_cell("0.859354", "0.86") == ("0.86", ' data-sort="0.859354"')
    assert assets.num_cell(1204, "1,204") == ("1,204", ' data-sort="1204"')

    # The attribute lands on the cell's own <td>, not on a span inside it.
    headers = [("Species", False), ("First guess right", True)]
    out = assets.table(headers, [["a", assets.num_cell("0.928571", "92.9%")]])
    assert '<td class="num" data-sort="0.928571">92.9%</td>' in out


def test_sort_key_carries_the_whole_number_and_nothing_idle(assets):
    """Six decimals is the precision, so two species that round to the same
    percentage still sort apart. Everything past the last non-zero digit is
    dropped: the sort reads it with parseFloat, which cannot tell "0.5" from
    "0.500000", and the page carries 558 of these."""
    assert assets.sort_key(0.0) == "0"
    assert assets.sort_key(0.5) == "0.5"
    assert assets.sort_key(1.0) == "1"
    assert assets.sort_key(0.9285714) == "0.928571"
    assert assets.sort_key(0.9285716) == "0.928572"
    assert assets.sort_key(1204) == "1204"
    assert assets.sort_key("0.859354") == "0.859354"


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


def test_svg_curve_of_no_series_is_empty(assets):
    assert assets.svg_curve([]) == ""
    assert assets.svg_curve([("empty", [], "#111")]) == ""


def test_svg_curve_draws_one_path_per_series(assets):
    out = assets.svg_curve([("up", [(0, 0), (1, 1)], "#111"),
                            ("flat", [(0, 1), (1, 1)], "#222")])
    assert out.count("<path") == 2
    assert "<svg" in out and out.strip().endswith("</svg>")


def test_svg_curve_puts_a_bigger_y_higher_up_the_page(assets):
    # The relationship, not a pixel count. SVG y grows downwards, so the taller
    # value must carry the smaller number, and a sign flip here would draw every
    # curve on this page upside down while every other check still passed.
    out = assets.svg_curve([("s", [(0, 0), (1, 10)], "#111")])
    d = re.search(r'<path d="M([\d.]+),([\d.]+) L([\d.]+),([\d.]+)"', out)
    assert d, out
    assert float(d.group(4)) < float(d.group(2))


def test_svg_curve_scales_from_zero_not_from_the_lowest_point(assets):
    # A curve on a cropped axis exaggerates the gap between two lines, which is
    # the one thing this chart exists to report honestly.
    out = assets.svg_curve([("s", [(0, 100), (1, 101)], "#111")])
    d = re.search(r'<path d="M[\d.]+,([\d.]+) L[\d.]+,([\d.]+)"', out)
    assert d, out
    # 100 and 101 are a 1% difference. Zero-based, they land on almost the same
    # line. An axis cropped to the data would spread them the full plot height.
    assert abs(float(d.group(1)) - float(d.group(2))) < 5


def test_svg_curve_escapes_every_label_it_is_handed(assets):
    out = assets.svg_curve([(INJECT, [(0, 0), (1, 1)], "#111")],
                           title=INJECT, x_title=INJECT, y_title=INJECT,
                           rules=[(0.5, INJECT)], marks=[(0.5, INJECT)])
    assert "<script>&" not in out


def test_svg_curve_widens_its_right_margin_to_fit_a_long_series_label(assets):
    # The series label sits at the end of its own line, outside the plot. A
    # margin that did not grow would push it off the viewBox, and SVG clips.
    plot = lambda svg: float(re.search(r'<line x1="[\d.]+" y1="[\d.]+" x2="([\d.]+)"',
                                       svg).group(1))
    short = assets.svg_curve([("A", [(0, 0), (1, 1)], "#111")])
    long = assets.svg_curve([("A much longer series label", [(0, 0), (1, 1)], "#111")])
    assert plot(long) < plot(short)


def test_svg_curve_rule_lifts_the_axis_when_it_sits_above_every_point(assets):
    # A rule drawn off the top of the plot is worse than no rule: it reads as if
    # no line ever reached the level being compared against.
    out = assets.svg_curve([("s", [(0, 0), (1, 1)], "#111")], rules=[(4, "high")])
    assert '>4<' in out, "the rule's own value has to appear on the y axis"


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


def test_css_for_drops_only_the_rules_the_page_has_nothing_to_style(assets):
    """One stylesheet covers every page and the pages are no longer alike. A
    rule goes only when every selector in it names a class the page never
    renders: element, id and state rules are none of this function's business,
    and neither is a class the script adds at runtime."""
    css = (".hero{a:1}\n.gone{b:2}\np{c:3}\n#id{d:4}\n"
           ".hero .metric,.gone{e:5}\n.gone,.other{f:6}\n"
           "tr.hidden{g:7}\n@media(max-width:640px){.gone{h:8}}")
    kept = assets.css_for(css, '<div class="hero"><p class="metric"></p></div>'
                               "<script>r.classList.toggle('hidden',x)</script>")
    assert ".gone{b:2}" not in kept
    assert ".hero{a:1}" in kept          # rendered
    assert "p{c:3}" in kept              # an element, not a class
    assert "#id{d:4}" in kept            # an id, not a class
    assert ".hero .metric,.gone{e:5}" in kept   # one live selector keeps the rule
    assert ".gone,.other{f:6}" not in kept      # neither selector is rendered
    assert "tr.hidden{g:7}" in kept      # the script writes this one
    assert "@media(max-width:640px){.gone{h:8}}" in kept  # kept whole


def test_css_for_leaves_every_class_the_page_renders_styled(assets, pagemod):
    """The point of the trim is bytes, so the failure to guard against is a
    page that loses a rule it needed and quietly renders unstyled."""
    body = '<div class="hero"><span class="tag reliable">x</span></div>'
    kept = assets.css_for(assets.strip_comments(pagemod.CSS), body + pagemod.JS)
    styled = set(re.findall(r"\.([A-Za-z][\w-]*)", kept))
    for rendered in ("hero", "tag", "reliable"):
        assert rendered in styled, f"the page renders .{rendered} and lost its rule"


def _relative_luminance(hex_color):
    """WCAG 2.1 relative luminance of an #rrggbb colour."""
    h = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _relative_luminance(a), _relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# Each row is a contrast ratio a comment states in prose, with the two colours
# it was measured between. The comment is the only record of why a colour was
# chosen, so a colour edit that does not move the comment leaves the reason
# describing a shade that is no longer there.
CONTRAST_CLAIMS = [
    ("dashboard/assets.py", "stays faint at {r}:1 on the white panel", "#bdbdbd", "#ffffff"),
    ("dashboard/style.py", "{r}:1 here against", "#6d6d6d", "#f5f5f5"),
    ("dashboard/style.py", "against {r}:1 before", "#bdbdbd", "#f5f5f5"),
]


@pytest.mark.parametrize("where,phrase,fg,bg", CONTRAST_CLAIMS,
                         ids=[f"{w.split('/')[1]}-{fg}" for w, _p, fg, _b in CONTRAST_CLAIMS])
def test_a_stated_contrast_ratio_is_the_one_the_two_colours_have(where, phrase, fg, bg):
    from conftest import REPO
    text = (REPO / where).read_text(encoding="utf-8")
    ratio = f"{_contrast(fg, bg):.2f}"
    assert phrase.format(r=ratio) in text, (
        f"{where} states a contrast for {fg} on {bg} that is not {ratio}:1, which "
        f"is what those two colours measure.")


def test_the_band_palette_is_as_readable_and_as_unordered_as_its_comment_says(explain):
    """Both halves of the BAND_COLOR comment are measurements, not choices.

    It promises every band clears 4.5:1 against white, which is what makes the
    number inside the bar readable, and it admits the ramp carries no order by
    listing the luminances and the closest pair. Swap one hex and the promise
    can break while the admission keeps quoting the old palette.
    """
    import pathlib
    import re

    colors = list(explain.BAND_COLOR.values())
    worst = min(_contrast(c, "#ffffff") for c in colors)
    assert worst >= 4.5, (
        f"the comment promises all {len(colors)} bands clear 4.5:1 against white; "
        f"the weakest is {worst:.2f}:1.")

    src = pathlib.Path(explain.__file__).read_text(encoding="utf-8")
    said = re.search(r"luminance ([\d., \n#]+?);", src)
    assert said, "explain.py no longer lists the band luminances"
    listed = [x for x in re.findall(r"0\.\d+", said.group(1))]
    assert listed == [f"{_relative_luminance(c):.3f}" for c in colors], (
        f"the comment lists luminances {listed}, the palette measures "
        f"{[f'{_relative_luminance(c):.3f}' for c in colors]}.")

    ends = f"{_contrast(colors[0], colors[-1]):.2f}"
    closest = min(_contrast(a, b) for i, a in enumerate(colors) for b in colors[i + 1:])
    assert f"the two ends sit at {ends}:1" in src, (
        f"the comment misstates the end-to-end contrast, which is {ends}:1.")
    assert f"at {closest:.2f}:1" in src, (
        f"the comment misstates the closest pair, which is {closest:.2f}:1.")


# ---------------------------------------------------------------------------
# table(source=...): the file a table's rows are in
# ---------------------------------------------------------------------------

def test_a_table_names_no_file_unless_one_is_passed(assets):
    """Most tables are counted off a figure with no file of its own, and a
    caption pointing at a near-enough CSV makes the table lie."""
    out = assets.table([("a", False)], [["1"]])
    assert ".csv" not in out


def test_a_table_with_a_source_links_it_under_the_rows(assets):
    """Under, not in the paragraph above: a reader who wants the rows is looking
    at the rows. `page.copy_linked_csvs` reads this href, so the file travels
    with the page and a named table cannot ship a 404."""
    out = assets.table([("a", False)], [["1"]], source="per_species_health.csv")
    assert out.index("</table>") < out.index('href="per_species_health.csv"')


def test_the_filterable_table_carries_its_source_the_same_way(assets):
    """The species table is the one a reader most wants as data, and it is the
    one that does not go through `table` at the call site."""
    out = assets.filterable_table([("Species", False)], [["a"]], options=(),
                                  source="per_species_health.csv")
    assert 'href="per_species_health.csv"' in out


def test_the_caption_reuses_the_footnote_style(assets):
    """A download affordance of its own would be a CSS rule and a colour for a
    line that says what every other footnote on the page says. test_style.py
    fails on a class with no rule, so this is the cheap half of that check."""
    assert 'class="note"' in assets.source_note("x.csv")
    assert assets.source_note(None) == ""


def test_every_table_on_the_public_page_names_the_file_behind_it(external_page):
    """The gap this closes: six files were measured every build and reachable by
    nobody reading a page. A table with no file is the state to catch, so the
    check is over tables and not over links."""
    html, _ = external_page
    blocks = html.split("<details")[1:]
    missing = [re.sub(r"<[^>]+>", "", re.search(r"<summary[^>]*>(.*?)</summary>",
                                                b, re.DOTALL).group(1))[:60].strip()
               for b in blocks
               if "<table" in b and "This table as data" not in b]
    assert not missing, f"tables with no file named under them: {missing}"
