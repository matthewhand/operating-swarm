from pathlib import Path


def test_req155_settings_dashboard_template_avatar_options():
    repo_root = Path(__file__).resolve().parents[2]
    template_path = repo_root / "src" / "swarm" / "templates" / "settings_dashboard.html"
    assert template_path.exists()
    content = template_path.read_text(encoding="utf-8")

    assert 'id="os-avatar-theme"' in content
    assert '<option value="bland">Default</option>' in content
    assert '<option value="blobs">Blobs</option>' in content
    assert '<option value="bee">Bee</option>' in content
    assert '<option value="robot3d">3D robot</option>' in content
    assert "docs/adr/008-3d-robot-avatar-theme.md" in content


def test_req155_chrome_avatar_theme_script_defaults_to_blobs():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "src" / "swarm" / "static" / "js" / "chrome_avatar_theme.js"
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")

    assert 'return "blobs";' in content
    assert 'theme === "bland"' in content
    assert 'theme === "bee"' in content
    assert 'stored === "robot3d"' in content
    assert 'localStorage.removeItem(KEY);' in content


def test_req155_frontend_avatar_theme_defaults():
    repo_root = Path(__file__).resolve().parents[2]
    theme_ts_path = repo_root / "webui" / "frontend" / "src" / "lib" / "avatarTheme.ts"
    assert theme_ts_path.exists()
    content = theme_ts_path.read_text(encoding="utf-8")

    assert "defaultAvatarTheme(): AvatarTheme" in content
    assert "return 'blobs'" in content
    assert "'blobs', 'bland', 'default', 'bee', 'robot3d'" in content
    assert "ROBOT3D_THEME_RESERVED = 'robot3d'" in content
    assert "008-3d-robot-avatar-theme.md" in content


def test_req155_avatar_theme_picker_labels():
    repo_root = Path(__file__).resolve().parents[2]
    picker_path = repo_root / "webui" / "frontend" / "src" / "components" / "AvatarThemePicker.tsx"
    assert picker_path.exists()
    content = picker_path.read_text(encoding="utf-8")

    assert ">Default<" in content
    assert ">Blobs<" in content
    assert ">Bee<" in content
    assert ">3D robot<" in content
    assert "Robot3dComboPicker" in content
    assert "ADR-008" in content
    assert "optional choices" in content
    assert "never auto-applied" in content
