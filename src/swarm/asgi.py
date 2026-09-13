"""ASGI config for the swarm project.

Exposes the ``application`` referenced by ``settings.ASGI_APPLICATION``:

- ``http``      -> the regular Django ASGI application
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
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")

# Initialise Django (apps/settings) *before* importing anything that touches
# the ORM or settings — swarm.routing imports the chat consumer, which
# imports models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from swarm.routing import websocket_urlpatterns  # noqa: E402
from swarm.ws_origin import SwarmWebsocketOriginValidator  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": SwarmWebsocketOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
