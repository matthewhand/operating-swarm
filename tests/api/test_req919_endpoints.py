"""REQ-919 endpoint tests: DELETE /source and POST /v1/blueprints/upload."""

import base64
import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import resolve

from swarm.core.blueprint_source import save_blueprint_source


def test_delete_and_upload_urls_resolve():
    assert resolve("/v1/blueprints/upload").url_name == "blueprint-upload"
    assert resolve("/v1/blueprints/upload/").url_name == "blueprint-upload-slash"


@pytest.mark.django_db
def test_delete_user_recipe_removes_tree(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)
    save_blueprint_source("cli_fusion", "class CliFusionBlueprint:\n    pass\n")

    resp = client.delete("/v1/blueprints/cli_fusion/source")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # The bundled original is visible again (the shadowing copy is gone).
    assert client.get("/v1/blueprints/cli_fusion/source").json()["origin"] == "bundled"


@pytest.mark.django_db
def test_delete_bundled_tombstones_and_hides(client):
    resp = client.delete("/v1/blueprints/cli_fusion/source")
    assert resp.status_code == 200
    assert resp.json()["tombstoned"] is True
    hidden = client.get("/v1/blueprints/cli_fusion/source")
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_upload_multipart_py_creates_recipe(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)

    resp = client.post(
        "/v1/blueprints/upload",
        data={
            "id": "uploaded_api",
            "file": SimpleUploadedFile(
                "blueprint_uploaded_api.py", b"class Ok:\n    pass\n"
            ),
        },
        format="multipart",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["uploaded"] is True
    got = client.get("/v1/blueprints/uploaded_api/source")
    assert got.status_code == 200
    assert "class Ok:" in got.json()["content"]


@pytest.mark.django_db
def test_upload_json_zip_roundtrip(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("blueprint_zipack.py", "class Ok:\n    pass\n")
        zf.writestr("README.md", "# zipack\n")
    resp = client.post(
        "/v1/blueprints/upload",
        data={
            "id": "zipack",
            "filename": "zipack.zip",
            "content_b64": base64.b64encode(buf.getvalue()).decode(),
        },
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.json()
    files = client.get("/v1/blueprints/zipack/source").json()["files"]
    assert any(f["name"] == "README.md" for f in files)


@pytest.mark.django_db
def test_upload_traversal_zip_is_400_and_writes_nothing(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.py", "class Evil:\n    pass\n")
    resp = client.post(
        "/v1/blueprints/upload",
        data={
            "id": "evilbp",
            "filename": "evil.zip",
            "content_b64": base64.b64encode(buf.getvalue()).decode(),
        },
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "traversal" in (resp.json().get("error") or "").lower()
    assert not (tmp_path / "evil.py").exists()


@pytest.mark.django_db
def test_upload_collision_is_409(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)
    first = client.post(
        "/v1/blueprints/upload",
        data={
            "id": "dupe",
            "file": SimpleUploadedFile("blueprint_dupe.py", b"class Ok:\n    pass\n"),
        },
        format="multipart",
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/blueprints/upload",
        data={
            "id": "dupe",
            "file": SimpleUploadedFile("blueprint_dupe.py", b"class Two:\n    pass\n"),
        },
        format="multipart",
    )
    assert second.status_code == 409
