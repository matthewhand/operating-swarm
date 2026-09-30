"""#1390 per-agent memory store — CRUD, tier filter, scrub, pack fragment."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from swarm.core import agent_memory as store
from swarm.core.memory_scrubber import (
    contains_credentials,
    omit_private_payload,
    redact_credentials,
    reject_credentials,
    scrub_for_pack,
)

# Fake credential *shapes* only — not live secrets.
FAKE_OPENAI = "sk-notarealkeyABCDEFGH"
FAKE_GITHUB = "ghp_notarealsecret0123456789abcd"
FAKE_EMAIL = "ada@example.test"
FAKE_PRIVATE_LINK = "http://127.0.0.1:9/internal"
FAKE_LAN_LINK = "http://10.1.2.4:8080/ops"
FAKE_USERINFO_LINK = "http://alice:s3cret@10.1.2.3/admin"
FAKE_METADATA_LINK = "http://169.254.169.254/latest/meta-data"
FAKE_HOME = "~/.ssh/id_ed25519"
FAKE_PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "AAAAB3NzaC1yc2EAAAADAQABAAABgQC7fake\n"
    "-----END OPENSSH PRIVATE KEY-----"
)
FAKE_AWS = "AKIAFAKEKEY123456789"
FAKE_AWS_TEMP = "ASIAFAKEKEY123456789"
FAKE_PHONE = "415-555-1212"
FAKE_BUILD = "2024092712"


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_MEMORIES_PATH", str(tmp_path / "agent_memories.json"))
    store.reset_memories_cache()


def test_scrubber_rejects_and_redacts_credential_shapes():
    assert contains_credentials(f"key {FAKE_OPENAI}") is True
    assert contains_credentials(f"token {FAKE_GITHUB}") is True
    assert contains_credentials("Prefers short answers.") is False
    with pytest.raises(ValueError, match="credential"):
        reject_credentials(f"keep {FAKE_OPENAI}", "body")
    redacted = redact_credentials(f"use {FAKE_OPENAI} then stop")
    assert FAKE_OPENAI not in redacted
    assert "[REDACTED]" in redacted


def test_scrubber_omits_pii_and_private_links():
    text = (
        f"Write {FAKE_EMAIL} at {FAKE_PRIVATE_LINK} or {FAKE_LAN_LINK} "
        "and keep the public motto."
    )
    cleaned = omit_private_payload(text)
    assert FAKE_EMAIL not in cleaned
    assert FAKE_PRIVATE_LINK not in cleaned
    assert FAKE_LAN_LINK not in cleaned
    assert "public motto" in cleaned
    packed = scrub_for_pack(f"api_key={FAKE_OPENAI} {FAKE_EMAIL}")
    assert FAKE_OPENAI not in packed
    assert FAKE_EMAIL not in packed


def test_scrubber_covers_private_keys_userinfo_and_spares_digit_runs():
    assert contains_credentials(FAKE_PEM) is True
    assert contains_credentials(FAKE_AWS) is True
    assert contains_credentials(FAKE_AWS_TEMP) is True
    redacted = redact_credentials(f"key follows\n{FAKE_PEM}\nend")
    assert "PRIVATE KEY" not in redacted
    assert "AAAAB3" not in redacted
    assert FAKE_AWS not in redact_credentials(f"id {FAKE_AWS}")
    assert FAKE_AWS_TEMP not in redact_credentials(f"id {FAKE_AWS_TEMP}")

    text = (
        f"Dash {FAKE_USERINFO_LINK} meta {FAKE_METADATA_LINK} "
        f"home {FAKE_HOME} phone {FAKE_PHONE} build {FAKE_BUILD} "
        "and https://example.com/docs stays."
    )
    cleaned = omit_private_payload(text)
    assert FAKE_USERINFO_LINK not in cleaned
    assert "10.1.2.3" not in cleaned
    assert FAKE_METADATA_LINK not in cleaned
    assert FAKE_HOME not in cleaned
    assert FAKE_PHONE not in cleaned
    assert FAKE_BUILD in cleaned
    assert "https://example.com/docs" in cleaned
    with pytest.raises(ValueError, match="credential"):
        reject_credentials(FAKE_PEM, "body")


def test_scrubber_keeps_public_paths_and_hostname_suffixes():
    kept = omit_private_payload(
        "https://example.com/root/cause "
        "https://example.com/home/docs "
        "https://example.com/Users/docs "
        "localhost.example.com "
        "https://localhost.example.com/docs "
        "https://10.1.2.3.example.com/docs "
        "https://example.com/~/alice "
        "https://example.com//home/docs "
        "../root/not-absolute "
        "end~/not-a-home"
    )
    assert "https://example.com/root/cause" in kept
    assert "https://example.com/home/docs" in kept
    assert "https://example.com/Users/docs" in kept
    assert "localhost.example.com" in kept
    assert "https://localhost.example.com/docs" in kept
    assert "https://10.1.2.3.example.com/docs" in kept
    assert "https://example.com/~/alice" in kept
    assert "https://example.com//home/docs" in kept
    assert "../root/not-absolute" in kept
    assert "end~/not-a-home" in kept

    dropped = omit_private_payload(
        "see ~/.ssh/id_ed25519 and /root/secret and /home/ada/keys "
        "and localhost:8080/x and http://127.0.0.1:9/internal"
    )
    assert "~/.ssh" not in dropped
    assert "/root/secret" not in dropped
    assert "/home/ada" not in dropped
    assert "localhost:8080" not in dropped
    assert "127.0.0.1" not in dropped

    punct = omit_private_payload(
        "note `/home/ada/.ssh/id_ed25519` "
        '"/root/secret" '
        "'/Users/ada/keys' "
        "dir=/home/ada/keys path=~/.ssh/id_ed25519 "
        "HOME=/home/ada see:/root/secret "
        "localhost.localdomain and localhost.local"
    )
    assert "/home/ada" not in punct
    assert "/root/secret" not in punct
    assert "/Users/ada" not in punct
    assert "~/.ssh" not in punct
    assert "HOME=/home/ada" not in punct
    assert "localhost.localdomain" not in punct
    assert "localhost.local" not in punct
    # An empty scrub would also hide those tokens. The surrounding prose stays.
    assert "note" in punct
    assert "dir=" in punct
    assert "path=" in punct
    assert "HOME=" in punct
    assert "see:" in punct


def test_scrubber_bounds_private_paths_without_eating_public_urls():
    kept = omit_private_payload(
        "https://en.wikipedia.org/wiki/localhost.localdomain "
        "https://example.com/localhost.local "
        "https://app.example.com/#/home/dashboard "
        "https://app.example.com/#/root/settings "
        "https://example.com/foo-/home/ada "
        "https://example.com/~ada/pub "
        "https://files.localdomain.com/a "
        "https://printer.localdomain.example.com/x "
        "https://not.localhost.example.com/docs "
        "http://localhost.localdomain.example.com/docs "
        "https://shopping.local.com/x "
        "https://127.0.0.1.example.com/docs "
        "my-localhost /homepage /rootkit /Users.html ~1.2/beta"
    )
    for piece in (
        "https://en.wikipedia.org/wiki/localhost.localdomain",
        "https://example.com/localhost.local",
        "https://app.example.com/#/home/dashboard",
        "https://app.example.com/#/root/settings",
        "https://example.com/foo-/home/ada",
        "https://example.com/~ada/pub",
        "https://files.localdomain.com/a",
        "https://printer.localdomain.example.com/x",
        "https://not.localhost.example.com/docs",
        "http://localhost.localdomain.example.com/docs",
        "https://shopping.local.com/x",
        "https://127.0.0.1.example.com/docs",
        "my-localhost",
        "/homepage",
        "/rootkit",
        "/Users.html",
        "~1.2/beta",
    ):
        assert piece in kept, piece

    dropped = omit_private_payload(
        "http://localhost.localdomain/admin "
        "https://localhost.local/admin "
        "https://printer.local/admin "
        "https://a.b.local/secret "
        "https://printer.localdomain/admin "
        "https://example.localhost/foo "
        "//localhost/admin "
        "~ada/.ssh/id_ed25519 "
        "path=~ada/.ssh/id "
        "HOME=/home /root /Users "
        "see:/root/secret"
    )
    for piece in (
        "localhost.localdomain",
        "localhost.local",
        "printer.local",
        "a.b.local",
        "printer.localdomain",
        "example.localhost",
        "//localhost",
        "~ada",
        "/home",
        "/root",
        "/Users",
        "see:/root",
    ):
        assert piece not in dropped, piece
    assert "path=" in dropped
    assert "HOME=" in dropped
    assert "see:" in dropped

    query = omit_private_payload("https://example.com/search?path=/home/ada")
    assert query == "https://example.com/search?path="
    assert omit_private_payload("//example.com/root/cause") == "//example.com/root/cause"


def test_list_empty_then_create_and_delete(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert store.list_memories("codey") == []
    created = store.create_memory(
        "codey",
        {"kind": "profile", "title": "Voice", "body": "Prefers short answers."},
    )
    assert created["kind"] == "profile"
    assert created["tier"] == "pack"
    assert created["title"] == "Voice"
    assert created["body"] == "Prefers short answers."
    assert created["id"]
    listed = store.list_memories("codey")
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]
    assert store.delete_memory("codey", created["id"]) is True
    assert store.list_memories("codey") == []
    assert store.delete_memory("codey", created["id"]) is False


def test_create_rejects_credential_shaped_body(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="credential"):
        store.create_memory(
            "codey",
            {"kind": "log", "body": f"token {FAKE_GITHUB}"},
        )
    assert store.list_memories("codey") == []


def test_tier_filter_excludes_local_kinds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_memory("codey", {"kind": "profile", "body": "Identity."})
    store.create_memory("codey", {"kind": "log", "body": "Did the weekly review."})
    store.create_memory("codey", {"kind": "episode", "body": "Tuesday chat."})
    store.create_memory("codey", {"kind": "note", "body": "Scratch."})

    pack = store.list_memories("codey", tier="pack")
    assert {row["kind"] for row in pack} == {"profile", "log"}
    local = store.list_memories("codey", tier="local")
    assert {row["kind"] for row in local} == {"episode", "note"}
    logs = store.list_memories("codey", kind="log")
    assert [row["kind"] for row in logs] == ["log"]
    logs_in_pack = store.list_memories("codey", kind="log", tier="pack")
    assert [row["kind"] for row in logs_in_pack] == ["log"]
    crossed = store.list_memories("codey", kind="episode", tier="pack")
    assert crossed == []
    local_notes = store.list_memories("codey", kind="log,note", tier="local")
    assert [row["kind"] for row in local_notes] == ["note"]


def test_pack_round_trip_ignores_episode_note_and_scrubs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_memory(
        "source",
        {
            "kind": "profile",
            "title": "Motto",
            "body": f"Keep the motto. Contact {FAKE_EMAIL}.",
        },
    )
    store.create_memory(
        "source",
        {
            "kind": "log",
            "body": f"Shipped the review. Notes at {FAKE_PRIVATE_LINK}",
        },
    )
    store.create_memory("source", {"kind": "episode", "body": "Private Tuesday chat."})
    store.create_memory("source", {"kind": "note", "body": "Do not pack this."})

    fragment = store.export_pack_fragment("source")
    assert fragment["object"] == "agent_memory_pack"
    kinds = {row["kind"] for row in fragment["memories"]}
    assert kinds == {"profile", "log"}
    blob = " ".join(row["body"] for row in fragment["memories"])
    assert FAKE_EMAIL not in blob
    assert FAKE_PRIVATE_LINK not in blob
    assert "Keep the motto." in blob
    assert "Tuesday chat" not in blob
    assert "Do not pack this." not in blob

    dirty = {
        "object": "agent_memory_pack",
        "memories": [
            *fragment["memories"],
            {"kind": "episode", "body": "Should be ignored on import."},
            {"kind": "note", "body": "Also ignored."},
            {"kind": "profile", "body": f"Use {FAKE_OPENAI} never."},
        ],
    }
    imported = store.import_pack_fragment("target", dirty)
    assert all(row["agent_id"] == "target" for row in imported)
    assert all(row["kind"] in store.PACK_KINDS for row in imported)
    target_bodies = [row["body"] for row in store.list_memories("target")]
    joined = " ".join(target_bodies)
    assert FAKE_OPENAI not in joined
    assert "Should be ignored on import." not in joined
    assert "Also ignored." not in joined
    assert any("Keep the motto." in body for body in target_bodies)
    assert any("[REDACTED]" in body for body in target_bodies)


def test_replace_pack_fragment_uses_disk_when_cache_is_stale(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_memory("codey", {"kind": "profile", "title": "Old", "body": "packed"})
    store.create_memory("codey", {"kind": "episode", "title": "Tuesday", "body": "stay"})
    path = store.memories_path()
    store._cache = {"schema": store.SCHEMA, "agents": {}}
    store._cache_stamp = (path.stat().st_mtime_ns, path.stat().st_size)
    replaced = store.replace_pack_fragment(
        "codey",
        {"memories": [{"kind": "log", "title": "New", "body": "only pack row"}]},
    )
    assert [row["title"] for row in replaced] == ["New"]
    assert {(row["kind"], row["title"]) for row in store.list_memories("codey")} == {
        ("log", "New"),
        ("episode", "Tuesday"),
    }


def test_replace_pack_fragment_rejects_before_deleting(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_memory("codey", {"kind": "profile", "title": "Old", "body": "packed"})
    store.create_memory("codey", {"kind": "note", "title": "Local", "body": "stay"})
    with pytest.raises(ValueError, match="body"):
        store.replace_pack_fragment(
            "codey",
            {"memories": [{"kind": "profile", "title": "Huge", "body": "y" * (store.MAX_BODY + 1)}]},
        )
    assert {(row["kind"], row["title"]) for row in store.list_memories("codey")} == {
        ("profile", "Old"),
        ("note", "Local"),
    }


def test_import_skips_rows_without_a_pack_kind(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    imported = store.import_pack_fragment(
        "target",
        {
            "memories": [
                {"body": "no kind, do not pack"},
                {"kind": "episode", "body": "local only"},
                {"kind": "profile", "body": "keep this"},
            ]
        },
    )
    assert [row["body"] for row in imported] == ["keep this"]
    assert [row["body"] for row in store.list_memories("target")] == ["keep this"]


def test_create_rejects_private_key_and_access_key_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="credential"):
        store.create_memory("codey", {"kind": "log", "body": FAKE_PEM})
    with pytest.raises(ValueError, match="credential"):
        store.create_memory("codey", {"kind": "log", "body": f"id {FAKE_AWS}"})
    assert store.list_memories("codey") == []


def test_stale_cache_does_not_clobber_disk(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_memory("codey", {"kind": "note", "body": "kept"})
    path = store.memories_path()
    store._cache = {"schema": store.SCHEMA, "agents": {}}
    store._cache_stamp = (path.stat().st_mtime_ns, path.stat().st_size)
    store.create_memory("codey", {"kind": "note", "body": "added"})
    bodies = {row["body"] for row in store.list_memories("codey")}
    assert bodies == {"kept", "added"}


def test_read_does_not_pin_bytes_under_a_newer_stamp(tmp_path, monkeypatch):
    """A write that lands during load must not stick the old bytes in cache."""
    _isolate(tmp_path, monkeypatch)
    store.create_memory("codey", {"kind": "note", "body": "first"})
    path = store.memories_path()
    real_load = store._load_store

    def load_then_replace() -> dict:
        loaded = real_load()
        path.write_text(
            path.read_text(encoding="utf-8").replace("first", "second"),
            encoding="utf-8",
        )
        return loaded

    monkeypatch.setattr(store, "_load_store", load_then_replace)
    store.reset_memories_cache()
    assert [row["body"] for row in store.list_memories("codey")] == ["first"]
    monkeypatch.setattr(store, "_load_store", real_load)
    assert [row["body"] for row in store.list_memories("codey")] == ["second"]


def test_corrupt_store_is_not_replaced(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    path = store.memories_path()
    path.write_text("{", encoding="utf-8")
    store.reset_memories_cache()
    with pytest.raises(OSError, match="Could not read"):
        store.list_memories("codey")
    with pytest.raises(OSError, match="Could not read"):
        store.create_memory("codey", {"kind": "note", "body": "nope"})
    assert path.read_text(encoding="utf-8") == "{"


def test_concurrent_creates_keep_every_row(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def add(index: int) -> None:
        store.create_memory("codey", {"kind": "note", "body": f"row-{index}"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(8)))
    bodies = {row["body"] for row in store.list_memories("codey")}
    assert bodies == {f"row-{index}" for index in range(8)}
