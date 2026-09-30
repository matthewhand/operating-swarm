"""Tests for the injectable filesystem toolset (safety + permission levels)."""
from __future__ import annotations

import pytest

from swarm.core.filesystem_toolset import (
    FilesystemError,
    FilesystemToolset,
    PathNotAllowed,
    PermissionDenied,
    SensitivePathDenied,
)


@pytest.fixture
def sandbox(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world", encoding="utf-8")
    return tmp_path


def test_read_within_allowlist(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    assert fs.read(str(sandbox / "a.txt")) == "hello"


def test_read_outside_allowlist_denied(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    with pytest.raises(PathNotAllowed):
        fs.read("/etc/passwd")


def test_list_and_stat(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    names = {e["name"] for e in fs.list(str(sandbox))}
    assert {"a.txt", "sub"} <= names
    assert fs.stat(str(sandbox / "a.txt"))["type"] == "file"


def test_readonly_blocks_write(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    with pytest.raises(PermissionDenied):
        fs.write(str(sandbox / "new.txt"), "x")


def test_none_blocks_read(sandbox):
    fs = FilesystemToolset(permission="none", allowed_paths=[str(sandbox)])
    with pytest.raises(PermissionDenied):
        fs.read(str(sandbox / "a.txt"))


def test_readwrite_allows_write(sandbox):
    fs = FilesystemToolset(permission="readwrite", allowed_paths=[str(sandbox)])
    fs.write(str(sandbox / "new.txt"), "data")
    assert fs.read(str(sandbox / "new.txt")) == "data"


def test_read_size_cap(sandbox):
    big = sandbox / "big.txt"
    big.write_text("x" * 5000, encoding="utf-8")
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)], max_read_bytes=100)
    out = fs.read(str(big))
    assert "truncated" in out and len(out) < 5000


def test_read_line_range_respects_max_read_bytes(sandbox):
    """Line-range / head must not bypass max_read_bytes (regression)."""
    big = sandbox / "many_lines.txt"
    big.write_text("\n".join(f"line{i}" for i in range(5000)), encoding="utf-8")
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)], max_read_bytes=80)
    ranged = fs.read(str(big), start_line=1, end_line=4000)
    assert "truncated" in ranged
    assert len(ranged.encode("utf-8")) < 5000
    headed = fs.head(str(big), n=4000)
    assert "truncated" in headed
    assert len(headed.encode("utf-8")) < 5000


def test_tail_respects_max_read_bytes(sandbox):
    big = sandbox / "huge_log.txt"
    big.write_text("\n".join(f"line{i}" for i in range(5000)), encoding="utf-8")
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)], max_read_bytes=80)
    out = fs.tail(str(big), n=4000)
    assert "truncated" in out
    assert len(out.encode("utf-8")) < 5000


def test_request_cannot_escalate_to_readwrite(sandbox):
    # config grants readonly; a per-request override asking for readwrite is ignored.
    cfg = {"filesystem": {"permission": "readonly", "allowed_paths": [str(sandbox)]}}
    fs = FilesystemToolset.from_config(cfg, overrides={"permission": "readwrite"})
    assert fs.permission == "readonly"
    with pytest.raises(PermissionDenied):
        fs.write(str(sandbox / "x.txt"), "y")


def test_request_cannot_escalate_none_to_readonly(sandbox):
    """Config ``none`` must not become ``readonly`` via per-request overrides."""
    cfg = {"filesystem": {"permission": "none", "allowed_paths": [str(sandbox)]}}
    fs = FilesystemToolset.from_config(cfg, overrides={"permission": "readonly"})
    assert fs.permission == "none"
    with pytest.raises(PermissionDenied):
        fs.read(str(sandbox / "a.txt"))
    fs_rw = FilesystemToolset.from_config(cfg, overrides={"permission": "readwrite"})
    assert fs_rw.permission == "none"


def test_request_may_deescalate_permission(sandbox):
    """Overrides may still lower rights (readwrite → readonly / none)."""
    cfg = {"filesystem": {"permission": "readwrite", "allowed_paths": [str(sandbox)]}}
    fs = FilesystemToolset.from_config(cfg, overrides={"permission": "readonly"})
    assert fs.permission == "readonly"
    with pytest.raises(PermissionDenied):
        fs.write(str(sandbox / "x.txt"), "y")
    assert fs.read(str(sandbox / "a.txt")) == "hello"


def test_request_cannot_widen_allowed_paths_to_root(sandbox):
    """Per-request allowed_paths must not expand beyond configured roots."""
    cfg = {"filesystem": {"permission": "readonly", "allowed_paths": [str(sandbox)]}}
    fs = FilesystemToolset.from_config(cfg, overrides={"allowed_paths": ["/"]})
    assert fs._roots == [sandbox.resolve()]
    with pytest.raises(PathNotAllowed):
        fs.read("/etc/passwd")
    assert fs.read(str(sandbox / "a.txt")) == "hello"


def test_request_may_narrow_allowed_paths(sandbox):
    """Overrides may restrict access to a subdirectory of a configured root."""
    cfg = {"filesystem": {"permission": "readonly", "allowed_paths": [str(sandbox)]}}
    sub = sandbox / "sub"
    fs = FilesystemToolset.from_config(cfg, overrides={"allowed_paths": [str(sub)]})
    assert fs.read(str(sub / "b.txt")) == "world"
    with pytest.raises(PathNotAllowed):
        fs.read(str(sandbox / "a.txt"))


def test_request_cannot_raise_max_read_bytes(sandbox):
    """Overrides may lower max_read_bytes but never raise it above config."""
    cfg = {
        "filesystem": {
            "permission": "readonly",
            "allowed_paths": [str(sandbox)],
            "max_read_bytes": 100,
        }
    }
    fs = FilesystemToolset.from_config(cfg, overrides={"max_read_bytes": 10_000_000})
    assert fs.max_read_bytes == 100
    fs_low = FilesystemToolset.from_config(cfg, overrides={"max_read_bytes": 50})
    assert fs_low.max_read_bytes == 50


def test_not_a_file(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    with pytest.raises(FilesystemError):
        fs.read(str(sandbox / "sub"))  # it's a dir


def test_read_line_range(sandbox):
    (sandbox / "lines.txt").write_text("L1\nL2\nL3\nL4\nL5", encoding="utf-8")
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    out = fs.read(str(sandbox / "lines.txt"), start_line=2, end_line=3)
    assert out == "2: L2\n3: L3"


def test_grep_file_and_dir(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    # a.txt="hello", sub/b.txt="world"
    assert "a.txt:1: hello" in fs.grep("hel", str(sandbox))
    assert "no matches" in fs.grep("zzz_nomatch", str(sandbox))


def test_find_glob(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    out = fs.find("*.txt", str(sandbox))
    assert "a.txt" in out and "b.txt" in out


def test_grep_bad_regex(sandbox):
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    with pytest.raises(FilesystemError):
        fs.grep("(unclosed", str(sandbox))


def test_head_and_tail(sandbox):
    (sandbox / "log.txt").write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    assert fs.head(str(sandbox / "log.txt"), 2) == "1: line1\n2: line2"
    assert fs.tail(str(sandbox / "log.txt"), 2) == "9: line9\n10: line10"


def test_dotenv_and_private_keys_denied_inside_allowlist(sandbox):
    """Credential files stay opaque even when their parent root is allow-listed."""
    (sandbox / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    (sandbox / ".env.local").write_text("TOKEN=x\n", encoding="utf-8")
    (sandbox / "id_rsa").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    (sandbox / "tls.pem").write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    (sandbox / "ok.txt").write_text("safe", encoding="utf-8")
    fs = FilesystemToolset(permission="readonly", allowed_paths=[str(sandbox)])
    for name in (".env", ".env.local", "id_rsa", "tls.pem"):
        with pytest.raises(SensitivePathDenied):
            fs.read(str(sandbox / name))
    assert fs.read(str(sandbox / "ok.txt")) == "safe"
    names = {e["name"] for e in fs.list(str(sandbox))}
    assert "ok.txt" in names
    assert ".env" not in names
    assert "id_rsa" not in names
    assert "OPENAI_API_KEY" not in fs.grep("OPENAI", str(sandbox))
    assert str(sandbox / ".env") not in fs.find(".env", str(sandbox))


def test_default_roots_exclude_project_checkout():
    """Bare defaults must not include ~/open-swarm (repo .env dump vector)."""
    assert all("open-swarm" not in r for r in FilesystemToolset.default_roots())
    fs = FilesystemToolset()
    assert all("open-swarm" not in str(r) for r in fs._roots)
