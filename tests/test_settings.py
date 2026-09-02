"""Where a Labelbox identifier comes from, and what happens when it is absent.

The ids used to sit in the source of the two scripts that read them, so
pointing a checkout at a second workspace meant editing a tracked file. They
now resolve through one function, and the case that matters is the last one: a
value that resolves to nothing must stop the run rather than authenticate and
then ask Labelbox for None.

    .venv/bin/pytest tests/test_settings.py
"""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

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


def test_config_yaml_carries_every_request_setting_the_fetchers_index(settings):
    """The fetch scripts index these rather than defaulting them.

    A `.get("identify_organs", "auto")` reads as a safety net and is really a
    second copy: it kept `predict/ingest_photos.py` asking the old way after
    the setting moved. Indexing turns a missing key into a loud KeyError at the
    top of a run, which is what this test makes sure config.yaml never causes.
    """
    plantnet = settings.load_config()["plantnet"]
    for key in ("identify_url", "embeddings_api_url", "identify_nb_results",
                "identify_organs", "identify_lang", "single_model_run_name"):
        assert key in plantnet, (
            f"config.yaml has no plantnet.{key}, and predict/ indexes it; a fetch "
            f"run would stop with a KeyError before its first call.")


def _source(*parts: str) -> str:
    return (REPO.joinpath(*parts)).read_text(encoding="utf-8")


def test_no_fetcher_types_a_plantnet_endpoint_of_its_own(settings):
    """config.yaml is the only place an endpoint is written down.

    `predict/embed.py` used to carry the embeddings URL as a constant while
    `predict/ingest_photos.py` read the same URL from config, so a Pl@ntNet
    version move would have left one of the two posting to the old endpoint
    and mixing vectors from two model versions in one file.
    """
    urls = {k: v for k, v in settings.load_config()["plantnet"].items()
            if str(v).startswith("http")}
    assert urls, "config.yaml names no Pl@ntNet endpoint"
    for source in sorted(REPO.glob("predict/*.py")) + sorted(REPO.glob("labelling/*.py")):
        text = source.read_text(encoding="utf-8")
        for key, url in urls.items():
            assert url not in text, (
                f"{source.name} types plantnet.{key}, which config.yaml already "
                f"carries. Read it from there, the way embed.py does.")


def test_photo_documents_exactly_the_settings_it_indexes():
    """photo.py's header lists the config it needs, and that list is a copy.

    It had already drifted: the list held four settings under a sentence
    saying three. A reader trimming config.yaml to the documented set would
    have stopped the run with a KeyError.
    """
    import re

    src = _source("predict", "photo.py")
    indexed = set(re.findall(r'pn_cfg\["(\w+)"\]', src))
    documented = set(re.findall(r"^  plantnet\.(\w+)", src, re.M))
    assert indexed and indexed == documented, (
        f"predict/photo.py indexes {sorted(indexed)} and its header lists "
        f"{sorted(documented)}. The header is the contract for why nothing "
        f"here may carry a default, so it has to name the same settings.")


def test_rank_unsent_reads_the_column_the_label_writers_write():
    """The command in rank_unsent.py's own header has to run as printed.

    Its default named `lb_label`, which is an export column, not a column of
    the labels file the header points it at, so the documented backtest exited
    on a missing column.
    """
    import re

    default = re.search(r'"--species-col", default="(\w+)"',
                        _source("labelling", "rank_unsent.py")).group(1)
    written = re.search(r'writerow\(\["global_key", "(\w+)"\]\)',
                        _source("labelling", "gt_from_export.py")).group(1)
    assert default == written, (
        f"rank_unsent.py reads {default!r} and gt_from_export.py writes "
        f"{written!r}, so --species-csv on the merged labels stops the run.")


def test_both_identify_paths_read_the_same_settings():
    """Two scripts call identify, and each builds the request itself.

    `predict/ingest_photos.py` had no `lang` in its parameters at all, so it
    took Pl@ntNet's default language for common names while `predict/photo.py`
    asked for the configured one. The same slip had already happened once with
    `organs`, which is why photo.py carries a comment about it.
    """
    import re

    def identify_settings(relative: str) -> set[str]:
        src = _source(*relative.split("/"))
        return {name for name in
                re.findall(r'(?:pn_cfg|config\["plantnet"\])\["(\w+)"\]', src)
                if name.startswith("identify_")}

    photo = identify_settings("predict/photo.py")
    ingest = identify_settings("predict/ingest_photos.py")
    assert photo and photo == ingest, (
        f"photo.py reads {sorted(photo)} and ingest_photos.py reads "
        f"{sorted(ingest)}. Both send the same endpoint the same question, so "
        f"a setting one of them skips is a setting that silently does nothing.")
