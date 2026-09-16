"""REQ-889: Herdr Send cannot be submitted without a target (#453).

Intent: the operate pane must not offer a Send that the backend is guaranteed to
reject. Herdr's send hard-requires a target (``_herdr_send``); every other kind
may legitimately send without one, so the guard is kind-scoped.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTES_SETTINGS_TSX = (
    REPO_ROOT / "webui" / "frontend" / "src" / "components" / "RemotesSettings.tsx"
)
REMOTES_PY = REPO_ROOT / "src" / "swarm" / "core" / "remotes.py"


def _settings_source() -> str:
    return REMOTES_SETTINGS_TSX.read_text(encoding="utf-8")


def test_backend_still_rejects_an_empty_herdr_target():
    """R5: the guard is a UI affordance, not a replacement for the contract."""
    source = REMOTES_PY.read_text(encoding="utf-8")
    assert 'detail="target is required (Herdr pane / CLI id, e.g. w3:p1 or grok)"' in source


def test_send_is_gated_by_a_kind_scoped_requires_target_flag():
    content = _settings_source()
    # R1: the guard exists and is derived from the remote kind, not hardcoded
    # inside the button, so a second target-requiring kind is a one-line change.
    assert "const requiresTarget = isHerdr" in content
    # R3: OMB is deliberately excluded (an empty target creates a bot there).
    assert "const isOmb = isOpenMousBotKind(remote.id)" in content
    assert "disabled={requiresTarget && !botId.trim()}" in content


def test_pane_lists_targets_once_on_mount():
    content = _settings_source()
    # R2: the guarded button reaches enabled without a separate List click.
    assert "const autoListedRef = useRef(false)" in content
    assert "if (autoListedRef.current) return" in content
    assert "listMutation.mutate()" in content
    # The mount list stays idempotent: an empty dependency list, not the
    # mutation identity (which would re-list on every render).
    effect_start = content.index("const autoListedRef = useRef(false)")
    effect_body = content[effect_start : effect_start + 500]
    assert "}, [])" in effect_body


def test_list_adoption_never_overwrites_an_operator_choice():
    # R2 acceptance: the first row is adopted only while the field is blank.
    content = _settings_source()
    assert "if (!botId && bots[0]?.id) setBotId(bots[0].id)" in content


def test_manual_list_control_is_still_available():
    content = _settings_source()
    assert "onClick={() => listMutation.mutate()}" in content
