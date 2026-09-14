"""Tests for named fleet seats resolution (Issue #178).

Proves:
1. Fleet proxy seats (e.g. litellm-pi, myproj-pi) remap to cli_agent with cli=pi.
2. Direct catalog names (pi, grok) and *_agent forms (pi_agent, grok_agent) work.
3. Unknown names with no catalog stem (foo-bar) return None / as-is.
4. api_agent continues to resolve to chatbot.
5. get_blueprint_instance('litellm-pi') yields a cli_agent instance with cli='pi'.
"""

import pytest
from swarm.core.agent_kind import resolve_chat_blueprint_id
from swarm.core.cli_catalog import cli_from_rail_id
from swarm.views.utils import get_blueprint_instance


def test_cli_from_rail_id_fleet_seats():
    assert cli_from_rail_id("litellm-pi") == "pi"
    assert cli_from_rail_id("myproj-grok") == "grok"
    assert cli_from_rail_id("fleet_pi") == "pi"
    assert cli_from_rail_id("pi_agent") == "pi"
    assert cli_from_rail_id("pi") == "pi"
    assert cli_from_rail_id("grok_agent") == "grok"
    assert cli_from_rail_id("grok") == "grok"


def test_cli_from_rail_id_unknown_and_standard_seats():
    assert cli_from_rail_id("foo-bar") is None
    assert cli_from_rail_id("software_dev") is None
    assert cli_from_rail_id("api_agent") is None
    assert cli_from_rail_id("cli_agent") is None
    assert cli_from_rail_id("") is None
    assert cli_from_rail_id(None) is None


def test_resolve_chat_blueprint_id_fleet_seats():
    assert resolve_chat_blueprint_id("litellm-pi") == "cli_agent"
    assert resolve_chat_blueprint_id("myproj-grok") == "cli_agent"
    assert resolve_chat_blueprint_id("pi_agent") == "cli_agent"
    assert resolve_chat_blueprint_id("pi") == "cli_agent"
    assert resolve_chat_blueprint_id("api_agent") == "chatbot"
    assert resolve_chat_blueprint_id("software_dev") == "software_dev"
    assert resolve_chat_blueprint_id("foo-bar") == "foo-bar"


@pytest.mark.asyncio
async def test_get_blueprint_instance_fleet_seat():
    instance = await get_blueprint_instance("litellm-pi")
    assert instance is not None
    assert instance.blueprint_id == "cli_agent"
    params = getattr(instance, "_params", getattr(instance, "params", {}))
    assert params.get("cli") == "pi"

