"""REQ-846 / #169 — the team-member dropdown defaults instead of asking.

Selecting a team defaults the talk-to session to the configured Chief of Staff
(cos / chief_of_staff), falling back to the first member — the dropdown shows a
real member label, not a vague "Pick a …" prompt. Builds on REQ-130.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PICKER = REPO / "webui" / "frontend" / "src" / "lib" / "sessionPicker.ts"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"


def test_req846_default_prefers_cos_then_first_member():
    text = PICKER.read_text(encoding="utf-8")
    assert "export function defaultSessionForTeam" in text
    assert "s.memberId === 'cos'" in text
    assert "s.role === 'chief_of_staff'" in text
    assert "return cos || sessions[0] || null" in text


def test_req846_chatpage_defaults_dropdown_on_team_select():
    text = CHAT.read_text(encoding="utf-8")
    assert "defaultSessionForTeam(selectedTeam)?.memberId ?? ALL_MEMBERS_TARGET" in text
    assert "teamDefaultedRef" in text