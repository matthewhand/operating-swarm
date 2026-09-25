"""Tests for GET/PUT /v1/blueprints/<id>/source (REQ-211)."""

import pytest
from django.urls import resolve


def test_blueprint_source_and_cli_agents_urls_accept_trailing_slash():
    """Slash + no-slash twins (same pattern as /v1/responses and /v1/chat/completions)."""
    assert resolve("/v1/blueprints/cli_fusion/source").url_name == "blueprint-source"
    assert resolve("/v1/blueprints/cli_fusion/source/").url_name == "blueprint-source-slash"
    assert resolve("/blueprint-library/cli_fusion/source/").url_name == "blueprint_source"
    assert resolve("/v1/cli-agents").url_name == "cli-agents-api-no-slash"
    assert resolve("/v1/cli-agents/").url_name == "cli-agents-api"


@pytest.mark.django_db
def test_source_returns_primary_file_and_content(client):
    resp = client.get("/v1/blueprints/cli_fusion/source")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "cli_fusion"
    assert data["primary"] == "blueprint_cli_fusion.py"
    assert data["selected"] == "blueprint_cli_fusion.py"
    assert any(f["name"] == "blueprint_cli_fusion.py" for f in data["files"])
    assert "class CliFusionBlueprint" in data["content"]
    assert data["editable"] is False
    assert data["origin"] == "bundled"
    assert "Bundled" in (data.get("readonly_reason") or "")


@pytest.mark.django_db
def test_source_unknown_blueprint_404(client):
    assert client.get("/v1/blueprints/definitely_not_a_blueprint_zzz/source").status_code == 404


@pytest.mark.django_db
def test_source_rejects_path_traversal(client):
    # Traversal outside the blueprint dir must 404 — never fall back to primary.
    resp = client.get("/v1/blueprints/cli_fusion/source", {"file": "../../settings.py"})
    assert resp.status_code == 404
    assert "error" in resp.json()


@pytest.mark.django_db
def test_source_missing_file_returns_404(client):
    """Explicit ?file= for a missing name is 404, not a silent primary fallback."""
    resp = client.get("/v1/blueprints/cli_fusion/source", {"file": "does_not_exist.py"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "file not found: does_not_exist.py"


@pytest.mark.django_db
def test_source_selects_requested_file(client):
    resp = client.get("/v1/blueprints/cli_fusion/source", {"file": "README.md"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"] == "README.md"
    assert data["primary"] == "blueprint_cli_fusion.py"
    assert len(data["content"]) > 0


@pytest.mark.django_db
def test_source_html_accept_is_pretty_python_not_json(client):
    """Browsers asking for HTML get highlighted Python, not the JSON envelope."""
    resp = client.get(
        "/v1/blueprints/cli_fusion/source/",
        HTTP_ACCEPT="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    )
    assert resp.status_code == 200
    assert "application/json" not in resp["Content-Type"]
    html = resp.content.decode()
    assert "language-python" in html
    assert "class CliFusionBlueprint" in html
    assert '"content":' not in html
    assert html.strip()[:1] != "{"


@pytest.mark.django_db
def test_source_json_accept_stays_json(client):
    resp = client.get(
        "/v1/blueprints/cli_fusion/source/",
        HTTP_ACCEPT="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "cli_fusion"
    assert "class CliFusionBlueprint" in data["content"]


@pytest.mark.django_db
def test_library_source_page_is_pretty_python(client, test_user):
    client.force_login(test_user)
    resp = client.get("/blueprint-library/cli_fusion/source/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "language-python" in html
    assert "class CliFusionBlueprint" in html
    assert '"primary":' not in html
    assert "os-source-save" not in html
    assert "Bundled checkout recipe" in html


@pytest.mark.django_db
def test_bundled_source_put_forks_to_user_library(client, tmp_path, monkeypatch):
    """REQ-919: editing a bundled recipe forks it to the user library —
    the copy shadows the original and the response says a copy was made."""
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)
    before = client.get("/v1/blueprints/cli_fusion/source").json()["content"]
    resp = client.put(
        "/v1/blueprints/cli_fusion/source",
        data={"content": "class CliFusionBlueprint:\n    forked = True\n"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["forked"] is True
    assert (tmp_path / "blueprints" / "cli_fusion").is_dir()
    after = client.get("/v1/blueprints/cli_fusion/source").json()
    assert after["origin"] == "user"
    assert after["editable"] is True
    # The checkout file's bytes are untouched.
    reread = client.get("/v1/blueprints/cli_fusion/source").json()
    assert "forked = True" in reread["content"]
    assert before is not None


@pytest.mark.django_db
def test_custom_source_get_put_and_invalid_rejected(client, monkeypatch):
    library = {
        "installed": [],
        "custom": [
            {
                "id": "my_custom_agent",
                "name": "My Custom Agent",
                "code": "class Ok:\n    pass\n",
            }
        ],
    }
    monkeypatch.setattr(
        "swarm.views.api_views.get_user_blueprint_library", lambda: library
    )
    monkeypatch.setattr(
        "swarm.views.api_views.save_user_blueprint_library", lambda _lib: True
    )

    got = client.get("/v1/blueprints/my_custom_agent/source")
    assert got.status_code == 200
    data = got.json()
    assert data["editable"] is True
    assert data["origin"] == "custom"
    assert data["content"] == "class Ok:\n    pass\n"
    assert data["readonly_reason"] is None

    bad = client.put(
        "/v1/blueprints/my_custom_agent/source",
        data={"content": "def (\n"},
        content_type="application/json",
    )
    assert bad.status_code == 400
    assert "syntax" in bad.json()["error"].lower()
    assert library["custom"][0]["code"] == "class Ok:\n    pass\n"

    good = "class Saved:\n    pass\n"
    ok = client.put(
        "/v1/blueprints/my_custom_agent/source",
        data={"content": good},
        content_type="application/json",
    )
    assert ok.status_code == 200
    saved = ok.json()
    assert saved["content"] == good
    assert saved["editable"] is True
    assert library["custom"][0]["code"] == good


@pytest.mark.django_db
def test_user_dir_source_put_writes_file(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    from swarm.core.paths import get_user_blueprints_dir

    bp_dir = get_user_blueprints_dir() / "user_recipe"
    bp_dir.mkdir(parents=True)
    target = bp_dir / "blueprint_user_recipe.py"
    original = "class Original:\n    pass\n"
    target.write_text(original)

    got = client.get("/v1/blueprints/user_recipe/source")
    assert got.status_code == 200
    assert got.json()["editable"] is True
    assert got.json()["origin"] == "user"
    assert "class Original" in got.json()["content"]

    bad = client.put(
        "/v1/blueprints/user_recipe/source",
        data={"content": "def (\n"},
        content_type="application/json",
    )
    assert bad.status_code == 400
    assert target.read_text() == original

    updated = "class Updated:\n    pass\n"
    ok = client.put(
        "/v1/blueprints/user_recipe/source",
        data={"content": updated},
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert ok.json()["content"] == updated
    assert target.read_text() == updated


@pytest.mark.django_db
def test_library_source_page_is_editor_for_custom(client, test_user, monkeypatch):
    library = {
        "installed": [],
        "custom": [
            {
                "id": "my_custom_agent",
                "name": "My Custom Agent",
                "code": "class Ok:\n    pass\n",
            }
        ],
    }
    monkeypatch.setattr(
        "swarm.views.api_views.get_user_blueprint_library", lambda: library
    )
    client.force_login(test_user)
    resp = client.get("/blueprint-library/my_custom_agent/source/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "os-source-editor" in html
    assert "os-source-save" in html
    assert "class Ok" in html
    assert "language-python" not in html


@pytest.mark.django_db
def test_cli_agents_endpoint_exposes_native_consensus(client):
    resp = client.get("/v1/cli-agents/")
    assert resp.status_code == 200
    data = resp.json()
    assert "grok" in data["clis"]
    assert data["native_consensus"]["grok"] == ["--best-of-n", "{n}"]
    assert data["catalog"]["grok"]["parse"] == "json:.text"
    assert data["list_models"]["opencode"] == ["opencode", "models"]
    assert "gemini" not in data["list_models"]  # #1142: deliberately unprobed
    assert data["list_models"]["codex"] == ["codex", "debug", "models"]
    assert data["list_sessions"]["grok"]["capability"] == "works"
    assert data["list_sessions"]["grok"]["list_argv"][:2] == ["grok", "sessions"]
    assert data["list_sessions"]["agy"]["list_store"] == "agy_conversations"
    assert data["list_sessions"]["claude"]["capability"] == "paste-only"


@pytest.mark.django_db
def test_cli_agent_models_urls_accept_trailing_slash():
    assert resolve("/v1/cli-agents/models").url_name == "cli-agent-models-all-no-slash"
    assert resolve("/v1/cli-agents/models/").url_name == "cli-agent-models-all"
    assert resolve("/v1/cli-agents/grok/models").url_name == "cli-agent-models-no-slash"
    assert resolve("/v1/cli-agents/grok/models/").url_name == "cli-agent-models"


@pytest.mark.django_db
def test_cli_agent_models_single_cli(client, monkeypatch):
    from swarm.core.cli_models import ListModelsResult

    monkeypatch.setattr(
        "swarm.core.cli_models.list_models",
        lambda name, **_k: ListModelsResult(cli=name, models=["grok-4"]),
    )
    resp = client.get("/v1/cli-agents/grok/models")
    assert resp.status_code == 200
    assert resp.json() == {"cli": "grok", "models": ["grok-4"]}


@pytest.mark.django_db
def test_cli_agent_models_unknown_cli_empty_warning(client, monkeypatch):
    from swarm.core.cli_models import ListModelsResult

    monkeypatch.setattr(
        "swarm.core.cli_models.list_models",
        lambda name, **_k: ListModelsResult(
            cli=name, models=[], warning="unknown CLI 'nope'"
        ),
    )
    resp = client.get("/v1/cli-agents/nope/models/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cli"] == "nope"
    assert data["models"] == []
    assert "unknown" in data["warning"]


@pytest.mark.django_db
def test_cli_agent_models_all(client, monkeypatch):
    from swarm.core.cli_models import ListModelsResult

    monkeypatch.setattr(
        "swarm.core.cli_models.list_models_all",
        lambda **_k: [
            ListModelsResult(cli="claude", models=[], warning="not installed"),
            ListModelsResult(cli="opencode", models=["opencode/big-pickle"]),
        ],
    )
    resp = client.get("/v1/cli-agents/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["models"] == []
    assert data[1] == {"cli": "opencode", "models": ["opencode/big-pickle"]}


# --- #537: POST /v1/blueprints/<id>/source/format — a proposal, not a save ---


@pytest.mark.django_db
def test_format_endpoint_pretty_prints_a_proposal(client, monkeypatch):
    """Formatting fills the draft — it must never write to disk."""
    monkeypatch.setenv("SWARM_USER_DATA_DIR", "/tmp/format-537-must-not-exist")
    from swarm.core.paths import get_user_blueprints_dir

    bp_dir = get_user_blueprints_dir() / "user_recipe_fmt"
    bp_dir.mkdir(parents=True, exist_ok=True)
    target = bp_dir / "blueprint_user_recipe_fmt.py"
    original = "def f( a,b ):\n  return a+b  # keep\n"
    target.write_text(original)

    resp = client.post(
        "/v1/blueprints/user_recipe_fmt/source/format",
        data={"content": original, "file": "blueprint_user_recipe_fmt.py"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["formatted"] != original
    assert "def f(a, b):" in body["formatted"]
    assert "# keep" in body["formatted"]
    # Proposal, not a save:
    assert target.read_text() == original


@pytest.mark.django_db
def test_format_endpoint_rejects_non_python_files(client):
    resp = client.post(
        "/v1/blueprints/cli_fusion/source/format",
        data={"content": "# md", "file": "README.md"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "python" in resp.json()["error"].lower()


@pytest.mark.django_db
def test_format_endpoint_requires_content(client):
    resp = client.post(
        "/v1/blueprints/cli_fusion/source/format",
        data={},
        content_type="application/json",
    )
    assert resp.status_code == 400
