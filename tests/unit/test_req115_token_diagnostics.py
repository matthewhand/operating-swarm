from pathlib import Path


def test_req115_token_diagnostics_modal_component_exists():
    repo_root = Path(__file__).resolve().parents[2]
    modal_ts = repo_root / "webui" / "frontend" / "src" / "components" / "TokenDiagnosticsModal.tsx"
    assert modal_ts.exists()
    content = modal_ts.read_text(encoding="utf-8")

    assert "Session Token Diagnostics" in content
    assert "diag-session-id" in content
    assert "diag-context-usage" in content
    assert "diag-input-tokens" in content
    assert "diag-output-tokens" in content
    assert "diag-compacts-count" in content
    assert "diag-tool-calls" in content
    assert "diag-message-count" in content
    assert "diag-estimated-cost" in content


def test_req115_chatpage_token_meter_button_and_modal_wired():
    repo_root = Path(__file__).resolve().parents[2]
    chat_page = repo_root / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
    assert chat_page.exists()
    content = chat_page.read_text(encoding="utf-8")

    # #773: the navbar token meter was removed — the composer's
    # ContextUsageBadge is the ONE canonical meter, and it opens the modal.
    assert "ContextUsageBadge" in content
    assert 'data-testid="context-usage-badge-slot"' in content
    assert "TokenDiagnosticsModal" in content
    assert "setTokenDiagOpen" in content
