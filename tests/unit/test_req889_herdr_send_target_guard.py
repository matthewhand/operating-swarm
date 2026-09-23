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
# #812 slice 5: the Herdr impl body moved verbatim to remote_impls/herdr.py.
HERDR_IMPL = REPO_ROOT / "src" / "swarm" / "core" / "remote_impls" / "herdr.py"


def _settings_source() -> str:
    return REMOTES_SETTINGS_TSX.read_text(encoding="utf-8")


def test_backend_still_rejects_an_empty_herdr_target():
    """R5: the guard is a UI affordance, not a replacement for the contract."""
    source = "\n".join(
        (
            REMOTES_PY.read_text(encoding="utf-8"),
            HERDR_IMPL.read_text(encoding="utf-8"),
        )
    )
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


# --- §6: the pane must not inherit another remote's targets -------------------


def test_pane_is_keyed_by_remote_id_so_a_switch_remounts_it():
    """R6: reusing the instance leaked `listed`/`botId` across the Remote picker."""
    sheet = (
        (REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx").read_text(encoding="utf-8")
        + (
            REPO_ROOT
            / "webui"
            / "frontend"
            / "src"
            / "components"
            / "settings"
            / "panes"
            / "RemotesCatalogPane.tsx"
        ).read_text(encoding="utf-8")
    )
    assert "<RemoteOperatePane key={selected.id} remote={selected} />" in sheet


def test_a_result_from_another_remote_is_ignored():
    """R7: a target list from one remote is never a target for another."""
    content = _settings_source()
    assert "const belongsHere = (result: { remote?: string }) => result.remote === remote.id" in content
    # Every mutation that can adopt or display a remote-scoped result is guarded:
    # list drops the result outright, health/interrogate/send keep this pane's own.
    assert "if (!belongsHere(result)) return" in content
    for setter in ("setHealth(result)", "setInterrogated(result)", "setSent(result)"):
        assert f"if (belongsHere(result)) {setter}" in content
    # The adoption line stays behind the ownership check, not before it.
    adoption = content.index("if (!botId && bots[0]?.id) setBotId(bots[0].id)")
    assert content.rindex("if (!belongsHere(result)) return", 0, adoption) < adoption


def test_the_mount_list_still_runs_once_per_pane():
    """R6 acceptance: remounting is what re-lists for the newly selected remote.

    Pinned as a pair so neither half can regress alone: the key in SettingsSheet
    makes a switch a fresh mount, and the ref keeps that mount idempotent.
    """
    content = _settings_source()
    assert "const autoListedRef = useRef(false)" in content
    sheet = (
        (REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx").read_text(encoding="utf-8")
        + (
            REPO_ROOT
            / "webui"
            / "frontend"
            / "src"
            / "components"
            / "settings"
            / "panes"
            / "RemotesCatalogPane.tsx"
        ).read_text(encoding="utf-8")
    )
    assert "key={selected.id}" in sheet
