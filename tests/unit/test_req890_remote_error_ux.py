"""REQ-890 / #449 — remote failures are sentences, not JSON dumps.

Before this change ``_render_operate`` appended
``json.dumps(result.data, indent=2)[:4000]`` to every failing operation whose
remote was not in a hardcoded ``{omb, hermes, herdr}`` trio, and it printed the
internal gap code verbatim as ``GAP: rakazo_rpc_requires_better_auth_session``.

The live repro is an unauthenticated Rakazo: ``/rpc/bots/list`` answers 401 and
the chat bubble carried the raw ``{"json": {"code": "UNAUTHORIZED" ...}}`` body.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from swarm.blueprints.remote_harness import blueprint_remote_harness as harness
from swarm.core.remotes import NOT_ADDED_MARKER, OperateResult

SRC = Path(__file__).resolve().parents[2] / "src"

# The exact body Rakazo returns when no Better Auth session is present.
_RAKAZO_401_BODY = {
    "json": {
        "defined": False,
        "code": "UNAUTHORIZED",
        "status": 401,
        "message": "Unauthorized",
    }
}


def _failed(
    *,
    remote: str = "rakazo",
    op: str = "list",
    detail: str = (
        "Rakazo /rpc/bots/list requires a Better Auth session. "
        "Health (GET /health) is public; operate is not."
    ),
    gap: str = "rakazo_rpc_requires_better_auth_session",
    data: object = None,
    http_status: int | None = 401,
) -> OperateResult:
    return OperateResult(
        remote=remote,
        op=op,
        ok=False,
        detail=detail,
        http_status=http_status,
        data=data,
        gap=gap,
    )


# --- the reported defect ----------------------------------------------------


def test_rakazo_401_does_not_dump_the_raw_body():
    """The upstream auth envelope must never reach the chat bubble."""
    out = harness._render_operate(_failed(data=_RAKAZO_401_BODY))

    assert "UNAUTHORIZED" not in out
    assert '"json"' not in out
    assert "{" not in out


def test_rakazo_401_does_not_leak_the_gap_identifier():
    out = harness._render_operate(_failed())

    assert "rakazo_rpc_requires_better_auth_session" not in out
    assert "GAP:" not in out


def test_rakazo_401_names_the_fix_and_keeps_the_fail_prefix():
    out = harness._render_operate(_failed())

    # Prefix contract kept (locked elsewhere by the TrueForge refused-send test).
    assert "rakazo list: FAIL —" in out
    assert "Fix: " in out
    assert "RAKAZO_SESSION_COOKIE" in out
    assert "RAKAZO_API_KEY" in out


@pytest.mark.parametrize(
    "remote",
    [
        "rakazo",
        "trueforge",
        "anythingllm",
        "slack",
        "letta",
        "openwebui",
        "flowise",
        "n8n",
        "omb",
        "hermes",
        "herdr",
    ],
)
def test_no_remote_dumps_json_on_failure(remote):
    """The trio-only special case is gone: every remote renders a sentence."""
    out = harness._render_operate(
        _failed(remote=remote, detail="upstream refused", gap="", data={"json": {"a": 1}})
    )

    assert "{" not in out
    assert '"a"' not in out
    assert f"{remote} list: FAIL — upstream refused" in out


# --- the gap map is complete and stays complete -----------------------------


# A gap code is lowercase snake_case; a comparison operand like "timed out" is not.
_CODE_SHAPE = re.compile(r"^[a-z][a-z0-9_]*$")


def _string_constants(node: ast.AST) -> set[str]:
    """Every code-shaped string literal inside an expression."""
    return {
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and _CODE_SHAPE.match(n.value)
    }


def _gap_codes_in_source() -> set[str]:
    """Every gap code the backend can actually raise.

    Parses the AST instead of grepping for ``gap="code"``. #474 rewrote one
    assignment as a multi-line conditional (``else "omb_reply_timeout"``), which
    the literal-only pattern read as "no raiser" — a false dead entry that would
    have deleted a live hint.
    """
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover — unparseable file, fall back
            found.update(re.findall(r'gap="([a-z0-9_]+)"', source))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "gap":
                    found.update(_string_constants(kw.value))
    return found


def test_every_real_gap_code_has_a_human_hint():
    codes = _gap_codes_in_source()
    assert codes, "expected to find gap codes in src/"
    missing = sorted(codes - set(harness._GAP_HINTS))
    assert not missing, (
        "these gap codes would leak their raw identifier into chat — add a hint "
        f"to _GAP_HINTS: {missing}"
    )


def test_hint_map_has_no_dead_entries():
    """A hint for a code nobody raises is stale documentation."""
    dead = sorted(set(harness._GAP_HINTS) - _gap_codes_in_source())
    assert not dead, f"_GAP_HINTS entries with no raiser: {dead}"


def test_hints_are_imperatives_not_identifiers():
    for code, hint in harness._GAP_HINTS.items():
        assert hint.endswith("."), f"{code} hint should be a sentence"
        assert re.search(r"[A-Za-z]", hint), f"{code} hint is empty"
        # Never restate the snake_case code as the "fix".
        assert code not in hint


def test_unknown_gap_still_does_not_leak_its_identifier():
    """A new code without a hint must degrade, not print snake_case."""
    out = harness._gap_line("brand_new_failure_code")

    assert "brand_new_failure_code" not in out
    assert "brand new failure code" in out
    assert out.startswith("\nFix: ")


def test_empty_gap_adds_no_line():
    assert harness._gap_line("") == ""


# --- contracts that must not regress ---------------------------------------


def test_never_added_seat_keeps_its_natural_sentence():
    """issue #129 — the not-added detail is already a whole sentence."""
    detail = (
        f"Hermes is {NOT_ADDED_MARKER} — the sidebar seat is a catalog placeholder. "
        "Add it in Settings → Remotes or run `swarm-cli remotes set hermes`."
    )
    out = harness._render_operate(_failed(remote="hermes", op="send", detail=detail, gap=""))

    assert out == detail
    assert "send: FAIL" not in out


def test_successful_send_reply_is_still_plain_text():
    """issue #301 — the reply text is the answer, undecorated."""
    result = OperateResult(
        remote="omb",
        op="send",
        ok=True,
        detail="started",
        data={"text": "Hailo-8L is still blocked until the ribbon arrives."},
    )
    out = harness._render_operate(result)

    assert out == "Hailo-8L is still blocked until the ribbon arrives."


def test_success_without_a_reply_still_reads_ok():
    result = OperateResult(remote="hermes", op="send", ok=True, detail="started")
    out = harness._render_operate(result)

    assert "hermes send: OK — started" in out
    assert "FAIL" not in out


def test_omb_timeout_stays_a_named_sentence():
    """issue #301 — a named timeout, never a UUID or run ACK."""
    out = harness._render_operate(
        _failed(
            remote="omb",
            op="send",
            detail="OpenMousBot reply timed out after 120s.",
            gap="omb_reply_timeout",
            data={"run_id": "79b5852c-9ae8-4972-a662-80054be9ea5f"},
        )
    )

    assert "timed out" in out
    assert "79b5852c" not in out
    assert "accepted the turn" not in out
    assert "omb_reply_timeout" not in out
