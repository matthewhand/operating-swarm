"""Bootstrap provider: deterministic onboarding for fresh installs (#893).

When the Admin agent's ``provider`` field is set to ``"bootstrap"`` and no LLM
inference has been configured yet, the consumer calls :func:`respond_with_bootstrap`
instead of dispatching to an LLM backend.  Responses are hardcoded, zero-dependency,
and guide the user to:

1. Configure an LLM inference provider (OpenAI, Anthropic, Ollama, Groq, etc.).
2. Return to this chat and toggle the Admin agent to use that provider.
3. At that point, the Admin bot becomes fully LLM-powered and can build blueprints.

The Bootstrap provider is **never** offered in the general composer picker dropdown.
It is only selectable from the agent editor settings for the Admin seat.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #

BOOTSTRAP_PROVIDER_ID = "bootstrap"
ADMIN_AGENT_ID = "starter-admin"
ADMIN_AGENT_ALIASES: frozenset[str] = frozenset(
    {ADMIN_AGENT_ID, "admin", "starter-support", "support"}
)

# Chips shown on every bootstrap reply.
BOOTSTRAP_KICKSTART_CHIPS: tuple[str, ...] = (
    "Configure API Provider",
    "What is Open Swarm?",
    "Local Models (Ollama)",
    "Upgrade to LLM",
)

# --------------------------------------------------------------------------- #
# Intent detection
# --------------------------------------------------------------------------- #

_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "greeting",
        [r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bstart\b", r"\bbegin\b", r"\bwelcome\b"],
    ),
    (
        "configure_provider",
        [
            r"\bconfigure\b", r"\bsetup\b", r"\bset up\b", r"\bapi\s*key\b",
            r"\bprovider\b", r"\btok(?:en)?\b", r"\bcredential\b",
            r"\bopenai\b", r"\banthropic\b", r"\bgroq\b", r"\bgemini\b",
            r"\blitellm\b", r"\bapi\s*gateway\b",
        ],
    ),
    (
        "local_models",
        [r"\bollama\b", r"\bvllm\b", r"\blocal\s*model\b", r"\boffline\b", r"\bself.host\b"],
    ),
    (
        "upgrade_llm",
        [r"\bupgrade\b", r"\bconnect\b", r"\benable\b", r"\bactivate\b", r"\bswitch\b"],
    ),
    (
        "what_is_swarm",
        [r"\bwhat\s+is\b", r"\bopen\s*swarm\b", r"\bexplain\b", r"\bhelp\b", r"\binfo\b"],
    ),
    (
        "blueprint",
        [r"\bblueprint\b", r"\bworkflow\b", r"\bteam\b", r"\bagent\b", r"\bcreate\b"],
    ),
]


def _detect_intent(text: str) -> str:
    lower = text.strip().lower()
    for intent, patterns in _INTENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, lower):
                return intent
    return "unknown"


# --------------------------------------------------------------------------- #
# Canned responses (intent → reply)
# --------------------------------------------------------------------------- #

_REPLIES: dict[str, str] = {
    "greeting": (
        "👋 Hi! I'm **Admin** — your Open Swarm onboarding assistant.\n\n"
        "Right now I'm running in **Bootstrap mode** because no LLM inference provider "
        "has been configured yet. My responses are pre-written, but I can still guide you "
        "through the setup.\n\n"
        "**To unlock full AI capabilities:**\n"
        "1. Configure an inference provider (OpenAI, Anthropic, Ollama, Groq, etc.).\n"
        "2. Come back here and open my agent settings → change **Provider** from "
        "`bootstrap` to your new provider.\n"
        "3. That's it — I'll be fully LLM-powered and ready to build custom blueprints "
        "and multi-agent teams with you.\n\n"
        "What would you like to do first?"
    ),
    "configure_provider": (
        "🔧 **Configuring an Inference Provider**\n\n"
        "Open Swarm supports several LLM inference backends:\n\n"
        "| Provider | Requires | Notes |\n"
        "|---|---|---|\n"
        "| **OpenAI** | `OPENAI_API_KEY` | GPT-4o, o1, etc. |\n"
        "| **Anthropic** | `ANTHROPIC_API_KEY` | Claude 3.5 etc. |\n"
        "| **Groq** | `GROQ_API_KEY` | Fast Llama/Mixtral inference |\n"
        "| **Gemini** | `GEMINI_API_KEY` | Google Gemini models |\n"
        "| **Ollama** | Local install | No API key needed |\n"
        "| **LiteLLM** | `LITELLM_BASE_URL` | Any model via proxy |\n\n"
        "**Steps:**\n"
        "1. Add your API key to the `.env` file in the Open Swarm root, e.g.:\n"
        "   ```\n"
        "   OPENAI_API_KEY=sk-...\n"
        "   ```\n"
        "2. Restart the Open Swarm server.\n"
        "3. Open **Settings → Providers** to verify the key is recognised.\n"
        "4. In my agent settings, change **Provider** from `bootstrap` to `openai` "
        "(or whichever you configured).\n\n"
        "Need step-by-step help for a specific provider? Just ask!"
    ),
    "local_models": (
        "🖥️ **Running Local Models with Ollama**\n\n"
        "Ollama lets you run open-weight models entirely offline — no API key needed.\n\n"
        "**Quick start:**\n"
        "```bash\n"
        "# 1. Install Ollama\n"
        "curl -fsSL https://ollama.com/install.sh | sh\n\n"
        "# 2. Pull a model (e.g. Llama 3.1 8B)\n"
        "ollama pull llama3.1\n\n"
        "# 3. Start the server (runs at http://localhost:11434 by default)\n"
        "ollama serve\n"
        "```\n\n"
        "**Then in Open Swarm:**\n"
        "1. Open **Settings → Providers** and add an Ollama provider:\n"
        "   - Base URL: `http://localhost:11434`\n"
        "   - No API key required.\n"
        "2. In my agent settings, change **Provider** to `ollama`.\n\n"
        "I'll be fully operational once you restart and switch my provider!"
    ),
    "upgrade_llm": (
        "⚡ **Upgrading from Bootstrap to LLM mode**\n\n"
        "Once you've configured an inference provider, upgrading me is easy:\n\n"
        "1. Open **Settings → Agents** (or click my name in the rail).\n"
        "2. Find the **Provider** dropdown — it currently shows `bootstrap`.\n"
        "3. Select your configured provider (e.g. `openai`, `ollama`, `anthropic`).\n"
        "4. Click **Save**.\n\n"
        "After saving, my responses will be fully AI-generated. I'll be able to:\n"
        "- Create custom blueprints and agent teams from natural language.\n"
        "- Help you wire CLI ↔ API ↔ Remote agents in one pane.\n"
        "- Build BA → Engineer → Tester workflows and more.\n\n"
        "Haven't configured a provider yet? Use the **Configure API Provider** option below!"
    ),
    "what_is_swarm": (
        "🌐 **What is Open Swarm?**\n\n"
        "Open Swarm is an open-source multi-agent orchestration platform. It lets you:\n\n"
        "- **Chat with AI agents** via a web UI, CLI, or remote connections.\n"
        "- **Build teams** of specialised agents (e.g. BA, Engineer, Tester) that "
        "hand off work between each other.\n"
        "- **Wire up providers**: OpenAI, Anthropic, Ollama, Groq, LiteLLM, and more.\n"
        "- **Connect remotes**: Hermes, Herdr, and other external agent services.\n"
        "- **Author blueprints**: Python classes (ApiKindBase / CliKindBase) that define "
        "agent logic, tools, and skills.\n\n"
        "Right now you're in **Bootstrap mode** — a zero-config starting point. "
        "Configure a provider to unlock the full AI experience!"
    ),
    "blueprint": (
        "📐 **Blueprints & Agent Teams**\n\n"
        "Blueprints are the Python classes that define how an agent behaves. "
        "You can create them from natural language — no Python required.\n\n"
        "**However**, I'm currently in **Bootstrap mode** (no LLM configured), so I "
        "can't generate blueprints yet.\n\n"
        "**To create your first blueprint:**\n"
        "1. Configure an LLM inference provider.\n"
        "2. Upgrade me from `bootstrap` to that provider in my agent settings.\n"
        "3. Come back and describe the team you want — I'll build it!\n\n"
        "Example request you can give me once upgraded:\n"
        "> *\"Create a BA → Engineer → Tester workflow that reviews pull requests\"*"
    ),
    "unknown": (
        "🤖 I'm **Admin** in Bootstrap mode — my responses are pre-written until you "
        "configure an LLM inference provider.\n\n"
        "Here's what I can help you with right now:\n"
        "- **Configure** an API provider (OpenAI, Anthropic, Groq, Ollama…)\n"
        "- **Explain** what Open Swarm is and how it works\n"
        "- **Guide** you to upgrade me to full AI mode\n\n"
        "Once you've configured a provider and updated my settings, I'll be fully "
        "LLM-powered and ready to build anything with you!"
    ),
}

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def is_bootstrap_active(blueprint_id: str | None, params: dict[str, Any] | None) -> bool:
    """Return True when this turn should be handled by the Bootstrap provider.

    Conditions:
    - The agent is the Admin/Support seat (id in ADMIN_AGENT_ALIASES), AND
    - ``params`` signals provider == "bootstrap", OR the agent id is ``starter-admin``
      and no ``model`` override is present in params.
    """
    bid = str(blueprint_id or "").strip().lower()
    if bid not in ADMIN_AGENT_ALIASES:
        return False
    if params is None:
        # No params at all → treat as bootstrap for the admin seat
        return bid == ADMIN_AGENT_ID
    provider = str(params.get("provider") or "").strip().lower()
    if provider == BOOTSTRAP_PROVIDER_ID:
        return True
    # starter-admin with no explicit provider falls back to bootstrap
    if bid == ADMIN_AGENT_ID and not provider and not params.get("model"):
        return True
    return False


def bootstrap_reply(user_text: str) -> dict[str, Any]:
    """Return a bootstrap response dict for *user_text*.

    Shape mirrors a typical chat response so callers can emit it without
    special-casing the render path:

    .. code-block:: python

        {
            "text": "<markdown reply>",
            "chips": ["Configure API Provider", ...],
            "provider": "bootstrap",
        }
    """
    intent = _detect_intent(user_text)
    text = _REPLIES.get(intent, _REPLIES["unknown"])
    # #894: the configure intent attaches the interactive in-chat setup card
    # (fenced JSON the bubble parses into ProviderSetupCard). The prose still
    # carries the provider table; the card replaces the manual .env steps.
    if intent == "configure_provider":
        text = (
            "🔧 **Let's configure your inference provider.** Pick a preset, "
            "paste your key, test the connection, and save — no .env editing "
            "or restart required.\n\n"
            "```swarm-provider-setup\n"
            '{"type": "provider_setup", "default_provider": "openai"}\n'
            "```\n\n"
            "Local options (Ollama, LM Studio, vLLM, OpenWebUI, LocalAI) need "
            "no API key at all."
        )
    return {
        "text": text,
        "chips": list(BOOTSTRAP_KICKSTART_CHIPS),
        "provider": BOOTSTRAP_PROVIDER_ID,
    }
