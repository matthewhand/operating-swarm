from pathlib import Path


def test_avatar_stack_renders_agent_avatar():
    """AvatarStack must embed AgentAvatar inside .os-stacked-avatar instead of blank discs."""
    src = Path("webui/frontend/src/components/AvatarStack.tsx").read_text(encoding="utf-8")
    assert "import AgentAvatar from './AgentAvatar'" in src
    assert "<AgentAvatar" in src
    assert "agentId={face.agentId || face.id}" in src
    assert "src={face.avatarSrc || face.src}" in src


def test_session_picker_passes_member_avatar_to_faces():
    """sessionPicker passes avatarSrc from team members to MemberSession and StackFace."""
    src = Path("webui/frontend/src/lib/sessionPicker.ts").read_text(encoding="utf-8")
    assert "avatarSrc: session.avatarSrc" in src
    assert "avatarSrc:" in src
    assert "member.avatarSrc || member.avatar_path || member.avatar || member.src" in src


def test_team_roster_supports_avatar_fields():
    """TeamMember interface supports optional avatar fields for customized team members."""
    src = Path("webui/frontend/src/lib/teamRosters.ts").read_text(encoding="utf-8")
    assert "avatarSrc?: string" in src
    assert "avatar_path?: string" in src
    assert "avatar?: string" in src


def test_avatar_stack_limit_is_documented_and_bounded():
    """STACK_FACE_LIMIT must cap rail faces (default 3) with +N remainder for CoS/scale-out."""
    src = Path("webui/frontend/src/lib/avatarStack.ts").read_text(encoding="utf-8")
    assert "STACK_FACE_LIMIT = 3" in src
