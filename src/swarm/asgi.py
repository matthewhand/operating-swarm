"""ASGI config for the swarm project.

Exposes the ``application`` referenced by ``settings.ASGI_APPLICATION``:

- ``http``      -> Django ASGI. Static is served by
  ``whitenoise.middleware.WhiteNoiseMiddleware`` (see ``settings.MIDDLEWARE``),
  which works with ``DEBUG=false`` as well as in development — so uvicorn
  answers ``/static/*.css`` whether or not a proxy sits in front of it.
  Before #423 this branch was wrapped in ``ASGIStaticFilesHandler`` only when
  ``DEBUG``, which left production with a Django 404 HTML page for every asset.
- ``websocket`` -> Channels routing for the chat consumer, wrapped in
  ``SwarmWebsocketOriginValidator`` (same-origin LAN Host/Origin, plus
  concrete ALLOWED_HOSTS; cross-site Origins are denied even when ``*``
  is listed) and ``AuthMiddlewareStack`` (the consumer requires an
  authenticated Django session).

Run it with any ASGI server, e.g.::

    daphne -b 127.0.0.1 -p 8000 swarm.asgi:application
    uvicorn swarm.asgi:application

``manage.py runserver`` also serves it (including /ws/ routes) because
``daphne`` is registered in ``INSTALLED_APPS``.

``build_application()`` builds a fresh stack; the module-level ``application``
is one such stack. Tests use the factory to exercise the app under settings
(``DEBUG``, ``STATIC_ROOT``) the single module-level instance cannot take on.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")

# Initialise Django (apps/settings) *before* importing anything that touches
# the ORM or settings — swarm.routing imports the chat consumer, which
# imports models.
get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from swarm.routing import websocket_urlpatterns  # noqa: E402
from swarm.ws_origin import SwarmWebsocketOriginValidator  # noqa: E402


def build_application() -> ProtocolTypeRouter:
    """Build the http + websocket ASGI stack.

    A fresh Django ASGI handler is created per call, which is what makes the
    result reflect the settings in force *now* — ``ASGIHandler.__init__`` is
    where the middleware chain (and therefore WhiteNoise's view of DEBUG and
    STATIC_ROOT) is resolved.
    """
    return ProtocolTypeRouter(
        {
            "http": get_asgi_application(),
            "websocket": SwarmWebsocketOriginValidator(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
            ),
        }
    )


application = build_application()
