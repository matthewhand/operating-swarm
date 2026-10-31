"""Unit tests for swarm.core.url_utils."""

from __future__ import annotations

from django.http import HttpResponse
from django.urls import URLPattern

from swarm.core.url_utils import ApiRouter, twin_path


def dummy_view(_request):
    return HttpResponse("ok")


def test_twin_path_default_naming():
    patterns = twin_path("v1/runtime", dummy_view, name="runtime-mode")
    assert len(patterns) == 2
    assert all(isinstance(p, URLPattern) for p in patterns)

    p_no_slash, p_slash = patterns
    assert str(p_no_slash.pattern) == "v1/runtime"
    assert p_no_slash.name == "runtime-mode-no-slash"

    assert str(p_slash.pattern) == "v1/runtime/"
    assert p_slash.name == "runtime-mode"


def test_twin_path_no_slash_suffix_heuristic():
    patterns = twin_path("v1/chat/retention/action", dummy_view, name="chat-retention-action-v1-no-slash")
    p_no_slash, p_slash = patterns

    assert str(p_no_slash.pattern) == "v1/chat/retention/action"
    assert p_no_slash.name == "chat-retention-action-v1-no-slash"

    assert str(p_slash.pattern) == "v1/chat/retention/action/"
    assert p_slash.name == "chat-retention-action-v1"


def test_twin_path_slash_suffix_heuristic():
    patterns = twin_path("v1/blueprints/upload", dummy_view, name="blueprint-upload-slash")
    p_no_slash, p_slash = patterns

    assert str(p_no_slash.pattern) == "v1/blueprints/upload"
    assert p_no_slash.name == "blueprint-upload"

    assert str(p_slash.pattern) == "v1/blueprints/upload/"
    assert p_slash.name == "blueprint-upload-slash"


def test_twin_path_explicit_names():
    patterns = twin_path("chat", dummy_view, slash_name="spa_chat_slash", no_slash_name="spa_chat")
    p_no_slash, p_slash = patterns

    assert str(p_no_slash.pattern) == "chat"
    assert p_no_slash.name == "spa_chat"

    assert str(p_slash.pattern) == "chat/"
    assert p_slash.name == "spa_chat_slash"


def test_twin_path_without_names():
    patterns = twin_path("health", dummy_view)
    p_no_slash, p_slash = patterns

    assert str(p_no_slash.pattern) == "health"
    assert p_no_slash.name is None

    assert str(p_slash.pattern) == "health/"
    assert p_slash.name is None


def test_api_router():
    router = ApiRouter(prefix="v1")
    router.register("models", dummy_view, name="models-list")
    router.register("blueprints", dummy_view, name="blueprints-list")

    urls = router.urls
    assert len(urls) == 4

    assert str(urls[0].pattern) == "v1/models"
    assert urls[0].name == "models-list-no-slash"
    assert str(urls[1].pattern) == "v1/models/"
    assert urls[1].name == "models-list"

    assert str(urls[2].pattern) == "v1/blueprints"
    assert urls[2].name == "blueprints-list-no-slash"
    assert str(urls[3].pattern) == "v1/blueprints/"
    assert urls[3].name == "blueprints-list"
