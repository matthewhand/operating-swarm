"""GET /v1/capabilities/seats/ publishes declared seat capabilities (#1324)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


def test_get_seat_capabilities(api_client):
    response = api_client.get("/v1/capabilities/seats/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "seat_capabilities"
    assert body["seat_capabilities"]["api"]["compact"]["enabled"] is True
    assert body["seat_capabilities"]["api"]["compact"]["label"] == "thread compact"
    assert body["seat_capabilities"]["cli"]["compact"]["enabled"] is False
    assert body["seat_capabilities"]["team"]["coordination"]["enabled"] is True
    assert body["labels"]["list"] == "session list"
    assert "export_argv" not in str(body["cli"])
    assert "sk-" not in str(body)


def test_get_seat_capabilities_without_slash(api_client):
    response = api_client.get("/v1/capabilities/seats")
    assert response.status_code == 200
    assert response.json()["object"] == "seat_capabilities"
