"""The labelling team's copy of the queue page, after it was folded in.

It used to be a second page, label_queue_team.html, built with ``--team``.
Its commands now sit in one closed block on the queue page, and the old
address is a redirect to that block, so a link saved to it still works.
"""
import re

from conftest import REPO

STUB = "label_queue_team.html"
TARGET = "label_queue_dashboard.html#sending-a-batch"


def _stub_path(stdout):
    m = re.search(r"wrote\s+(\S+" + re.escape(STUB) + r")\s+\(redirect to (\S+)\)", stdout)
    assert m, f"the internal build printed no redirect line:\n{stdout}"
    return m.group(1), m.group(2)


def test_the_internal_build_writes_the_redirect_beside_the_page(internal_page):
    _html, stdout = internal_page
    path, to = _stub_path(stdout)
    assert to == TARGET
    with open(path, encoding="utf-8") as f:
        stub = f.read()
    assert f'<meta http-equiv="refresh" content="0; url={TARGET}">' in stub
    # A browser that ignores the refresh still has a link to follow.
    assert f'<a href="{TARGET}">' in stub


def test_the_redirect_lands_on_a_block_the_page_carries(internal_page, queue_panels):
    """The anchor is the team block's id, and the block starts closed: the
    page's script opens it when the address names it."""
    html, _stdout = internal_page
    assert TARGET.split("#")[1] == queue_panels.TEAM_BLOCK_ID
    assert html.count(f'id="{queue_panels.TEAM_BLOCK_ID}"') == 1
    assert f'<details class="more" id="{queue_panels.TEAM_BLOCK_ID}">' in html


def test_the_redirect_is_still_published():
    """Taking it off the publish list would turn every saved link into a 404."""
    src = (REPO / "bin" / "publish_pages.sh").read_text(encoding="utf-8")
    pages = re.search(r'^PAGES="([^"]*)"', src, re.MULTILINE)
    assert pages and STUB in pages.group(1).split()


def test_no_builder_takes_the_old_flag():
    for script in ("page.py", "build_internal.py", "build_external.py"):
        src = (REPO / "dashboard" / script).read_text(encoding="utf-8")
        assert "--team" not in src, script
    assert "--team" not in (REPO / "bin" / "refresh.sh").read_text(encoding="utf-8")
