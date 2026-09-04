"""One photo, ingested: the step both fetch modes now run.

A local directory and a CSV of URLs differ in one thing, where the pixels come
from. They used to differ in two functions of forty lines each, and the copies
drifted: the URL path recorded the crop rectangle for months after the file
path had stopped. `process_image` takes the pixels as a callable so there is
one cache key, one crop, one pair of API calls and one atomic write.

The API is never called here. What is checked is the shape of the step around
it: the cache short-circuit, the geometry stamp, and the write that cannot
leave half a file behind.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def config(ingest):
    """The repo's own config.yaml, so the settings the step reads are the ones
    a run reads. A dict typed here would pass while config.yaml renamed a key."""
    return ingest.load_config()


@pytest.fixture
def call_recorder(ingest, monkeypatch):
    """Stands in for the network. Records what the step asked for."""
    calls = []

    # Shaped the way each endpoint answers, so the conversion the step runs
    # between them is exercised rather than stepped over.
    replies = {
        "call_survey": {"results": {"species": [{"binomial": "Hura crepitans"}]}},
        "call_identify": {"version": "2026-03-20 (7.5)", "results": [{
            "score": 0.8, "gbif": {"id": 3055009},
            "species": {"scientificNameWithoutAuthor": "Hura crepitans",
                        "commonNames": ["sandbox tree"]},
        }]},
        "call_embeddings": {"embedding": [0.1, 0.2, 0.3]},
    }

    def fake(fn, *args, **kwargs):
        calls.append(fn.__name__)
        return replies[fn.__name__]

    monkeypatch.setattr(ingest, "with_retry", fake)
    monkeypatch.setattr(ingest.time, "sleep", lambda _s: None)
    return calls


def test_a_cached_photo_is_not_fetched_again(ingest, tmp_path, call_recorder):
    """The resume promise the quota message makes: a rerun after the key runs
    dry costs nothing for the photos already answered."""
    (tmp_path / "a.jpg.json").write_text(json.dumps({"results": {"cached": 1}}))

    def no_pixels():
        raise AssertionError("a cached photo read its pixels")

    out = ingest.process_image("a.jpg", no_pixels, "key", {}, tmp_path)
    assert out == {"results": {"cached": 1}}
    assert call_recorder == []


def test_the_survey_path_takes_one_call_and_the_identify_path_two(
        ingest, tmp_path, jpeg, call_recorder, config):
    """Two calls stand in for the one the survey endpoint would answer, which
    is the whole reason the fallback exists."""
    ingest.process_image("s.jpg", lambda: jpeg(800, 600), "key", {}, tmp_path,
                         survey_url="https://example.invalid/survey")
    assert call_recorder == ["call_survey"]

    call_recorder.clear()
    ingest.process_image("i.jpg", lambda: jpeg(800, 600), "key", config,
                         tmp_path)
    assert call_recorder == ["call_identify", "call_embeddings"]


def test_the_cache_records_what_the_model_was_shown(
        ingest, tmp_path, jpeg, call_recorder, config):
    """Either mode, the same stamp: the frame it came from and the rectangle
    that was sent, so a later crown comparison never assumes the crop."""
    for name, frame in (("big.jpg", (4000, 3000)), ("small.jpg", (800, 600))):
        ingest.process_image(name, lambda f=frame: jpeg(*f), "key", config,
                             tmp_path)
        crop = json.loads((tmp_path / f"{name}.json").read_text())["crop"]
        assert (crop["frame_width"], crop["frame_height"]) == frame
        assert crop["unit"] == "photo"

    answer = json.loads((tmp_path / "big.jpg.json").read_text())
    assert answer["results"]["species"][0]["binomial"] == "Hura crepitans"
    box = answer["crop"]["box"]
    assert box == {"x_min": 1360, "y_min": 860, "x_max": 2640, "y_max": 2140}
    assert not list(tmp_path.glob("*.tmp")), "a temporary file was left behind"


def test_the_cache_records_which_model_answered(
        ingest, tmp_path, jpeg, call_recorder, config):
    """The model identity is read off the answer, not typed into config.yaml.

    config.yaml says ``v7.4-2026-03-27`` and the live endpoint reports
    ``2026-03-20 (7.5)``: an earlier date on a later version, because the
    config string dates the run rather than the model. A trend across model
    versions cannot be built on the string that disagrees with the API, so the
    cache keeps the API's own.
    """
    ingest.process_image("v.jpg", lambda: jpeg(800, 600), "key", config,
                         tmp_path)
    answer = json.loads((tmp_path / "v.jpg.json").read_text())
    assert answer["model_version"] == "2026-03-20 (7.5)"


def test_an_answer_without_a_version_is_still_cached(
        ingest, tmp_path, jpeg, call_recorder):
    """The survey endpoint names no version and older cached answers carry
    none. Absence is recorded as absence rather than as an empty string, so a
    later read can tell "not reported" from "reported as nothing"."""
    ingest.process_image("n.jpg", lambda: jpeg(800, 600), "key", {},
                         tmp_path, survey_url="https://example.invalid/survey")
    answer = json.loads((tmp_path / "n.jpg.json").read_text())
    assert "model_version" not in answer
