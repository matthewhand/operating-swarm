"""#812 slice 5 — REQ-203 harness wiring, moved verbatim out of
``swarm.core.remotes``. The 11 ``RemoteHarness`` registrations (binders,
bound senders, ``_install_remote_harnesses``) live here; ``remotes``
imports this module and calls :func:`install` once at import. References
to ``remotes`` names go through ``R`` so monkeypatching still lands.
"""

from __future__ import annotations

import importlib
from typing import Any

R: Any = importlib.import_module("swarm.core.remotes")


def install() -> None:
    """Public alias kept for the moved installer (module-private upstream)."""
    _install_remote_harnesses()


def _bind_health(impl_id: str):
    def _health(spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:  # noqa: ARG001
        target_id = spec.id if hasattr(spec, "id") and spec.id else impl_id
        return R.check_health(target_id, config=config, timeout=timeout)

    return _health


def _bind_http_list(fn):
    def _list(spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
        return fn(spec, timeout)

    return _list


def _hermes_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",  # noqa: ARG001 — RemoteHarness.send signature
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    return R._hermes_send(spec, prompt, timeout, session_id=session_id)


def _anythingllm_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    return R._anythingllm_send(spec, prompt, timeout, session_id=session_id, target=target)



def _n8n_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    send_timeout = timeout if timeout != R._OPERATE_TIMEOUT_S else R._N8N_SEND_TIMEOUT_S
    return R._n8n_send(spec, prompt, send_timeout, session_id=session_id, target=target)



def _flowise_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    send_timeout = timeout if timeout >= 30 else R._FLOWISE_SEND_TIMEOUT_S
    return R._flowise_send(spec, prompt, send_timeout, session_id=session_id, target=target)



def _openwebui_list_bound(
    spec: R.RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None  # noqa: ARG001
) -> R.OperateResult:
    from swarm.core.openwebui_remote import openwebui_list

    return openwebui_list(spec, timeout)


def _openwebui_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    *,
    target: str = "",
    timeout: float,
    session_id: str | None = None,
    config: dict[str, Any] | None = None,  # noqa: ARG001
) -> R.OperateResult:
    from swarm.core.openwebui_remote import openwebui_send, send_timeout

    return openwebui_send(
        spec, prompt, send_timeout(timeout), session_id=session_id, target=target
    )


def _letta_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    send_timeout = timeout if timeout >= 30 else R._LETTA_SEND_TIMEOUT_S
    return R._letta_send(spec, prompt, send_timeout, session_id=session_id, target=target)


def _omb_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    return R._omb_send(spec, prompt, target or (session_id or ""), timeout)


def _rakazo_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> R.OperateResult:
    return R._rakazo_send(spec, prompt, target, timeout)


def _swarm_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> R.OperateResult:
    return R._swarm_send(spec, prompt, target, timeout)


def _trueforge_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> R.OperateResult:
    return R._trueforge_send(spec, prompt, target=target, timeout=timeout, session_id=session_id)


def _trueforge_routines_bound(
    spec: R.RemoteSpec,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
) -> R.OperateResult:
    return R._trueforge_routines(spec, timeout=timeout)


def _herdr_list_bound(
    spec: R.RemoteSpec,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
) -> R.OperateResult:
    return R._herdr_list(spec, timeout, config)


def _herdr_send_bound(
    spec: R.RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
    session_id: str | None = None,  # noqa: ARG001
) -> R.OperateResult:
    return R._herdr_send(spec, prompt, target, timeout, config)


def _herdr_operate_bound(
    spec: R.RemoteSpec,
    op: str,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
    prompt: str = "",
    target: str = "",
    session_id: str | None = None,  # noqa: ARG001
) -> R.OperateResult:
    if op == "interrogate":
        return R._herdr_interrogate(spec, target, timeout, config)
    if op == "list":
        return R._herdr_list(spec, timeout, config)
    return R._herdr_send(spec, prompt, target, timeout, config)


def _install_remote_harnesses() -> None:
    """Map existing remotes.py adapters onto :class:`RemoteHarness` (REQ-203)."""
    from swarm.core.remote_harness import (
        BoundRemoteHarness,
        capabilities_for,
        register_harness,
    )

    register_harness(
        BoundRemoteHarness(
            impl_id="hermes",
            label="Hermes",
            capabilities=capabilities_for("hermes"),
            health_fn=_bind_health("hermes"),
            list_fn=_bind_http_list(R._hermes_list),
            send_fn=_hermes_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="omb",
            label="OpenMousBot",
            capabilities=capabilities_for("omb"),
            health_fn=_bind_health("omb"),
            list_fn=_bind_http_list(R._omb_list),
            send_fn=_omb_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="rakazo",
            label="Rakazo",
            capabilities=capabilities_for("rakazo"),
            health_fn=_bind_health("rakazo"),
            list_fn=_bind_http_list(R._rakazo_list),
            send_fn=_rakazo_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="herdr",
            label="Herdr",
            capabilities=capabilities_for("herdr"),
            health_fn=_bind_health("herdr"),
            list_fn=_herdr_list_bound,
            send_fn=_herdr_send_bound,
            operate_fn=_herdr_operate_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="swarm",
            label="Swarm",
            capabilities=capabilities_for("swarm"),
            health_fn=_bind_health("swarm"),
            list_fn=_bind_http_list(R._swarm_list),
            send_fn=_swarm_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="anythingllm",
            label="AnythingLLM",
            capabilities=capabilities_for("anythingllm"),
            health_fn=_bind_health("anythingllm"),
            list_fn=_bind_http_list(R._anythingllm_list),
            send_fn=_anythingllm_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="letta",
            label="Letta",
            capabilities=capabilities_for("letta"),
            health_fn=_bind_health("letta"),
            list_fn=_bind_http_list(R._letta_list),
            send_fn=_letta_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="openwebui",
            label="Open WebUI",
            capabilities=capabilities_for("openwebui"),
            health_fn=_bind_health("openwebui"),
            list_fn=_openwebui_list_bound,
            send_fn=_openwebui_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="flowise",
            label="Flowise",
            capabilities=capabilities_for("flowise"),
            health_fn=_bind_health("flowise"),
            list_fn=_bind_http_list(R._flowise_list),
            send_fn=_flowise_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="n8n",
            label="n8n",
            capabilities=capabilities_for("n8n"),
            health_fn=_bind_health("n8n"),
            list_fn=_bind_http_list(R._n8n_list),
            send_fn=_n8n_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="trueforge",
            label="TrueForge",
            capabilities=capabilities_for("trueforge"),
            health_fn=_bind_health("trueforge"),
            list_fn=_bind_http_list(R._trueforge_list),
            send_fn=_trueforge_send_bound,
            routines_fn=_trueforge_routines_bound,
        )
    )


