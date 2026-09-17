"""Issue #423 — production serves /static/ without DEBUG and without a proxy.

#419/#420 made uvicorn serve /static/ when ``DEBUG`` was on. Production
(``DEBUG=false`` — the systemd and docker/LAN deployments) still answered every
asset with a Django 404, and neither deployment has a proxy in front of it to
take over: the docker/LAN one binds uvicorn directly.

The ASGI http branch is therefore no longer conditionally wrapped in
``ASGIStaticFilesHandler``; static is served by
``whitenoise.middleware.WhiteNoiseMiddleware`` in every mode. These proves drive
a real HTTP GET through the real ASGI stack to hold that down.

``build_application()`` builds a fresh stack per call, which is what lets a test
observe the app under a ``DEBUG`` / ``STATIC_ROOT`` combination the single
module-level ``application`` cannot take on.
"""

from __future__ import annotations

import pytest
from channels.testing import HttpCommunicator
from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.management import call_command
from django.test import override_settings

from swarm.asgi import application, build_application

ASSET = "/static/css/operator.css"
# Loopback Host so ALLOWED_HOSTS is satisfied.
HOST_HEADERS = [(b"host", b"localhost")]
TIMEOUT = 5


async def _asgi_get(app, path: str) -> tuple[int, dict[bytes, bytes], bytes]:
    """Return ``(status, headers, body)`` for a GET driven through ASGI.

    ``HttpCommunicator.get_response`` asserts a bytes ``body`` on every chunk,
    but the terminating chunk is ``{"type": "http.response.body"}`` with no
    ``body`` key at all, so it raises ``KeyError`` on any streamed or file
    response — which is what a static asset is. The messages are assembled here
    instead, and the app is exercised exactly the same way.
    """
    communicator = HttpCommunicator(app, "GET", path, headers=HOST_HEADERS)
    await communicator.send_input({"type": "http.request", "body": b""})

    start = await communicator.receive_output(timeout=TIMEOUT)
    assert start["type"] == "http.response.start"
    headers = {key.lower(): value for key, value in start["headers"]}

    body = b""
    while True:
        chunk = await communicator.receive_output(timeout=TIMEOUT)
        assert chunk["type"] == "http.response.body"
        body += chunk.get("body", b"")
        if not chunk.get("more_body", False):
            break
    return start["status"], headers, body


def test_the_http_branch_carries_no_debug_only_static_handler():
    """The #423 defect: static that only exists when DEBUG is on.

    Django's ``serve()``-based handler is DEBUG-only by design and is not meant
    to face a network, so it must not be what production relies on.
    """
    http_app = application.application_mapping["http"]
    assert not isinstance(http_app, ASGIStaticFilesHandler)
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in settings.MIDDLEWARE


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_debug_false_serves_the_asset():
    """The shipped configuration: DEBUG off, no proxy, asset still 200 text/css."""
    with override_settings(DEBUG=False):
        app = build_application()
        status, headers, body = await _asgi_get(app, ASSET)

    assert status == 200
    assert b"text/css" in headers[b"content-type"]
    # The body is the stylesheet, not an error page that happens to be 200.
    assert body.lstrip().startswith(b"/*")
    assert b"{" in body


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_debug_false_serves_from_static_root_after_collectstatic(tmp_path):
    """The documented collectstatic path: STATIC_ROOT alone is enough.

    Finders are switched off for this case, so the 200 can only have come from
    the collected directory.
    """
    static_root = tmp_path / "staticfiles"
    with override_settings(
        DEBUG=False, STATIC_ROOT=static_root, WHITENOISE_USE_FINDERS=False
    ):
        call_command("collectstatic", interactive=False, verbosity=0)
        assert (static_root / "css" / "operator.css").is_file(), (
            "collectstatic did not place the asset"
        )

        app = build_application()
        status, headers, _ = await _asgi_get(app, ASSET)

    assert status == 200
    assert b"text/css" in headers[b"content-type"]


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_nothing_else_serves_static_when_whitenoise_cannot(tmp_path):
    """Control: no STATIC_ROOT contents and no finders means a 404.

    Without this, a passing ``200`` above would not distinguish "WhiteNoise
    served it" from "some other handler was still installed".
    """
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    with override_settings(
        DEBUG=False, STATIC_ROOT=empty_root, WHITENOISE_USE_FINDERS=False
    ):
        app = build_application()
        status, _, _ = await _asgi_get(app, ASSET)

    assert status == 404


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_debug_true_still_serves_the_asset():
    """The dev path #420 established keeps working through the same mechanism."""
    with override_settings(DEBUG=True):
        app = build_application()
        status, headers, _ = await _asgi_get(app, ASSET)

    assert status == 200
    assert b"text/css" in headers[b"content-type"]
