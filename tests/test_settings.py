"""Where a Labelbox identifier comes from, and what happens when it is absent.

The ids used to sit in the source of the two scripts that read them, so
pointing a checkout at a second workspace meant editing a tracked file. They
now resolve through one function, and the case that matters is the last one: a
value that resolves to nothing must stop the run rather than authenticate and
then ask Labelbox for None.

    .venv/bin/pytest tests/test_settings.py
"""

import pytest

CONFIG = {"labelbox": {"dataset_id": "from_config"}}


def test_the_environment_wins_over_the_config_default(settings, monkeypatch):
    monkeypatch.setenv("LABELBOX_DATASET_ID", "from_env")
    assert settings.setting("labelbox", "dataset_id",
                            env="LABELBOX_DATASET_ID", config=CONFIG) == "from_env"


def test_the_config_default_is_used_when_the_environment_is_silent(
        settings, monkeypatch):
    monkeypatch.delenv("LABELBOX_DATASET_ID", raising=False)
    assert settings.setting("labelbox", "dataset_id",
                            env="LABELBOX_DATASET_ID", config=CONFIG) == "from_config"


@pytest.mark.parametrize("config", [{}, {"labelbox": {}}, {"labelbox": None}])
def test_a_value_that_resolves_to_nothing_stops_the_run(
        settings, monkeypatch, config):
    monkeypatch.delenv("LABELBOX_DATASET_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        settings.setting("labelbox", "dataset_id",
                         env="LABELBOX_DATASET_ID", config=config)
    # The message has to name both places, or the reader has to guess which
    # one to edit.
    assert "LABELBOX_DATASET_ID" in str(exc.value)
    assert "labelbox.dataset_id" in str(exc.value)


def test_the_shipped_config_carries_both_ids(settings):
    labelbox = settings.load_config()["labelbox"]
    assert labelbox["dataset_id"] and labelbox["project_id"]


def test_the_api_key_has_no_config_default(settings, monkeypatch):
    """A credential is not a setting. It resolves from the environment or not
    at all, so config.yaml can never become a place a key is committed."""
    monkeypatch.delenv("LABELBOX_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        settings.api_key()
    assert "LABELBOX_API_KEY" in str(exc.value)


def test_the_run_log_provenance_block_matches_config_yaml(settings, core):
    """The pages publish which Pl@ntNet model answered, and it is a literal.

    `dashboard/` is stdlib only, so it cannot read config.yaml, and the
    provenance block in `run_log.py` types the endpoint and the model run name
    out by hand. `history.model_tag_of` then regexes both back out of
    run_log.txt, and that string is the `<code>` tag on the model-health page.
    So a Pl@ntNet version bump that updates config.yaml and nothing else makes
    every new snapshot publish the old model identity, silently. Nothing
    compared the two copies until this test.
    """
    import os

    plantnet = settings.load_config()["plantnet"]
    root = os.path.dirname(os.path.dirname(os.path.abspath(core.__file__)))
    src = open(os.path.join(root, "dashboard", "run_log.py"), encoding="utf-8").read()
    for key in ("identify_url", "single_model_run_name", "identify_organs"):
        value = str(plantnet[key])
        assert value in src, (
            f"config.yaml plantnet.{key} is {value!r}, and run_log.py does not "
            f"print it. The provenance block names the run that filled the cache, "
            f"so it has to say what config.yaml says.")
    assert plantnet["identify_nb_results"] == core.N_CANDIDATES, (
        "config.yaml asks Pl@ntNet for a different list length than "
        "core.N_CANDIDATES, which every page counts against.")
