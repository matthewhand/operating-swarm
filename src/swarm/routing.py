"""Websocket URL routing for the swarm project.

Kept separate from ``swarm.urls`` (HTTP) so that ``swarm.asgi`` can build a
``URLRouter`` without importing the (much heavier) HTTP urlconf. Routes
mirror the clients:

- Django template UI (``templates/chat.html`` HTMx ``ws-connect``) and the
  legacy SPA path (``webui/frontend/src/lib/chatWs.ts``):

      ws(s)://<host>/ws/ai-demo/<conversation_id>/

- Whole-SPA multiplex socket (ADR-017 PR-3, REQ-925 / #1118):

      ws(s)://<host>/ws/spa/
"""

from django.urls import path

from swarm.consumers import DjangoChatConsumer
from swarm.spa_multiplex import SpaMultiplexConsumer

websocket_urlpatterns = [
    path("ws/ai-demo/<str:conversation_id>/", DjangoChatConsumer.as_asgi()),
    path("ws/spa/", SpaMultiplexConsumer.as_asgi()),
]
