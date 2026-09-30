"""#1228 — TrueForge external sessions hydrate instead of rendering blank.

Picking a TrueForge session created outside Operating Swarm lands on
``/chat?remote=trueforge&session=<sid>`` and GETs
``/chat/thread/?agent=remote:trueforge&conversation_id=remote-trueforge-<sid>``.
Django has no local rows for that conversation, so the window rendered
``messages: []`` — while Herdr's chat_thread branch backfills recent pane
text, TrueForge had no equivalent. The view now asks the TrueForge harness
for the session's turns (``GET /api/v1/sessions/{sid}/turns``) and maps the
model events into transcript rows; a harness miss stays an honest empty.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

# Must precede any remote_impls import: remotes' wiring installs the impl
# attribute shims at import time, and importing the impl first would
# re-enter the partially-initialized module (import-order cycle).
from swarm.core import remotes  # noqa: F401

TF_CID = "remote-trueforge-01abc"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="tf-hydrate-user", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="tf-hydrate-user", password="pw")
    return c


def _turn(turn_id: str, user_text: str, reply_text: str) -> dict:
    return {
        "id": turn_id,
        "input": [{"type": "user.message", "content": user_text}],
        "events": [
            {"type": "model.message", "content": reply_text},
        ],
        "state": {"status": "completed"},
    }


@pytest.mark.django_db
def test_trueforge_session_hydrates_turns_from_harness(client, user):
    """Local miss + TrueForge reachable → harness turns become transcript rows."""
    fetched: dict = {}

    def fake_http_json(method, url, **kwargs):
        fetched["method"] = method
        fetched["url"] = url
        if url.endswith("/turns"):
            return mock.Mock(
                status=200,
                body={"data": [_turn("t1", "hi forge", "Forge says hi.")]},
            )
        return mock.Mock(status=404, body={})

    with mock.patch("swarm.core.remote_impls.trueforge.R.http_json", side_effect=fake_http_json):
        resp = client.get(f"/chat/thread/?agent=remote:trueforge&conversation_id={TF_CID}")
    assert resp.status_code == 200
    body = resp.json()
    contents = [row.get("content") for row in body["messages"]]
    assert "hi forge" in contents
    assert "Forge says hi." in contents
    assert fetched["method"] == "GET"
    assert TF_CID[len("remote-trueforge-"):] in fetched["url"]


@pytest.mark.django_db
def test_trueforge_hydrate_is_honest_when_harness_unreachable(client):
    """Harness down → still an empty thread, no fabricated rows, no 500."""
    with mock.patch(
        "swarm.core.remote_impls.trueforge.R.http_json",
        side_effect=OSError("conn refused"),
    ):
        resp = client.get(f"/chat/thread/?agent=remote:trueforge&conversation_id={TF_CID}")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


@pytest.mark.django_db
def test_local_rows_still_win_over_harness_backfill(client, user):
    """Persisted turns exist → the harness is not consulted for content."""
    from swarm.core import chat_store

    chat_store.save(
        chat_store.user_key_for(user),
        "remote_harness",
        [{"role": "user", "content": "local row"}],
        conversation_id=TF_CID,
        session_id=TF_CID,
    )
    with mock.patch(
        "swarm.core.remote_impls.trueforge.R.http_json",
        side_effect=AssertionError("harness must not be fetched when local rows exist"),
    ) as probe:
        resp = client.get(f"/chat/thread/?agent=remote:trueforge&conversation_id={TF_CID}")
    assert resp.status_code == 200
    contents = [row.get("content") for row in resp.json()["messages"]]
    assert "local row" in contents
    assert probe.call_count == 0
