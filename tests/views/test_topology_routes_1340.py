"""#1340 — every ``/v1`` API route must actually be registered in ``urls.py``.

Two separate defects hid behind the same symptom (a ``text/html`` 404 that
looks like the SPA catch-all, but is really Django's default page_not_found
because the SPA regex at the bottom of ``urls.py`` explicitly excludes
``v1/``):

* ``1e2858a7`` (#1333) deleted three imports and five ``path()`` entries from
  ``src/swarm/urls.py`` while editing the ``/oauth/`` block. The views
  (``FsDirectoriesView``, ``RemotePairView``, ``TeamRosterTopologyAPIView``)
  stayed in the tree, so the endpoints 404'd in production while their
  functional tests kept asserting against them. ``webui/frontend/src/lib/
  api/fs.ts`` calls ``/v1/fs/directories/`` — that call was broken too.
* This file exists so a future bad merge that drops a ``path()`` line fails
  loudly here, naming the route, instead of silently 404ing.

The assertions are on *routing*, not on view behaviour: each behavioural test
already lives next to its view.
"""

from __future__ import annotations

import pytest
from django.urls import resolve, reverse

# (url, expected url_name, expected view class) — the slash/no-slash twins the
# rest of urls.py registers in pairs.
ROUTES = [
    ("/v1/fs/directories", "fs-directories-no-slash", "FsDirectoriesView"),
    ("/v1/fs/directories/", "fs-directories", "FsDirectoriesView"),
    ("/v1/team-rosters/build-rig/topology/", "team-rosters-api-topology", "TeamRosterTopologyAPIView"),
    ("/v1/remotes/omb/pair", "remotes-pair-no-slash", "RemotePairView"),
    ("/v1/remotes/omb/pair/", "remotes-pair", "RemotePairView"),
]


@pytest.mark.parametrize(("url", "url_name", "view_name"), ROUTES)
def test_api_route_is_registered(url, url_name, view_name):
    match = resolve(url)
    assert match.url_name == url_name
    assert match.func.view_class.__name__ == view_name


@pytest.mark.parametrize(("url", "url_name", "view_name"), ROUTES)
def test_api_route_reverses_back(url, url_name, view_name):
    """A registered route must also be reversible — a hand-typed path that
    nothing reverse()s is usually a path that was never wired up."""
    kwargs = {}
    if "<str:roster_id>" in str(resolve(url).route):
        kwargs["roster_id"] = "build-rig"
    if "<str:remote_id>" in str(resolve(url).route):
        kwargs["remote_id"] = "omb"
    assert reverse(url_name, kwargs=kwargs) == url


def test_no_v1_route_swallows_the_others():
    """The detail routes must not shadow the more specific sub-resources.

    ``v1/remotes/<str:remote_id>`` uses ``<str:...>``, which never spans a
    ``/``, so ``/v1/remotes/omb/pair/`` can only reach RemotePairView. Same
    for ``v1/team-rosters/<str:roster_id>/``. This pins that ordering
    invariant so re-ordering urls.py cannot quietly shadow either endpoint.
    """
    assert resolve("/v1/remotes/omb/").func.view_class.__name__ == "RemoteDetailView"
    assert resolve("/v1/team-rosters/build-rig/").func.view_class.__name__ == "TeamRosterDetailAPIView"
