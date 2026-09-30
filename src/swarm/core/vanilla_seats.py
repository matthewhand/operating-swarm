"""Vanilla / first-run admission gate for the seat catalog (#1699 / #1700 / #1725).

Why this module exists
----------------------

``GET /v1/blueprints/`` is the *only* "what seats exist" endpoint the SPA reads
— the rail, the composer picker and ``GET /v1/models``' model ids are all views
onto it — and it was served straight out of the discovery cache with no
admission and no readiness information at all. Three consequences, which
#1699, #1700 and #1725 each describe one face of:

* a greenfield install advertised **Remote-kind** recipes as chat targets
  (#1699). A remote is a harness on another box; nothing about a fresh install
  makes one reachable, and listing it assumes the operator already has remotes.
* a row that **cannot run a turn** — no resolvable provider/model, a missing CLI
  binary, a remote nobody added — was presented as a chat target, and the
  failure it produced (``blueprint 'cos' was not found or could not be
  initialized``) carried no fix path (#1700);
* the one server component that already *knew* whether inference was usable
  (:func:`swarm.core.support_context.live_context`) had **no SPA consumer**, so
  the "no API provider yet" fact could not reach the top of the chat (#1725).

There is no row *creation* and no write in this module. It answers two
questions about rows that already exist, and publishes both so no client has to
re-derive them:

``seat_listed``   may this row appear as a seat in the rail / agent picker?
``chat_ready``    can it run a turn right now, and if not, what fixes it?

Why the checks are capability checks and not a name list
--------------------------------------------------------

A denylist of blueprint ids would need extending on every rename and would
silently go stale — the exact "a field with no consumer" trap #1725 is about.
Every rule here reads a fact about the *host* instead:

* **kind** comes from the recipe's *own declared kind base*
  (``ApiKindBase.kind`` / ``CliKindBase.kind`` / ``RemoteKindBase.kind`` /
  ``TeamKindBase.kind`` in :mod:`swarm.core.kind_bases`), and otherwise from
  :func:`swarm.core.agent_kind.classify_agent_kind`, the one existing id
  resolution rule. Nothing here restates what a ``remote:`` / ``herdr:`` /
  ``remote_harness`` id is, and a recipe whose *metadata* claims
  ``kind: "api"`` cannot talk its way out of the gate — the declared base wins.
* **remotes** come from :func:`swarm.core.remotes.configured_remote_ids`, the
  same opt-in list the rail and ``GET /v1/remotes/`` already publish.
* **provider / model resolvability** comes from
  :func:`swarm.core.seat_doctor.enumerate_seats`, whose ``llm_profile``
  ``SeatSpec``s already carry the doctor's own ``base_url`` / ``model`` /
  ``missing_env`` resolution. This module *reads* those specs; it does not
  re-derive them.
* **CLI binaries** come from :func:`swarm.core.cli_catalog.discover_host_clis`,
  the same PATH resolver ``seat_health`` and ``/v1/cli-agents/`` already use.
* **the live verdict** (liveness, a real turn) stays in
  :mod:`swarm.core.seat_health` and :mod:`swarm.core.seat_doctor`. This module
  is a *static* gate for a list endpoint, so it never probes the network and
  never forks a process.

Fail-open, deliberately
-----------------------

Only a **positively proven** blocker flips a flag. Anything this module cannot
decide — an unreadable config, a recipe with no declared provider that a host
might still serve, a kind added tomorrow — stays listed and ready. A tip or a
badge that can be wrong is worse than none (#1700's own constraint), and a gate
that hides a working seat is the same defect as the one being fixed.

New install vs existing install
-------------------------------

The gate never writes, so it cannot change what any install *has*. It only
changes what a *consumer* is offered, and the distinction is structural rather
than a heuristic on names:

* a **discovered** row (a shipped recipe from the blueprint directory) is gated;
* a **user** row — custom-library seat, roster member, configured remote,
  configured ``cli_agents`` entry — is never withheld, because creating one is
  the operator's own act and hiding it would lose their work.

That is why this is safe without a migration: on an existing install the only
rows it can withhold are shipped recipes, and a row becomes listed again the
moment the operator configures the thing it needed.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from swarm.core.agent_kind import classify_agent_kind
from swarm.core.kind_bases import KIND_API, KIND_CLI, KIND_REMOTE, KIND_TEAM

logger = logging.getLogger(__name__)

#: The identity kind a recipe seat carries when its id says "recipe" rather
#: than a harness kind. It is a member of ``agent_kind.AgentKind``, not of
#: ``kind_bases``: there is no ``BlueprintKindBase``, because ``blueprint`` is
#: the *recipe* identity, not a harness a turn runs on.
KIND_BLUEPRINT = "blueprint"

#: Seat kinds a first-run install is allowed to *offer* (#1699).
#:
#: CLI, API, Blueprint and Team are shipped recipes that work from the checkout
#: alone. ``remote`` is not: it presumes the operator already has remotes
#: configured, which is the assumption #1699 rejects.
#:
#: A *kind* set, not a blueprint-id list, so renaming or adding a recipe cannot
#: silently change the rule. Asserted against ``kind_bases``' own vocabulary by
#: ``tests/core/test_vanilla_seed_1699.py`` so a new kind base has to make a
#: deliberate decision here.
SEAT_OFFER_KINDS: frozenset[str] = frozenset(
    {KIND_API, KIND_CLI, KIND_BLUEPRINT, KIND_TEAM}
)

#: Provenance of a catalog row. ``discovery`` = a shipped recipe the operator has
#: not touched. ``user`` = it came from a store the operator writes to.
SOURCE_DISCOVERY = "discovery"
SOURCE_USER = "user"

#: In-product fix paths — the same SPA settings deep links
#: ``lib/settingsLinks.ts`` already intercepts, so a link here opens the sheet
#: in-app rather than navigating away.
#:
#: Deliberately *not* a mirror of every Settings pane. A constant with no
#: emitter is a public surface with no consumer — the exact shape #1725 is
#: about — so this list holds only the routes a verdict can actually produce,
#: and ``tests/core/test_vanilla_readiness_1700.py`` asserts each one is
#: emitted by some verdict and that no other href ever is.
MANAGE_HREF_LLM_PROFILES = "/chat?settings=llm-profiles"
MANAGE_HREF_CLI_AGENTS = "/chat?settings=cli-agents"
MANAGE_HREF_REMOTES = "/chat?settings=remotes"

REASON_NO_REMOTE = (
    "No remote is configured. Add one in Settings → Remotes, then this seat "
    "becomes available."
)
REASON_NO_PROVIDER = (
    "No LLM provider is configured. Add an API provider in Settings → LLM profiles."
)
REASON_CLI_MISSING = (
    "This seat runs a CLI and no catalogued CLI is installed on this host."
)

#: Recipes whose only input is *other* seats. A host with no CLI on PATH cannot
#: run them, which is a capability answer rather than a name list: the set is
#: keyed on the ``cli_`` prefix the composer seats already share
#: (``cli_agent``/``cli_fusion``/``cli_orchestrator``/…), and the check is
#: "does this host have any CLI at all", not "is this id in a table".
_COMPOSITION_PREFIX = "cli_"


@dataclass(frozen=True)
class SeatOffer:
    """One catalog row's admission + readiness verdict.

    ``seat_listed`` false means the row must not appear as a *seat* in the rail
    or the agent picker. It stays in the Settings catalog: a recipe is a
    template, and Settings is where an operator goes to look at templates.

    ``chat_ready`` false means the row is visible but must not be a silent chat
    target: it carries a reason and a manage link.
    """

    blueprint_id: str
    kind: str
    source: str = SOURCE_DISCOVERY
    seat_listed: bool = True
    chat_ready: bool = True
    unavailable_reason: str = ""
    manage_links: tuple[dict[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        # ``seat_kind`` / ``seat_source``, NOT ``kind`` / ``source``: a
        # custom-library seat already publishes ``kind`` (its navbar provider
        # choice) and ``source`` (its provenance marker) from a different owner,
        # and clobbering either would silently retype the seat. These are the
        # gate's own fields under names nobody else claims.
        return {
            "seat_kind": self.kind,
            "seat_source": self.source,
            "seat_listed": self.seat_listed,
            "chat_ready": self.chat_ready,
            "unavailable_reason": self.unavailable_reason,
            "manage_links": [dict(link) for link in self.manage_links],
        }


@dataclass
class HostCapabilities:
    """What this host can actually reach, read once per listing.

    Probed through the existing resolvers so there is exactly one definition of
    "is a remote configured" and one of "does this profile resolve".
    """

    configured_remote_ids: frozenset[str] = frozenset()
    on_path_clis: frozenset[str] = frozenset()
    inference_ready: bool = False
    resolved_profiles: frozenset[str] = frozenset()
    unreadable: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "configured_remotes": sorted(self.configured_remote_ids),
            "on_path_clis": sorted(self.on_path_clis),
            "inference_ready": self.inference_ready,
            "resolved_profiles": sorted(self.resolved_profiles),
            "unreadable": self.unreadable,
            "notes": list(self.notes),
        }


def _link(href: str, label: str) -> dict[str, str]:
    return {"href": href, "label": label}


def host_capabilities(config: Mapping[str, Any] | None = None) -> HostCapabilities:
    """Read the host facts the gate needs, once, through the existing resolvers.

    Every read is individually guarded: an unreadable config must not take the
    catalog down, it must only make the gate *silent* (``unreadable``), which is
    the fail-open direction.
    """
    caps = HostCapabilities()
    cfg = dict(config) if isinstance(config, Mapping) else None
    try:
        from swarm.core import remotes as remotes_core

        caps.configured_remote_ids = frozenset(remotes_core.configured_remote_ids(cfg))
    except Exception:  # noqa: BLE001 — a missing remote registry is not a fault
        logger.debug("vanilla_seats: remote ids unreadable", exc_info=True)
        caps.unreadable = True
        caps.notes.append("remotes unreadable")

    try:
        from swarm.core import cli_catalog

        caps.on_path_clis = frozenset(cli_catalog.discover_host_clis())
    except Exception:  # noqa: BLE001
        logger.debug("vanilla_seats: cli discovery unreadable", exc_info=True)
        caps.unreadable = True
        caps.notes.append("cli discovery unreadable")

    # The provider question is asked of the *doctor's* roster, not re-derived:
    # enumerate_seats already resolves base_url / ${VAR} / model per profile and
    # is the same read the Seat Doctor pane shows the operator.
    try:
        from swarm.core.seat_doctor import enumerate_seats

        profiles: set[str] = set()
        for spec in enumerate_seats(cfg):
            if spec.kind != KIND_API or spec.origin != "llm_profile":
                continue
            if spec.missing_env or not spec.base_url:
                continue
            profiles.add(spec.seat_id)
        caps.resolved_profiles = frozenset(profiles)
        caps.inference_ready = bool(profiles)
    except Exception:  # noqa: BLE001
        logger.debug("vanilla_seats: seat_doctor roster unreadable", exc_info=True)
        caps.unreadable = True
        caps.notes.append("seat roster unreadable")

    if caps.unreadable:
        # Never hide a seat because *we* could not read the host.
        caps.inference_ready = True
    return caps


def row_kind(
    row_id: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    class_type: type | None = None,
) -> str:
    """Kind of a catalog row, from the one existing resolution rule.

    Precedence, strongest evidence first:

    1. the recipe class's own ``kind`` ClassVar (what base it subclasses);
    2. the id, via :func:`classify_agent_kind` — the single existing rule for
       ``remote:`` / ``herdr:`` / ``remote_harness`` / ``cli:`` seats;
    3. the row's ``kind`` metadata, which can only ever *name* a remote (a
       metadata field claiming ``api`` on a RemoteKindBase recipe loses to 1).
    """
    declared = str(getattr(class_type, "kind", "") or "").strip().lower()
    if declared in SEAT_OFFER_KINDS or declared == KIND_REMOTE:
        return declared
    classified = classify_agent_kind(row_id)
    if classified == KIND_REMOTE:
        return KIND_REMOTE
    meta = metadata if isinstance(metadata, Mapping) else {}
    explicit = str(meta.get("kind") or "").strip().lower() or None
    if explicit == KIND_REMOTE:
        return KIND_REMOTE
    return classified


def row_source(
    row_id: str,
    *,
    discovery_ids: Iterable[str],
    user_ids: Iterable[str],
) -> str:
    """``user`` when the operator created the row, else ``discovery``.

    Provenance, not a heuristic: a row counts as the operator's only if it came
    from a store they write to. A shipped recipe stays ``discovery`` forever,
    which is what makes it safe to re-evaluate the gate on every listing.
    """
    ident = str(row_id or "").strip()
    if not ident:
        return SOURCE_DISCOVERY
    if ident in {str(item).strip() for item in user_ids if str(item).strip()}:
        return SOURCE_USER
    if ident in {str(item).strip() for item in discovery_ids if str(item).strip()}:
        return SOURCE_DISCOVERY
    # Unknown to both maps: treat as discovery so the default is the gate, but
    # never as user — inventing user provenance would switch the gate off.
    return SOURCE_DISCOVERY


def _readiness_for_kind(
    kind: str,
    *,
    blueprint_id: str,
    metadata: Mapping[str, Any],
    caps: HostCapabilities,
) -> tuple[bool, str, tuple[dict[str, str], ...]]:
    """(chat_ready, reason, manage_links) for one row. Fail-open."""
    if kind == KIND_REMOTE:
        if caps.configured_remote_ids:
            return True, "", ()
        return False, REASON_NO_REMOTE, (_link(MANAGE_HREF_REMOTES, "Add a remote"),)

    if kind == KIND_CLI:
        # A CLI recipe names no binary of its own; the CLI *seats* the rail shows
        # are minted by /v1/cli-agents/ from PATH discovery. What cannot work is
        # a composition recipe (cli_fusion & friends) on a host with no CLI.
        if blueprint_id.startswith(_COMPOSITION_PREFIX) and not caps.on_path_clis:
            return False, REASON_CLI_MISSING, (
                _link(MANAGE_HREF_CLI_AGENTS, "Manage CLI agents"),
            )
        return True, "", ()

    # api / blueprint. A row that pins a model or provider of its own is as ready
    # as that provider; a row with neither needs *some* usable profile.
    meta = metadata if isinstance(metadata, Mapping) else {}
    if str(meta.get("model") or meta.get("provider") or "").strip():
        return True, "", ()
    if caps.unreadable or caps.inference_ready:
        return True, "", ()
    return False, REASON_NO_PROVIDER, (
        _link(MANAGE_HREF_LLM_PROFILES, "Set up an API provider"),
    )


def seat_offer(
    blueprint_id: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    caps: HostCapabilities,
    source: str = SOURCE_DISCOVERY,
    class_type: type | None = None,
) -> SeatOffer:
    """Admission + readiness for one catalog row.

    A ``SOURCE_USER`` row is never withheld: the operator installed that seat
    on purpose, and #1699 is about what a *first-run* install ships, not about
    hiding someone's work. Readiness is still reported, because "the remote you
    added is gone" is useful on an existing install too.
    """
    ident = str(blueprint_id or "").strip()
    kind = row_kind(ident, metadata, class_type=class_type)
    ready, reason, links = _readiness_for_kind(
        kind, blueprint_id=ident, metadata=metadata or {}, caps=caps
    )
    seat_listed = True
    if (
        source != SOURCE_USER
        and kind not in SEAT_OFFER_KINDS
        and not caps.configured_remote_ids
    ):
        # #1699: a greenfield install has no remote, so a Remote-kind recipe can
        # only fail. Withhold it from the seat list; it stays in the Settings
        # catalog, and it comes back the moment a remote is added.
        seat_listed = False
        ready = False
        reason = REASON_NO_REMOTE
        links = (_link(MANAGE_HREF_REMOTES, "Add a remote"),)
    return SeatOffer(
        blueprint_id=ident,
        kind=kind,
        source=source,
        seat_listed=seat_listed,
        chat_ready=ready,
        unavailable_reason=reason,
        manage_links=links,
    )


def catalog_offers(
    rows: Iterable[tuple[str, Mapping[str, Any] | None]],
    *,
    discovery_ids: Iterable[str] = (),
    user_ids: Iterable[str] = (),
    config: Mapping[str, Any] | None = None,
    caps: HostCapabilities | None = None,
) -> dict[str, SeatOffer]:
    """Verdict per catalog row id. One host read, one verdict per row.

    ``rows`` is ``(blueprint_id, metadata, class_type)`` triples; ``None`` for
    either optional element is fine (a custom-library seat has no discovery
    class). ``discovery_ids`` are the ids discovery produced; ``user_ids`` are
    the ids the operator's own stores produced. Ids in neither are treated as
    discovery (see :func:`row_source`).
    """
    resolved = caps if caps is not None else host_capabilities(config)
    out: dict[str, SeatOffer] = {}
    for row in rows:
        ident = str(row[0] or "").strip()
        if not ident:
            continue
        metadata = row[1] if len(row) > 1 else None
        class_type = row[2] if len(row) > 2 else None
        out[ident] = seat_offer(
            ident,
            metadata=metadata,
            caps=resolved,
            source=row_source(ident, discovery_ids=discovery_ids, user_ids=user_ids),
            class_type=class_type,
        )
    return out


__all__ = [
    "MANAGE_HREF_CLI_AGENTS",
    "MANAGE_HREF_LLM_PROFILES",
    "MANAGE_HREF_REMOTES",
    "REASON_CLI_MISSING",
    "REASON_NO_PROVIDER",
    "REASON_NO_REMOTE",
    "SEAT_OFFER_KINDS",
    "SOURCE_DISCOVERY",
    "SOURCE_USER",
    "HostCapabilities",
    "SeatOffer",
    "catalog_offers",
    "host_capabilities",
    "row_kind",
    "row_source",
    "seat_offer",
]
