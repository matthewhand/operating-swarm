"""Hermes external sessions hydrate instead of rendering blank.

Picking a Hermes gateway session lands on
``/chat?remote=hermes&session=<sid>`` and GETs
``/chat/thread/?agent=remote:hermes&conversation_id=remote-hermes-<sid>``.
Django has no local rows for that conversation, so the view asks the Hermes
gateway for the session's messages (``GET /api/sessions/{sid}/messages``) and
maps them into transcript rows; a harness miss stays an honest empty.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

# Must precede any remote_impls import: remotes' wiring installs the impl
# attribute shims at import time (import-order cycle).
from swarm.core import remotes  # noqa: F401

H_CID = "remote-hermes-run_1"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="hermes-hydrate-user", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="hermes-hydrate-user", password="pw")
    return c


@pytest.mark.django_db
def test_hermes_session_hydrates_turns_from_gateway(client):
    fetched: dict = {}

    def fake_http_json(method, url, **kwargs):
        fetched["method"] = method
        fetched["url"] = url
        if url.endswith("/messages"):
            return mock.Mock(
                status=200,
                body={
                    "object": "list",
                    "session_id": "run_1",
                    "data": [
                        {"role": "user", "content": "Remember ZEBRA-42"},
                        {"role": "assistant", "content": "STORED"},
                        {"role": "tool", "tool_name": "terminal", "content": "{}"},
                    ],
                },
            )
        return mock.Mock(status=404, body={})

    with mock.patch("swarm.core.remote_impls.hermes.R.http_json", side_effect=fake_http_json):
        resp = client.get(f"/chat/thread/?agent=remote:hermes&conversation_id={H_CID}")
    assert resp.status_code == 200
    body = resp.json()
    contents = [row.get("content") for row in body["messages"]]
    assert "Remember ZEBRA-42" in contents
    assert "STORED" in contents
    assert fetched["method"] == "GET"
    assert "run_1" in fetched["url"]


@pytest.mark.django_db
def test_hermes_hydrate_is_honest_when_gateway_unreachable(client):
    with mock.patch(
        "swarm.core.remote_impls.hermes.R.http_json",
        side_effect=OSError("conn refused"),
    ):
        resp = client.get(f"/chat/thread/?agent=remote:hermes&conversation_id={H_CID}")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


@pytest.mark.django_db
def test_local_rows_still_win_over_hermes_backfill(client, user):
    from swarm.core import chat_store

    chat_store.save(
        chat_store.user_key_for(user),
        "remote_harness",
        [{"role": "user", "content": "local row"}],
        conversation_id=H_CID,
        session_id=H_CID,
    )
    with mock.patch(
        "swarm.core.remote_impls.hermes.R.http_json",
        side_effect=AssertionError("gateway must not be fetched when local rows exist"),
    ) as probe:
        resp = client.get(f"/chat/thread/?agent=remote:hermes&conversation_id={H_CID}")
    assert resp.status_code == 200
    contents = [row.get("content") for row in resp.json()["messages"]]
    assert "local row" in contents
    assert probe.call_count == 0
