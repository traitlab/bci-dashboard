"""One way to post an image, one way to retry it, one way to read a 429.

Three scripts call Pl@ntNet: predict/photo.py, predict/embed.py and
predict/ingest_photos.py. Each used to carry its own request, its own retry
loop and its own reading of HTTP 429, and the copies did not agree. One read
the quota answer as an ordinary failure and retried it twice before giving up,
which turns a run that could have been resumed into a run that lost its place.

They now share `post_image` and `with_retry` in photo.py. What is checked here
is the behaviour that decides whether a long run survives: a spent key stops
immediately, and a dropped connection does not.

    .venv/bin/pytest tests/test_api_calls.py
"""

from __future__ import annotations

import pytest


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self._payload = payload if payload is not None else {"ok": True}

    def json(self):
        return self._payload


class Wire(list):
    """The requests the code would have sent, and the answers it will get."""

    def __init__(self):
        super().__init__()
        self.replies = []


@pytest.fixture
def posted(photo, monkeypatch):
    """Every request the code would have sent, without sending one."""
    wire = Wire()

    def fake_post(url, **kwargs):
        wire.append({"url": url, **kwargs})
        return wire.replies.pop(0) if wire.replies else FakeResponse()

    monkeypatch.setattr(photo.requests, "post", fake_post)
    monkeypatch.setattr(photo.time, "sleep", lambda _s: None)
    return wire


def test_a_spent_key_stops_the_run_instead_of_being_retried(photo, posted):
    """The quota answer is the one failure worth stopping on: the run resumes
    from its cache, and three more requests would return the same 429."""
    posted.replies.extend([FakeResponse(429, headers={"X-RateLimit-Remaining": "0"})])

    with pytest.raises(photo.QuotaExceededError) as raised:
        photo.with_retry(photo.post_image, "https://example.invalid/identify",
                         "images", b"jpeg", "a.jpg", params={})

    assert len(posted) == 1, "a 429 was retried"
    assert "Remaining: 0" in str(raised.value), (
        "the message drops the header that says how much of the key is left")


def test_a_dropped_connection_is_tried_again(photo, posted):
    """Runs here are thousands of images long, so one bad moment on the wire
    is not a reason to lose the rest of them."""
    posted.replies.extend([FakeResponse(503, text="upstream busy"),
                           FakeResponse(200, payload={"embeddings": [0.5]})])

    out = photo.with_retry(photo.post_image, "https://example.invalid/embeddings",
                           "image", b"jpeg", "a.jpg", params={})

    assert out == {"embeddings": [0.5]}
    assert len(posted) == 2


def test_a_failure_that_keeps_happening_is_raised_with_what_the_server_said(
        photo, posted):
    posted.replies.extend([FakeResponse(500, text="boom") for _ in range(photo.MAX_RETRIES)])

    with pytest.raises(RuntimeError, match="HTTP 500: boom"):
        photo.with_retry(photo.post_image, "https://example.invalid/identify",
                         "images", b"jpeg", "a.jpg", params={})

    assert len(posted) == photo.MAX_RETRIES, (
        f"tried {len(posted)} times, MAX_RETRIES is {photo.MAX_RETRIES}")


def test_identify_sends_every_setting_the_caller_was_given(photo, posted):
    """The request is built in one place, so a setting added to config.yaml
    reaches the endpoint on every path that reads it."""
    photo.call_identify_api(b"jpeg", "a.jpg", "https://example.invalid/identify",
                            "key", 5, "auto", "en")

    sent = posted[0]
    assert sent["params"] == {"api-key": "key", "nb-results": 5,
                              "no-reject": "true",
                              "include-related-images": "false", "lang": "en"}
    assert sent["data"] == {"organs": "auto"}
    assert next(iter(sent["files"]))[0] == "images", (
        "identify takes the plural field name; the singular returns HTTP 400")


@pytest.mark.parametrize("module,call", [
    ("embed", "call_embeddings_api"),
    ("ingest", "call_embeddings"),
    ("ingest", "call_identify"),
    ("ingest", "call_survey"),
])
def test_no_script_posts_an_image_its_own_way(request, photo, module, call):
    """A second post is a second reading of 429, and that is the copy that
    cost a run its place in the queue."""
    fn = getattr(request.getfixturevalue(module), call)
    source = fn.__code__.co_consts, fn.__code__.co_names
    assert "post_image" in fn.__code__.co_names or "with_retry" in fn.__code__.co_names, (
        f"{module}.{call} does not go through photo.post_image: {source}")
