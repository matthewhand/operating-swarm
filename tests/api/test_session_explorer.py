"""Session Explorer web UI: list_summaries data layer + the list/detail/API views."""
from __future__ import annotations

import json

import pytest
from django.urls import reverse

from swarm.core import responses_store


def _save(rid, *, status="completed", model="hybrid_team", output="hello", progress=None, created=1, owner="user:explorer"):
    """Persist a session; default owner matches auth_client principal (user:explorer)."""
    record = {
        "id": rid, "object": "response",
        "response": {
            "id": rid, "model": model, "status": status, "created_at": created,
            "output_text": output, "execution_ms": 42,
            "progress": progress or [],
        },
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": output}],
    }
    if owner is not None:
        record["owner"] = owner
    responses_store.save(record)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_RESPONSES_DIR", str(tmp_path))
    return tmp_path


def test_failed_session_preview_is_classified_as_error(store):
    """#1441: a failed response with only ``error.message`` is an error preview."""
    record = {
        "id": "resp_fail",
        "object": "response",
        "response": {
            "id": "resp_fail",
            "model": "hybrid_team",
            "status": "failed",
            "created_at": 9,
            "output_text": "",
            "error": {"message": "execution timed out"},
            "progress": [],
        },
        "messages": [],
        "owner": "user:explorer",
    }
    responses_store.save(record)
    rows = {row["id"]: row for row in responses_store.list_summaries()}
    assert rows["resp_fail"]["output_preview"] == "execution timed out"
    assert rows["resp_fail"]["preview_class"] == "error"
    _save("resp_ok", created=8, output="all good", status="completed")
    ok = {row["id"]: row for row in responses_store.list_summaries()}["resp_ok"]
    assert ok["preview_class"] == "reply"


@pytest.mark.django_db
def test_session_explorer_marks_error_previews(auth_client, store):
    responses_store.save({
        "id": "resp_fail",
        "object": "response",
        "owner": "user:explorer",
        "response": {
            "id": "resp_fail",
            "model": "hybrid_team",
            "status": "failed",
            "created_at": 3,
            "output_text": "",
            "error": {"message": "execution timed out"},
        },
        "messages": [],
    })
    resp = auth_client.get(reverse("session-explorer"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'data-preview="error"' in body
    assert "execution timed out" in body


def test_list_summaries_newest_first(store):
    _save("resp_a", created=1, output="first")
    _save("resp_b", created=5, output="second", progress=[{"role": "agent", "status": "completed"}])
    rows = responses_store.list_summaries()
    assert [r["id"] for r in rows] == ["resp_b", "resp_a"]  # newest first
    assert rows[0]["delegations"] == [{"role": "agent", "status": "completed"}]


@pytest.fixture
def auth_client(client, django_user_model):
    """Session Explorer requires login — authenticate the test client."""
    django_user_model.objects.create_user(username="explorer", password="x")
    assert client.login(username="explorer", password="x")
    return client


@pytest.mark.django_db
def test_session_explorer_requires_login(client, store):
    _save("resp_x", output="explorer-marker")
    resp = client.get(reverse("session-explorer"))
    assert resp.status_code in (302, 401, 403)


@pytest.mark.django_db
def test_session_explorer_list_view(auth_client, store):
    _save("resp_x", output="explorer-marker")
    resp = auth_client.get(reverse("session-explorer"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Session Explorer" in body and "resp_x" in body and "explorer-marker" in body
    assert 'data-preview="reply"' in body


@pytest.mark.django_db
def test_session_explorer_empty_state_is_owner_scoped(auth_client, store):
    """Empty copy must not imply a public/global session inventory."""
    resp = auth_client.get(reverse("session-explorer"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "No sessions for your account yet." in body
    assert "only sessions you own" in body
    assert "No sessions yet." not in body.split("<script>", 1)[0]


@pytest.mark.django_db
def test_session_detail_view_shows_delegations(auth_client, store):
    _save("resp_d", progress=[
        {"role": "agent", "status": "completed", "result": "coded", "model_used": "gpt-4o"},
        {"role": "auxiliary", "status": "failed", "error": "boom"},
    ])
    resp = auth_client.get(reverse("session-detail", kwargs={"response_id": "resp_d"}))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Delegation timeline" in body and "agent" in body and "auxiliary" in body
    assert "coded" in body and "boom" in body
    # Tablist a11y: named tabs/panels + labelled scrollable output region.
    assert 'role="tablist"' in body
    assert 'id="sd-graph-tab"' in body and 'aria-controls="sd-graph"' in body
    assert 'aria-selected="true"' in body
    assert 'role="tabpanel" aria-labelledby="sd-graph-tab"' in body
    assert 'role="tabpanel" aria-labelledby="sd-timeline-tab"' in body
    assert 'role="tabpanel" aria-labelledby="sd-output-tab"' in body
    assert 'aria-label="Session output"' in body
    assert 'role="alert"' in body  # failed delegation error surfaced to AT


@pytest.mark.django_db
def test_session_detail_404(auth_client, store):
    assert auth_client.get(reverse("session-detail", kwargs={"response_id": "resp_nope"})).status_code == 404


@pytest.mark.django_db
def test_session_list_api(auth_client, store):
    _save("resp_api")
    resp = auth_client.get(reverse("session-list-api"))
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert any(s["id"] == "resp_api" for s in data["sessions"])
    # Live feed contract: capped sessions + total metadata (UX fleet).
    assert "total" in data and "limit" in data and "shown" in data
    assert data["shown"] == len(data["sessions"])
    assert data["total"] >= data["shown"]


def _count_session_cards(html: str) -> int:
    """Count server-rendered session cards (exclude the live-poll JS template string)."""
    # Cards are only meaningful in the HTML body before the live-refresh script.
    head = html.split("<script>", 1)[0]
    return head.count('class="se-card" data-status=')


@pytest.mark.django_db
def test_session_explorer_respects_default_limit_and_banner(auth_client, store):
    """First paint must cap cards at default limit=50 and surface truncation."""
    # 60 sessions → default limit 50 should truncate.
    for i in range(60):
        _save(f"resp_lim_{i:03d}", created=i + 1, output=f"out-{i}")
    resp = auth_client.get(reverse("session-explorer"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'data-limit="50"' in body
    assert "Showing newest" in body
    assert 'id="se-shown">50</strong>' in body
    assert 'id="se-total-banner">60</strong>' in body
    assert _count_session_cards(body) == 50
    # True total must be 60, not silently capped at store default 200.
    assert 'id="se-total">60</strong>' in body


@pytest.mark.django_db
def test_session_explorer_total_beyond_store_default_200(auth_client, store):
    """Totals must not under-report when store size exceeds list_summaries default 200."""
    for i in range(210):
        _save(f"resp_big_{i:03d}", created=i + 1, output=f"big-{i}")
    resp = auth_client.get(reverse("session-explorer") + "?limit=50")
    assert resp.status_code == 200
    body = resp.content.decode()
    # Total chip / banner must show 210, not 200.
    assert 'id="se-total">210</strong>' in body
    assert 'id="se-total-banner">210</strong>' in body
    assert _count_session_cards(body) == 50


@pytest.mark.django_db
def test_session_list_api_honours_limit_query(auth_client, store):
    for i in range(30):
        _save(f"resp_api_lim_{i:03d}", created=i + 1)
    resp = auth_client.get(reverse("session-list-api") + "?limit=10")
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["limit"] == 10
    assert data["shown"] == 10
    assert data["total"] == 30
    assert data["truncated"] is True
    assert len(data["sessions"]) == 10
    # Newest first — highest created wins.
    assert data["sessions"][0]["id"] == "resp_api_lim_029"


@pytest.mark.django_db
def test_live_poll_feed_stays_capped_like_first_paint(auth_client, store):
    """Simulated live poll: card count stays <= page limit after API refresh.

    Reproduces the skeptic bug where session_list_api returned up to 200 and
    client render() replaced the 50-card first paint with the full feed.
    """
    for i in range(80):
        _save(f"resp_poll_{i:03d}", created=i + 1, output=f"p-{i}")

    # First paint
    page = auth_client.get(reverse("session-explorer"))
    assert page.status_code == 200
    body = page.content.decode()
    assert _count_session_cards(body) == 50
    assert 'data-limit="50"' in body

    # Live poll uses same default limit as the page (JS appends ?limit= from data-limit)
    feed = auth_client.get(reverse("session-list-api") + "?limit=50")
    assert feed.status_code == 200
    data = json.loads(feed.content)
    assert len(data["sessions"]) == 50
    assert data["total"] == 80
    assert data["truncated"] is True
    assert data["shown"] == 50
    # Even without client limit, server must not return the old uncapped dump.
    feed_default = auth_client.get(reverse("session-list-api"))
    data_default = json.loads(feed_default.content)
    assert len(data_default["sessions"]) == 50
    assert data_default["limit"] == 50
