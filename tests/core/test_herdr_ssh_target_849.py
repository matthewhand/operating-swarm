"""#849 — flexible SSH target parsing + per-instance Herdr dispatch."""

from __future__ import annotations

import pytest

from swarm.herdr.ssh import SSHNotConfiguredError, parse_ssh_target


def test_plain_host_gets_default_port_and_current_user():
    target = parse_ssh_target("docs-host.lan")
    assert target.host == "docs-host.lan"
    assert target.port == 22
    assert target.user  # current user fallback


def test_user_at_host_and_host_port():
    t1 = parse_ssh_target("operator@192.0.2.10")
    assert (t1.user, t1.host, t1.port) == ("operator", "192.0.2.10", 22)
    t2 = parse_ssh_target("operator@docs-host:2222")
    assert (t2.user, t2.host, t2.port) == ("operator", "docs-host", 2222)


def test_ssh_uri_forms():
    t1 = parse_ssh_target("ssh://192.0.2.10:22")
    assert (t1.user, t1.host, t1.port) == ("", "", 22) if False else (t1.host, t1.port) == ("192.0.2.10", 22)
    t2 = parse_ssh_target("ssh://operator@docs-host:2222")
    assert (t2.user, t2.host, t2.port) == ("operator", "docs-host", 2222)


def test_default_user_fallback_over_getpass():
    target = parse_ssh_target("192.0.2.20", default_user="deploy")
    assert target.user == "deploy"


def test_empty_and_bad_inputs_raise_clear_errors():
    with pytest.raises(SSHNotConfiguredError):
        parse_ssh_target("")
    with pytest.raises(SSHNotConfiguredError):
        parse_ssh_target("host:notaport")
    with pytest.raises(SSHNotConfiguredError):
        parse_ssh_target("https://example.com")


def test_target_destination_round_trips():
    target = parse_ssh_target("ssh://operator@docs-host:2222")
    assert target.destination() == "operator@docs-host"
    assert target.public_label() == "operator@docs-host:2222"
