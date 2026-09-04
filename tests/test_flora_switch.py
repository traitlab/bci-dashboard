"""Switching the Pl@ntNet flora is one line in config.yaml.

Etienne asked for the BCNM micro-project over `k-central-america`, and the
reason that was not a one-line change is recorded here as tests. The slug used
to be typed in four places, one of them load-bearing: `run_log.py` printed the
endpoint as a literal and `history.model_tag_of` regexes the flora back out of
that printed line. Editing config.yaml alone left the page naming one flora
while the numbers came from another.
"""
import re


def config_naming(tmp_path, project):
    """A config.yaml carrying nothing but the key that is read."""
    p = tmp_path / "config.yaml"
    p.write_text("plantnet:\n"
                 f"  identify_url: https://my-api.plantnet.org/v2/identify/{project}\n"
                 "  identify_nb_results: 5\n", encoding="utf-8")
    return str(p)


def test_the_endpoint_is_read_rather_than_typed(core, tmp_path):
    assert core.identify_url(config_naming(tmp_path, "bcnm")) == (
        "https://my-api.plantnet.org/v2/identify/bcnm")


def test_the_project_is_the_last_segment_of_the_endpoint(core, tmp_path):
    """`checklist.py` opens `data/checklist_<EVAL_PROJECT>.json`, so this is
    what decides which species list proves a species out of scope."""
    url = core.identify_url(config_naming(tmp_path, "bcnm"))
    assert url.rstrip("/").rsplit("/", 1)[-1] == "bcnm"


def test_an_unreadable_config_falls_back_rather_than_crashing(core, tmp_path):
    """A last resort, not a default. The file is tracked, so its absence means
    the checkout is wrong, not that a choice was left unmade."""
    assert core.identify_url(str(tmp_path / "absent.yaml")) == core.IDENTIFY_URL_FALLBACK


def test_a_config_without_the_key_falls_back(core, tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("plantnet:\n  identify_nb_results: 5\n", encoding="utf-8")
    assert core.identify_url(str(p)) == core.IDENTIFY_URL_FALLBACK


def test_bcnm_has_a_name_ready_for_the_switch(core):
    """The page says "the {name} model". After the switch it must not still
    read "Central America"."""
    assert core.flora_name("bcnm") == "Barro Colorado Nature Monument"
    assert core.flora_name("k-central-america") == "Central America regional"


def test_an_unnamed_flora_reads_as_its_own_slug(core):
    """Worse English than a name, and better than a wrong name."""
    assert core.flora_name("k-somewhere-else") == "k-somewhere-else"


def test_the_model_tag_survives_a_flora_switch(history, tmp_path):
    """`history.model_tag_of` builds the published tag by regexing
    `identify/<slug>` out of run_log.txt. This is the whole trap: the tag has
    to follow config.yaml, because it is what the page prints as the identity
    of the model that produced every number on it."""
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "run_log.txt").write_text(
        "    endpoint : https://my-api.plantnet.org/v2/identify/bcnm\n"
        "    single_model_run_name 'v7.5-2026-09-01'\n", encoding="utf-8")
    assert history.model_tag_of(str(snap), "fallback") == "bcnm@v7.5-2026-09-01"


def test_the_run_log_endpoint_line_is_the_one_that_was_read(core):
    """The line `model_tag_of` reads back is printed from the constant, so the
    flora on the page and the flora that was called are the same string."""
    from conftest import REPO, _on_path

    src = (REPO / "dashboard" / "run_log.py").read_text(encoding="utf-8")
    assert "{IDENTIFY_URL}" in src
    with _on_path(REPO / "dashboard"):
        import run_log
        assert run_log.IDENTIFY_URL == core.IDENTIFY_URL
    assert re.search(r"identify/([A-Za-z0-9-]+)", core.IDENTIFY_URL).group(1) == \
        core.EVAL_PROJECT
