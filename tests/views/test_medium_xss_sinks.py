"""Regression: medium XSS sinks must escape / gate untrusted values.

Covers rest_mode toast.js, blueprint_creator showSuccessModal,
profiles.html base_url href (javascript: protocol), Session Explorer
attribute escape, and rest_mode blueprintManager metadata sinks.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REST_JS = ROOT / "src" / "swarm" / "static" / "rest_mode" / "js"
TOAST_JS = REST_JS / "toast.js"
CHAT_LOGIC = REST_JS / "chatLogic.js"
SIMPLE_LOGIC = REST_JS / "simpleLogic.js"
MESSENGER_LOGIC = REST_JS / "messengerLogic.js"
BLUEPRINT_MANAGER = REST_JS / "modules" / "blueprintManager.js"
SESSION_EXPLORER = ROOT / "src" / "swarm" / "static" / "js" / "session_explorer.js"
BLUEPRINT_CREATOR = ROOT / "src" / "swarm" / "static" / "js" / "blueprint_creator.js"
PROFILES = ROOT / "src" / "swarm" / "templates" / "profiles.html"

_INNERHTML_MESSAGE_SINK = re.compile(
    r"innerHTML\s*\+=\s*`<div class=\"(user|assistant|error)-message\">\$\{"
)


def _slice_after(source: str, marker: str, length: int = 1200) -> str:
    idx = source.find(marker)
    assert idx != -1, f"marker not found: {marker}"
    return source[idx : idx + length]


def test_rest_mode_toast_escapes_message():
    source = TOAST_JS.read_text(encoding="utf-8")
    body = _slice_after(source, "export function showToast")
    assert "escapeHtml(message)" in body
    assert re.search(r"<span>\$\{\s*message\s*\}</span>", body) is None
    # Helper lives in htmlSafe.js (imported), not inlined in toast.js.
    assert "from './htmlSafe.js'" in source or 'from "./htmlSafe.js"' in source
    assert "function escapeHtml" not in source


def test_blueprint_creator_show_success_modal_escapes_fields():
    source = BLUEPRINT_CREATOR.read_text(encoding="utf-8")
    body = _slice_after(source, "function showSuccessModal")
    assert "escapeHtml(blueprint.name)" in body
    assert "escapeHtml(blueprint.category)" in body
    assert "escapeHtml(blueprint.author)" in body
    assert "escapeHtml(blueprint.created_at)" in body
    assert "escapeHtml(blueprint.description)" in body
    assert "escapeHtml(tag)" in body
    assert re.search(r"\$\{\s*blueprint\.(name|category|author|created_at|description)\s*\}", body) is None
    assert re.search(r"\$\{\s*tag\s*\}", body) is None
    assert "function escapeHtml" in source


def test_profiles_base_url_href_gated_to_http_https():
    source = PROFILES.read_text(encoding="utf-8")
    # Must not use raw base_url as href without an http(s) gate.
    assert 'href="{{ p.base_url }}"' in source
    assert 'u|slice:":8" == "https://"' in source
    assert 'u|slice:":7" == "http://"' in source
    # Non-http(s) values render as text, not a link.
    assert '<span class="prof-url">{{ p.base_url }}</span>' in source


def test_chat_logic_exports_initializer_and_uses_textcontent():
    """ui.js imports initializeChatLogic — export must exist; chat lines use textContent."""
    source = CHAT_LOGIC.read_text(encoding="utf-8")
    assert "export async function initializeChatLogic" in source
    assert "textContent" in source
    assert _INNERHTML_MESSAGE_SINK.search(source) is None


def test_simple_logic_appends_messages_via_textcontent():
    """Demo simpleLogic.js must not sink chat/error strings into innerHTML."""
    source = SIMPLE_LOGIC.read_text(encoding="utf-8")
    assert "appendMessage" in source
    assert "textContent" in source
    assert _INNERHTML_MESSAGE_SINK.search(source) is None


def test_messenger_logic_appends_messages_via_textcontent():
    """Demo messengerLogic.js must not sink chat/error strings into innerHTML."""
    source = MESSENGER_LOGIC.read_text(encoding="utf-8")
    assert "textContent" in source
    assert _INNERHTML_MESSAGE_SINK.search(source) is None


def test_debug_js_escapes_message_fields():
    source = (REST_JS / "debug.js").read_text(encoding="utf-8")
    assert "escapeHtml(role)" in source
    assert "escapeHtml(sender)" in source
    assert "escapeHtml(content" in source
    assert "createTextNode" in source
    assert re.search(r"Active Agent:</strong>\s*\$\{", source) is None


def test_settings_js_escapes_llm_config_fields():
    source = (REST_JS / "settings.js").read_text(encoding="utf-8")
    assert "escapeHtml(key)" in source
    assert "escapeAttr(value)" in source
    assert re.search(r'value="\$\{value\}"', source) is None


def test_session_explorer_esc_covers_attribute_quotes():
    """Live-poll card HTML uses esc() in data-status/title — quotes must escape."""
    source = SESSION_EXPLORER.read_text(encoding="utf-8")
    body = _slice_after(source, "function esc(s)", length=400)
    assert "&quot;" in body
    assert "&#39;" in body
    assert '[&<>"\']' in body or "[&<>\"']" in body
    assert "data-status=\"'+esc(st)" in source
    assert "title=\"'+esc(d.role)" in source


def test_blueprint_manager_escapes_api_metadata():
    source = BLUEPRINT_MANAGER.read_text(encoding="utf-8")
    assert "from '../htmlSafe.js'" in source or 'from "../htmlSafe.js"' in source
    assert "escapeAttr(bp.id)" in source
    assert "escapeHtml(bp.title)" in source
    assert "escapeHtml(bp.description)" in source
    assert "escapeHtml(blueprintName)" in source
    assert "escapeHtml(blueprintDescription)" in source
    assert re.search(r'data-id="\$\{bp\.id\}"', source) is None
    assert re.search(r"<h2>\$\{blueprintName\}</h2>", source) is None
