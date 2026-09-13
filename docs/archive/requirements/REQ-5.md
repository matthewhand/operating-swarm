# REQ-5

Intent: make live Open Swarm UI look like OMB/Grok Bot dark chrome (not purple/pink/teal operator skin). First page more impressive: larger cards for the four quick actions. Carry over hide agent from the sidepane. Later operator pages (Blueprints, Teams, Sessions, Settings, Chat) share that chrome.

Success:
1. Colour theme matches OMB: near-black chrome, muted greys, small accents, not rainbow stats/buttons.
2. Home/Dashboard four options as large cards: Launch Team, Browse Blueprints, Manage Teams, Settings.
3. Sidepane exists; right-click Hide from sidebar on an agent; item leaves the main list; expandable Hidden; Unhide; persist across reload. hide-all must not be required.
4. Later pages share the same chrome.

Constraints: Live http://198.51.100.30:8001/. Do not change OMB (:8802). No LiteLLM catalog. Adding a sidepane is in scope if hide needs it; do not clone OMB wholesale. REQ-4 custom CoS+engineer+skeptic teams is a separate track. No Neon/oracle. No Qwen-while-Comfy POST. No Chatty implement. No Dual-entry rewrite.

Landed on origin/main as the squash-merge of https://github.com/matthewhand/open-swarm/pull/307, SHA 91dabd645d289ee539aa00bbe0721e1dc916b116 (`91dabd64`).

Guest/anonymous preview (`SWARM_ALLOW_ANONYMOUS=1`, local uncommitted `src/swarm/consumers.py`, `src/swarm/middleware.py`, `src/swarm/settings.py`) is NOT part of this REQ and is NOT in `91dabd64`.

Owner: open-swarm engineer.
