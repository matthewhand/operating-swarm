from pathlib import Path


def test_avatar_stack_renders_agent_avatar():
    """AvatarStack must embed AgentAvatar inside .os-stacked-avatar instead of blank discs."""
    src = Path("webui/frontend/src/components/AvatarStack.tsx").read_text(encoding="utf-8")
    assert "import AgentAvatar from './AgentAvatar'" in src
    assert "<AgentAvatar" in src
    assert "agentId={face.agentId || face.id}" in src
    assert "src={face.avatarSrc || face.src}" in src


def test_session_picker_passes_member_avatar_to_faces():
    """sessionPicker passes avatarSrc from team members to MemberSession and StackFace.

    #1692 moved the four-name resolution chain out of this file and into
    `lib/seatAvatar.ts`, so the property this test protects is no longer "this
    literal chain is spelled out here" -- it is "the picker resolves a member's
    face through the one resolver, so the picker and the rail cannot disagree".
    Asserting the old inline literal would have failed on a correct refactor,
    which is the same rotted-assertion defect this whole change set removes.
    The four field names are still covered, in the one place that now owns
    them: the two assertions below.
    """
    src = Path("webui/frontend/src/lib/sessionPicker.ts").read_text(encoding="utf-8")
    avatar = Path("webui/frontend/src/lib/seatAvatar.ts").read_text(encoding="utf-8")

    assert "avatarSrc: session.avatarSrc" in src
    # Both picker shapes delegate: a team member row and a bare agent row.
    assert "from './seatAvatar'" in src
    assert "seatAvatarSrc(member)" in src
    assert "seatAvatarSrc(agent)" in src
    # The chain is not re-inlined anywhere in the picker. This is the
    # anti-drift half: without it, a later "just add the new field here too"
    # would restore the two-sources-of-truth defect silently.
    assert "avatarSrc ||" not in src
    assert "avatar_path" not in src
    # The four accumulated field names are all still honoured, in the one
    # module that owns the precedence.
    for field in ("avatarSrc", "avatar_path", "avatar", "src"):
        assert f"'{field}'" in avatar, f"seatAvatar.ts no longer knows {field}"


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
