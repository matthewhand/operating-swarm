"""#814 — Role sub-hierarchy (Worker/Verifier/Advisory/Supervisor) + Mode B engine.

Contracts:
- Every canonical role inherits one of the four behavioral sub-bases; the
  taxonomy is assertable with ``isinstance``.
- Verifier roles (gate, skeptic) share the standard ``Verdict`` schema and a
  unified ``execute_verification``; verdicts fail closed (undetermined → not
  approved).
- ``Role.execute_as_role(ctx, payload)`` builds the Mode B model window
  strictly from ``[execution_prompt, caller_context, latest_message]`` — the
  callee's private Mode A thread never leaks in.
- Descriptors expose ``category`` so the UI can group roles without a
  parallel table.
"""

from __future__ import annotations

from typing import Any

from swarm.core.roles import ROLE_REGISTRY, get_role
from swarm.core.roles.adapters import (
    AdvisorRole,
    ChiefOfStaffRole,
    DefaultRole,
    EngineerRole,
    GateRole,
    SkepticRole,
    SuggestionsRole,
    SupportRole,
)
from swarm.core.roles.base import (
    AdvisoryRole,
    Role,
    RoleContext,
    SupervisorRole,
    VerifierRole,
    Verdict,
    WorkerRole,
)


def _ctx(**params: Any) -> RoleContext:
    return RoleContext(params=params)


# ---------------------------------------------------------------- taxonomy

def test_taxonomy_support_gate_skeptic_suggestions_engineer_default():
    assert isinstance(get_role("support"), WorkerRole)
    assert isinstance(get_role("gate"), VerifierRole)
    assert isinstance(get_role("skeptic"), VerifierRole)
    assert isinstance(get_role("suggestions"), AdvisoryRole)
    assert isinstance(get_role("advisor"), AdvisoryRole)
    assert isinstance(get_role("default"), WorkerRole)
    assert isinstance(get_role("engineer"), WorkerRole)


def test_taxonomy_admin_supervisor_chief_of_staff():
    # Admin and CoS hold lifecycle/topology authority over other seats.
    assert isinstance(get_role("admin"), SupervisorRole)
    assert isinstance(get_role("chief_of_staff"), SupervisorRole)


def test_sub_bases_inherit_role_and_registry_unchanged():
    for base in (WorkerRole, VerifierRole, AdvisoryRole, SupervisorRole):
        assert issubclass(base, Role)
    # Registry keys must remain identical to the pre-refactor flat set.
    assert set(ROLE_REGISTRY) == {
        "admin",
        "default",
        "support",
        "gate",
        "skeptic",
        "advisor",
        "chief_of_staff",
        "engineer",
        "suggestions",
    }


# --------------------------------------------------------------- verifier

def test_verifier_role_has_unified_execute_verification():
    gate = get_role("gate")
    skeptic = get_role("skeptic")
    assert callable(getattr(gate, "execute_verification", None))
    assert callable(getattr(skeptic, "execute_verification", None))


def test_gate_execute_verification_fail_closed_on_unwired():
    gate = get_role("gate")
    assert isinstance(gate, GateRole)
    verdict = gate.execute_verification(_ctx(), payload={"calls": []})
    assert isinstance(verdict, Verdict)
    assert verdict.approved is False
    assert verdict.failed is True  # fail-closed: unwired verifier cannot approve


def test_skeptic_execute_verification_maps_findings():
    skeptic = get_role("skeptic")
    assert isinstance(skeptic, SkepticRole)

    class _Ok:
        accomplished = True
        findings: list[str] = []

    class _Bad:
        accomplished = False
        findings = ["output missing tests"]

    ok = skeptic.execute_verification(_ctx(), result=_Ok())
    assert ok.approved is True and ok.failed is False
    bad = skeptic.execute_verification(_ctx(), result=_Bad())
    assert bad.approved is False and bad.failed is True
    assert "tests" in (bad.reason or "")


# ---------------------------------------------------------------- mode B

def test_execute_as_role_builds_strict_context_window():
    skeptic = get_role("skeptic")
    payload: dict[str, Any] = {
        "invocation": "as_tool",
        "caller_id": "coordinator-1",
        "role": "skeptic",
        "latest_message": "review my diff",
        "caller_context": "We are shipping the parser module.",
    }
    messages = skeptic.execute_as_role(_ctx(), payload)
    assert isinstance(messages, list) and messages
    # Exactly execution-prompt + caller-context + latest-message: no more.
    assert len(messages) == 3
    assert messages[0]["role"] == "system"  # execution prompt
    assert "Caller Context from coordinator-1" in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": "review my diff"}


def test_execute_as_role_never_loads_callee_thread():
    skeptic = get_role("skeptic")
    payload: dict[str, Any] = {
        "invocation": "as_tool",
        "caller_id": "coordinator-1",
        "role": "skeptic",
        "latest_message": "review",
        "caller_context": "ctx",
        #callee_thread_id is deliberately ignored — that's the leak it guards.
        "callee_thread_id": "thread-abc",
    }
    messages = skeptic.execute_as_role(_ctx(), payload)
    joined = " ".join(m["content"] for m in messages)
    assert "thread-abc" not in joined


def test_execute_as_role_rejects_invalid_payload():
    skeptic = get_role("skeptic")
    with __import__("pytest").raises(Exception):
        skeptic.execute_as_role(_ctx(), {"invocation": "as_tool"})  # missing caller/role/message


# ------------------------------------------------------------ descriptors

def test_descriptors_expose_category():
    for role_id, expected in (
        ("gate", "verifier"),
        ("skeptic", "verifier"),
        ("advisor", "advisory"),
        ("suggestions", "advisory"),
        ("chief_of_staff", "supervisor"),
        ("admin", "supervisor"),
        ("default", "worker"),
        ("support", "worker"),
        ("engineer", "worker"),
    ):
        desc = get_role(role_id).describe()
        assert desc["category"] == expected, role_id


def test_adapters_import_the_four_sub_bases():
    # The adapters module must keep exporting the taxonomy for consumers.
    import swarm.core.roles.adapters as ad

    for name in (
        "WorkerRole",
        "VerifierRole",
        "AdvisoryRole",
        "SupervisorRole",
        "Verdict",
        "AdvisorRole",
        "ChiefOfStaffRole",
        "DefaultRole",
        "EngineerRole",
        "GateRole",
        "SkepticRole",
        "SuggestionsRole",
        "SupportRole",
    ):
        assert hasattr(ad, name), name
