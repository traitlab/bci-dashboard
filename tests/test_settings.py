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
