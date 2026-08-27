"""The Labelbox deep link is read from a file, never guessed.

A data row opens only inside a project it belongs to, so a link is only
correct where an export stated both halves. These tests pin the two halves of
that contract: the URL shape, and silence rather than a guess when the pair is
not known.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "dashboard"))

import core as hc  # noqa: E402


def write(tmp_path, *rows):
    p = tmp_path / "data_row_ids.csv"
    body = "global_key,data_row_id,project_id\n" + "".join(
        ",".join(r) + "\n" for r in rows)
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_a_missing_file_is_an_empty_map_not_an_error(tmp_path):
    assert hc.labelbox_urls(str(tmp_path / "absent.csv")) == {}


def test_a_known_pair_builds_the_project_scoped_url(tmp_path):
    urls = hc.labelbox_urls(write(tmp_path, ("comb_a.JPG", "dr1", "pr1")))
    assert urls == {"comb_a.JPG": "https://app.labelbox.com/projects/pr1/data-rows/dr1"}


@pytest.mark.parametrize("row", [("comb_a.JPG", "", "pr1"),
                                 ("comb_a.JPG", "dr1", ""),
                                 ("comb_a.JPG", "", "")])
def test_a_half_known_row_yields_no_link_rather_than_a_broken_one(tmp_path, row):
    assert hc.labelbox_urls(write(tmp_path, row)) == {}


def test_rows_are_independent(tmp_path):
    urls = hc.labelbox_urls(write(tmp_path, ("comb_a.JPG", "dr1", "pr1"),
                                  ("comb_b.JPG", "", "pr1"),
                                  ("comb_c.JPG", "dr3", "pr2")))
    assert sorted(urls) == ["comb_a.JPG", "comb_c.JPG"]
