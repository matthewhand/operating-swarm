"""Issue #1256 — GET /v1/fs/directories/ (agent Folder server picker).

Hermetic: browse roots are pointed at a tmp_path tree via
``SWARM_FS_BROWSE_ROOTS`` so no real home directory is read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core.fs_browse import get_browse_roots

User = get_user_model()

URL = "/v1/fs/directories/"


@pytest.fixture(autouse=True)
def disable_api_auth(settings):
    settings.ENABLE_API_AUTH = False


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def browse_root(tmp_path, monkeypatch):
    """A tmp tree set as the only browse root: root/{alpha(git), beta, .hidden, file}."""
    root = tmp_path / "browse-root"
    root.mkdir()
    (root / "alpha").mkdir()
    (root / "alpha" / ".git").mkdir()
    (root / "beta").mkdir()
    (root / ".hidden").mkdir()
    (root / "not-a-dir.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setenv("SWARM_FS_BROWSE_ROOTS", str(root))
    monkeypatch.delenv("ALLOW_UNRESTRICTED_WORKDIR", raising=False)
    return root


def test_urls_accept_trailing_slash():
    assert resolve("/v1/fs/directories").url_name == "fs-directories-no-slash"
    assert resolve("/v1/fs/directories/").url_name == "fs-directories"


def test_defaults_to_home_when_path_omitted(tmp_path, monkeypatch, api_client):
    monkeypatch.delenv("SWARM_FS_BROWSE_ROOTS", raising=False)
    home = Path.home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "projects").mkdir(exist_ok=True)

    response = api_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(home.resolve())
    assert body["parent"] is None
    assert "projects" in [entry["name"] for entry in body["entries"]]
    assert body["roots"] == [str(root) for root in get_browse_roots()]


@pytest.mark.django_db
def test_lists_only_child_directories_sorted_with_git_flag(browse_root, api_client):
    response = api_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(browse_root.resolve())
    assert body["parent"] is None  # at the top of the configured root

    names = [entry["name"] for entry in body["entries"]]
    assert names == [".hidden", "alpha", "beta"]  # dirs only, case-sorted
    assert "not-a-dir.txt" not in names

    by_name = {entry["name"]: entry for entry in body["entries"]}
    assert by_name["alpha"]["is_git_repo"] is True
    assert by_name["alpha"]["path"] == str(browse_root / "alpha")
    assert by_name["beta"]["is_git_repo"] is False
    # No file contents or secret-shaped fields leak.
    assert set(by_name["alpha"]) == {"name", "path", "is_git_repo"}


@pytest.mark.django_db
def test_nested_listing_reports_parent_and_navigates_up(browse_root, api_client):
    down = api_client.get(URL, {"path": str(browse_root / "alpha")})
    assert down.status_code == 200
    down_body = down.json()
    assert down_body["path"] == str((browse_root / "alpha").resolve())
    assert down_body["parent"] == str(browse_root.resolve())
    assert [entry["name"] for entry in down_body["entries"]] == [".git"]

    up = api_client.get(URL, {"path": down_body["parent"]})
    assert up.status_code == 200
    assert up.json()["path"] == str(browse_root.resolve())


@pytest.mark.django_db
def test_relative_path_joins_under_default_root(browse_root, api_client):
    response = api_client.get(URL, {"path": "beta"})
    assert response.status_code == 200
    assert response.json()["path"] == str((browse_root / "beta").resolve())


@pytest.mark.django_db
def test_rejects_path_outside_browse_roots(tmp_path, browse_root, api_client):
    outside = tmp_path / "outside"
    outside.mkdir()
    response = api_client.get(URL, {"path": str(outside)})
    assert response.status_code == 403
    assert "outside the permitted browse roots" in response.json()["error"]


@pytest.mark.django_db
def test_rejects_dotdot_escape(browse_root, api_client):
    response = api_client.get(URL, {"path": "../outside"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_rejects_symlink_escape_in_listing(tmp_path, browse_root, api_client):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = browse_root / "link-out"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    names = [entry["name"] for entry in api_client.get(URL).json()["entries"]]
    assert "link-out" not in names  # resolves outside the allowed root

    response = api_client.get(URL, {"path": str(link)})
    assert response.status_code == 403


@pytest.mark.django_db
def test_missing_path_is_404_and_file_is_400(browse_root, api_client):
    missing = api_client.get(URL, {"path": str(browse_root / "nope")})
    assert missing.status_code == 404
    assert "does not exist" in missing.json()["error"]

    file_resp = api_client.get(URL, {"path": str(browse_root / "not-a-dir.txt")})
    assert file_resp.status_code == 400
    assert "not a directory" in file_resp.json()["error"]


@pytest.mark.django_db
def test_unrestricted_escape_allows_arbitrary_root(tmp_path, monkeypatch, api_client):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "project").mkdir()
    monkeypatch.setenv("SWARM_FS_BROWSE_ROOTS", str(allowed))
    monkeypatch.setenv("ALLOW_UNRESTRICTED_WORKDIR", "true")

    response = api_client.get(URL, {"path": str(elsewhere)})
    assert response.status_code == 200
    assert [entry["name"] for entry in response.json()["entries"]] == ["project"]


@pytest.mark.django_db
def test_requires_auth_when_enabled(settings, browse_root, api_client):
    settings.ENABLE_API_AUTH = True
    assert api_client.get(URL).status_code in (401, 403)

    user = User.objects.create_user("alice", password="pw")
    authed = APIClient()
    authed.force_login(user)
    assert authed.get(URL).status_code == 200


@pytest.mark.django_db
def test_never_returns_file_names_or_secrets(browse_root, api_client):
    (browse_root / "secret.env").write_text("API_KEY=sk-123", encoding="utf-8")
    body = api_client.get(URL).json()
    blob = str(body)
    assert "secret.env" not in blob
    assert "sk-123" not in blob
