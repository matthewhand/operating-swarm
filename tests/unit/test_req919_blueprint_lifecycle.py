"""REQ-919 / #538 — every blueprint is editable, deletable and uploadable.

The refusal message ("Bundled checkout recipe — not writable…") was the bug.
Model:
- **Edit** a bundled/marketplace recipe → fork-on-write: copy its tree into
  the user blueprints dir, then edit the copy (which shadows the bundled
  original via existing precedence). The response says a copy was made.
- **Delete** a bundled recipe → a tombstone hides it from listings; the
  checkout file is never touched. A user-dir delete removes the tree.
- **Upload** → one ``.py`` becomes a user-dir recipe; a zip/tar extracts into
  ``get_user_blueprints_dir()/<id>/`` after path-traversal rejection, a size
  cap, the suffix filter, and sandbox validation of every ``.py`` — before
  anything is written.
"""

import io
import zipfile

import pytest

from swarm.core import blueprint_source as bs
from swarm.core.blueprint_source import (
    ORIGIN_BUNDLED,
    ORIGIN_USER,
    load_blueprint_source,
    resolve_blueprint_origin,
    save_blueprint_source,
)


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)
    return tmp_path / "blueprints"


class TestForkOnWrite:
    @pytest.mark.usefixtures("user_dir")
    def test_editing_a_bundled_recipe_copies_it_to_user_dir(self):
        assert resolve_blueprint_origin("cli_fusion") == ORIGIN_BUNDLED
        payload, code = save_blueprint_source(
            "cli_fusion", "class CliFusionBlueprint:\n    pass\n"
        )
        assert code == 200, payload
        assert payload.get("forked") is True, "the copy must never be silent"
        # The fork shadows the bundled original.
        assert resolve_blueprint_origin("cli_fusion") == ORIGIN_USER
        # The checkout file is untouched.
        reread, _ = load_blueprint_source("cli_fusion")
        assert "class CliFusionBlueprint:" in reread["content"]
        assert 'print("nope")' not in reread["content"]

    @pytest.mark.usefixtures("user_dir")
    def test_fork_copies_sibling_files_too(self):
        payload, code = save_blueprint_source(
            "cli_fusion", "class CliFusionBlueprint:\n    pass\n"
        )
        assert code == 200
        files = {f["name"] for f in payload["files"]}
        assert "README.md" in files, "the fork carries the recipe's other files"

    @pytest.mark.usefixtures("user_dir")
    def test_forked_copy_is_fully_editable_afterwards(self):
        save_blueprint_source("cli_fusion", "class CliFusionBlueprint:\n    pass\n")
        second, code = save_blueprint_source(
            "cli_fusion", "class CliFusionBlueprint:\n    variant = True\n"
        )
        assert code == 200
        assert second.get("forked") is not True, "the second edit edits in place"

    @pytest.mark.usefixtures("user_dir")
    def test_invalid_python_leaves_the_fork_absent(self):
        before = resolve_blueprint_origin("cli_fusion")
        payload, code = save_blueprint_source("cli_fusion", "def (\n")
        assert code == 400
        assert resolve_blueprint_origin("cli_fusion") == before


class TestDelete:
    @pytest.mark.usefixtures("user_dir")
    def test_delete_user_recipe_removes_the_tree(self):
        save_blueprint_source("cli_fusion", "class CliFusionBlueprint:\n    pass\n")
        assert resolve_blueprint_origin("cli_fusion") == ORIGIN_USER
        payload, code = bs.delete_blueprint("cli_fusion")
        assert code == 200
        assert resolve_blueprint_origin("cli_fusion") == ORIGIN_BUNDLED
        assert payload.get("tombstoned") is not True

    @pytest.mark.usefixtures("user_dir")
    def test_delete_bundled_tombstones_without_touching_the_checkout(self):
        payload, code = bs.delete_blueprint("cli_fusion")
        assert code == 200
        assert payload.get("tombstoned") is True
        # Hidden from loads…
        assert resolve_blueprint_origin("cli_fusion") is None
        assert load_blueprint_source("cli_fusion")[1] == 404
        # …but the checkout file still exists on disk (pristine repo).
        from swarm.core.blueprint_source import _bundled_base, _confined_dir

        checkout = _confined_dir(_bundled_base(), "cli_fusion")
        assert checkout is not None and checkout.is_dir()

    @pytest.mark.usefixtures("user_dir")
    def test_tombstone_is_idempotent(self):
        bs.delete_blueprint("cli_fusion")
        payload, code = bs.delete_blueprint("cli_fusion")
        assert code == 404
        assert payload.get("tombstoned") is True

    @pytest.mark.usefixtures("user_dir")
    def test_unknown_blueprint_404(self):
        payload, code = bs.delete_blueprint("definitely_not_zzz")
        assert code == 404


class TestUpload:
    def _zip_bytes(self, files: dict[str, str]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    @pytest.mark.usefixtures("user_dir")
    def test_single_py_upload_creates_user_recipe(self):
        payload, code = bs.upload_blueprint_archive(
            "uploaded_one",
            b"class Ok:\n    pass\n",
            filename="blueprint_uploaded_one.py",
        )
        assert code == 201, payload
        assert resolve_blueprint_origin("uploaded_one") == ORIGIN_USER

    @pytest.mark.usefixtures("user_dir")
    def test_zip_upload_extracts_into_user_dir(self):
        data = self._zip_bytes(
            {
                "blueprint_pack.py": "class Ok:\n    pass\n",
                "README.md": "# pack\n",
            }
        )
        payload, code = bs.upload_blueprint_archive(
            "pack", data, filename="pack.zip"
        )
        assert code == 201, payload
        reread, lcode = load_blueprint_source("pack")
        assert lcode == 200
        assert "class Ok:" in reread["content"]
        assert any(f["name"] == "README.md" for f in reread["files"])

    @pytest.mark.usefixtures("user_dir")
    def test_tar_gz_upload_extracts(self):
        import tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo("blueprint_tarpack.py")
            content = b"class Ok:\n    pass\n"
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        payload, code = bs.upload_blueprint_archive(
            "tarpack", buf.getvalue(), filename="tarpack.tar.gz"
        )
        assert code == 201, payload
        assert resolve_blueprint_origin("tarpack") == ORIGIN_USER

    def test_traversal_entries_are_refused_and_nothing_is_written(self, user_dir):
        data = self._zip_bytes(
            {
                "../evil.py": "class Evil:\n    pass\n",
                "blueprint_ok.py": "class Ok:\n    pass\n",
            }
        )
        payload, code = bs.upload_blueprint_archive("evil", data, filename="evil.zip")
        assert code == 400
        assert "traversal" in (payload.get("error") or "").lower()
        assert resolve_blueprint_origin("evil") is None
        assert not (user_dir / "evil.py").exists()

    @pytest.mark.usefixtures("user_dir")
    def test_absolute_and_hidden_entries_refused(self):
        data = self._zip_bytes({"/abs.py": "x = 1\n", ".hidden.py": "x = 2\n"})
        payload, code = bs.upload_blueprint_archive("absbp", data, filename="a.zip")
        assert code == 400

    @pytest.mark.usefixtures("user_dir")
    def test_oversized_archive_refused(self):
        data = b"x" * (bs.MAX_UPLOAD_BYTES + 1)
        payload, code = bs.upload_blueprint_archive("big", data, filename="big.zip")
        assert code == 413

    @pytest.mark.usefixtures("user_dir")
    def test_disallowed_suffix_refused(self):
        data = self._zip_bytes({"run.sh": "rm -rf /\n"})
        payload, code = bs.upload_blueprint_archive("shbp", data, filename="s.zip")
        assert code == 400

    @pytest.mark.usefixtures("user_dir")
    def test_invalid_python_refused_and_library_unchanged(self):
        payload, code = bs.upload_blueprint_archive(
            "broken", b"def (\n", filename="blueprint_broken.py"
        )
        assert code == 400
        assert resolve_blueprint_origin("broken") is None
        reread, rcode = load_blueprint_source("broken")
        assert rcode == 404 and "error" in reread, "nothing was written"

    @pytest.mark.usefixtures("user_dir")
    def test_id_collision_refused_never_silent_overwrite(self):
        ok, code = bs.upload_blueprint_archive(
            "mine", b"class Ok:\n    pass\n", filename="blueprint_mine.py"
        )
        assert code == 201
        payload, code = bs.upload_blueprint_archive(
            "mine", b"class Two:\n    pass\n", filename="blueprint_mine.py"
        )
        assert code == 409, "refuse or fork — never silently overwrite"
        reread, _ = load_blueprint_source("mine")
        assert "class Ok:" in reread["content"]

    @pytest.mark.usefixtures("user_dir")
    def test_unsupported_archive_format_400(self):
        payload, code = bs.upload_blueprint_archive(
            "binbp", b"\x00\x01\x02", filename="blob.bin"
        )
        assert code == 400
