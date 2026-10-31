"""URL utilities for Operating Swarm.

Provides helpers for registering twin slash/no-slash routes consistently across
the REST API surface without duplicate declarations, avoiding body-dropping 301/302
redirects on bare endpoints.
"""

from __future__ import annotations

from typing import Any, Callable
from django.urls import path


def twin_path(
    route: str,
    view: Callable[..., Any],
    kwargs: dict[str, Any] | None = None,
    name: str | None = None,
    *,
    slash_name: str | None = None,
    no_slash_name: str | None = None,
) -> list:
    """Generate both unslashed and slashed route variants for an endpoint.

    Resolves both `/v1/resource` and `/v1/resource/` to the same view handler.
    By convention:
    - If `name` ends with `-slash`, the slashed route receives `name`
      and unslashed receives `name[:-6]`.
    - If `name` ends with `-no-slash`, the unslashed route receives `name`
      and slashed receives `name[:-9]`.
    - Otherwise, if `name` is provided, the slashed route receives `name` and unslashed
      receives `f"{name}-no-slash"`.
    Explicit `slash_name` or `no_slash_name` overrides this heuristic.

    Ordering: unslashed route is placed first, followed by slashed route, matching
    Operating Swarm routing resolution convention.
    """
    clean_route = route.strip("/")
    unslashed = clean_route
    slashed = f"{clean_route}/"

    resolved_no_slash_name = no_slash_name
    resolved_slash_name = slash_name

    if name:
        if resolved_no_slash_name is None and resolved_slash_name is None:
            if name.endswith("-no-slash"):
                resolved_no_slash_name = name
                resolved_slash_name = name[: -len("-no-slash")]
            elif name.endswith("-slash"):
                resolved_slash_name = name
                resolved_no_slash_name = name[: -len("-slash")]
            else:
                resolved_slash_name = name
                resolved_no_slash_name = f"{name}-no-slash"
        elif resolved_no_slash_name is None:
            resolved_no_slash_name = name
        elif resolved_slash_name is None:
            resolved_slash_name = name

    return [
        path(unslashed, view, kwargs=kwargs, name=resolved_no_slash_name),
        path(slashed, view, kwargs=kwargs, name=resolved_slash_name),
    ]


class ApiRouter:
    """Lightweight REST API router managing twin slash/no-slash routes."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix.strip("/")
        self._urls: list = []

    def register(
        self,
        route: str,
        view: Callable[..., Any],
        name: str | None = None,
        *,
        slash_name: str | None = None,
        no_slash_name: str | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        clean = route.strip("/")
        full_route = f"{self.prefix}/{clean}" if self.prefix else clean
        self._urls.extend(
            twin_path(
                full_route,
                view,
                kwargs=kwargs,
                name=name,
                slash_name=slash_name,
                no_slash_name=no_slash_name,
            )
        )

    @property
    def urls(self) -> list:
        return list(self._urls)
