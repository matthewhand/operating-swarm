# Announce copy — Grok-agnostic UI + multi-harness bridge (REQ-136)

Issue SoT: [REQ-136 #529](https://github.com/matthewhand/open-swarm/issues/529).

**This page is the announce-ready spiel.** README embeds the short pitch and
the hero clip. CoS / Matthew owns **when** to post. Do not write to
production announce channels from this tree.

**Honesty:** the checked-in hero is a **captioned storyboard** (15–20s). Live
WebUI recapture is a later pass on a clean demo box — not CI, not Neon, not
a Fast-Forward preview host. See [Recording checklist](#recording-checklist).

Related: showoff names [REQ-135 #526](https://github.com/matthewhand/open-swarm/issues/526)
([SHOWOFF_DEMO_AGENTS.md](./SHOWOFF_DEMO_AGENTS.md)); near-release GIF kit
[#456](https://github.com/matthewhand/open-swarm/issues/456)
([docs/assets/readme/](./assets/readme/README.md)); openai-agents graphs
[REQ-156 #564](https://github.com/matthewhand/open-swarm/issues/564).

No secrets. No private hostnames. No LAN dumps.

---

## Spiel (SoT)

Use this wording in README, announce posts, and GIF captions.

**Problem.** AI enthusiasts juggle many frameworks; some combine CLIs and
APIs, but still do not talk to **remote harnesses** (Hermes, OpenMousBot as
remote, and the like).

**Operating Swarm.** A **Grok-agnostic** Grok-Bot-like UI **and** a **bridge** —
task one place, coordinate across CLI, API, remotes, and local blueprints.

### Differentiator (lead with this)

1. **Bridging types** — one pane / one team spanning **CLI + API + remote**
   (Hermes, OpenMousBot, Antigravity / `agy`, OpenCode, and the rest).
   Frameworks that only mix CLIs and APIs **locally** (for example
   OpenMousBot as a local combiner) still do not integrate remotes like
   **Hermes**.
2. **Grok-agnostic chrome** — Grok Bot UI inspired (simplicity, ⌘K search,
   quiet chrome, favourites, native sessions) **without** locking the
   product to Grok / xAI.
3. **Customised programmatic agents via natural language** — Support (or a
   named onboarder) can build a blueprint / handoff workflow without the
   user writing Python ([#567](https://github.com/matthewhand/open-swarm/issues/567));
   optional peek at code. Workflow-gen that uses itself.

### Fold-in addenda (Matthew 2026-09-04)

- **Single pane of glass** to track and task **all types** of agentic
  solutions (CLI, API, remotes, blueprints / teams).
- **Uses your existing setups** — you do not replace Herdr / Hermes /
  OpenMousBot; you point Operating Swarm at them.
- **Mobile / on the road:** a desk terminal is fine; on a phone you want
  the **remote in the WebUI**, with **auto-suggestions**
  ([#441](https://github.com/matthewhand/open-swarm/issues/441)) so you can
  **task without typing**. Suggestions apply to **any** CLI, API, or remote
  — not Herdr-only.
- **Agents for all parts of the workflow** — gating, suggestions, Chief of
  Staff coordination / comms. Legacy UIs constrain users with forms and
  menus; Operating Swarm aims **natural language first** (Settings still exists
  where needed). Embrace agents as much as possible.
- **Native sessions, not a cage.** When Operating Swarm drives a CLI or remote,
  the session is via **native tooling**. Users can switch freely:
  Operating Swarm WebUI (and later TUI [#481](https://github.com/matthewhand/open-swarm/issues/481)),
  or the tool directly (`grok`, `agy`, Hermes UI, …) for deeper config or
  troubleshooting. Pick up that native session when they return
  ([#468](https://github.com/matthewhand/open-swarm/issues/468) /
  [#469](https://github.com/matthewhand/open-swarm/issues/469)).
- **Cross-tool context move** (for example Grok → Antigravity) is
  **roadmap**, not a launch claim
  ([#531](https://github.com/matthewhand/open-swarm/issues/531)). Announce
  honestly: native escape hatch is real today; ferry-between-CLIs is
  pending.
- Quick dropdown switch when quota dies is an announce beat; **context
  carry into the new CLI/API** is that same pending #531 story.

### Short social / README blurb

> AI enthusiasts juggle many frameworks; some combine CLIs and APIs, but
> still don’t talk to **remote harnesses** (Hermes, OpenMousBot as remote,
> …). Operating Swarm is a **Grok-agnostic** Grok-Bot-like UI **and** a bridge —
> task one place, coordinate across CLI, API, remotes, and local blueprints.

---

## Hero clip

| Slot | Path | Role |
|---|---|---|
| **Announce hero** (this Issue) | [`docs/assets/readme/announce-bridge.gif`](./assets/readme/announce-bridge.gif) | 15–20s storyboard. Captions use the spiel. |
| Meta (duration / captions) | [`docs/assets/readme/announce-bridge.meta.json`](./assets/readme/announce-bridge.meta.json) | Path-contract lock for CI. |
| #456 kit (later) | `docs/assets/readme/{cli,api,remotes,combined}.gif` | Reserved names. Do not invent stills here. |

Regenerate the storyboard (no live host, no secrets):

```bash
uv run --with pillow python scripts/render_announce_gif.py
```

Historical terminal loop stays at [`docs/demo/cli-and-api.gif`](./demo/cli-and-api.gif)
(CLI+API only — not the remote-bridge story).

---

## Demo roster (must appear in the GIF)

Kind-clear names follow Mode A ([#526](https://github.com/matthewhand/open-swarm/issues/526)).
Blueprint personas are Mode B. Label **OpenMousBot**, never OMB.

Filming composition (one CoS team — not five disconnected chats):

| Display name | Kind | Source (placeholders only) |
|---|---|---|
| Chief of Staff | Blueprint / API coordinator | `blueprint:sdlc_handoff` |
| Hermes Remote | Remote | `placeholder:remote:hermes` |
| OpenMousBot Remote | Remote | `placeholder:remote:omb` |
| Antigravity CLI | CLI | `cli:agy` |
| OpenCode CLI | CLI | `cli:opencode` |
| BA → Engineer → Tester | Blueprint personas | openai-agents **handoff / use-as-tool** (`sdlc_handoff`) |

Existing seed rosters cover most of this without a new `demo-*` id:

- [`demo-bridge.json`](./examples/openai-agents-handoff-graphs/demo-bridge.json) — CoS + kind-clear mix
- [`demo-harness-kinds.json`](./examples/openai-agents-handoff-graphs/demo-harness-kinds.json) — Hermes / OpenMousBot / Antigravity
- [`demo-sdlc-pipeline.json`](./examples/openai-agents-handoff-graphs/demo-sdlc-pipeline.json) — BA → Engineer → Tester

**OpenCode CLI** is an announce-film extra (`cli:opencode`). It is not a
REQ-135 seed member; add it locally when recapturing. Do not commit
hostnames, tokens, or LAN URLs.

---

## Storyboard (15–20 seconds)

One sequence. Viewer must see **one** task on **one** CoS, then work
move across kinds. Captions are on-screen; no voiceover.

| t | Beat | On-screen caption (spiel) | Picture |
|---|---|---|---|
| 0–3s | Problem | Some tools mix CLIs and APIs. They still don’t talk to **remote harnesses**. | Split: “CLI + API only” vs empty remote seat |
| 3–6s | Solution | **Grok-agnostic** Grok-Bot-like UI **and** a multi-harness **bridge**. | Quiet chrome + Operating Swarm wordmark |
| 6–10s | One pane / one task | Task **one** place. Chief of Staff coordinates the team. | Composer: “Ship the release notes.” CoS accepts |
| 10–16s | Coordination | Hermes Remote · OpenMousBot Remote · Antigravity CLI · OpenCode CLI · BA → Engineer → Tester | Members light in sequence; not five chats |
| 16–20s | Existing setups + chips | Point Operating Swarm at what you already run. **Task without typing.** Native sessions, not a cage. | Suggestion chips on a remote row; native-escape note |

Skeptic lock: FAIL if the clip is a screenshot dump or five unrelated
threads. PASS only if one CoS task visibly fans out across CLI + remote +
blueprint.

---

## Recording checklist (live recapture)

Parked until Matthew says the UI wave is camera-ready. **Do not** film
production chats. **Do not** use Neon. **Do not** target a Fast-Forward
preview host from CI or from this doc.

1. Clean local preview (`http://localhost:8000` after `make frontend` +
   `docker compose up`). Empty remotes catalog until you place demo
   remotes.
2. Seed labeled Demo rosters only:
   `uv run python scripts/seed_demo_agents.py --dry-run` then
   `uv run python scripts/seed_demo_agents.py`.
3. Place **Hermes Remote** and **OpenMousBot Remote** against already-
   configured harnesses (or honest placeholders). Add **Antigravity CLI**
   (`agy`) and **OpenCode CLI** (`opencode`) from Settings → Suggested if
   those binaries are on PATH.
4. Open **Demo Bridge** (or a local announce team that includes the
   roster above). Select **Chief of Staff**.
5. Crop to the SPA rail + chat. No OS username, no home path, no LAN IP,
   no token, no cookie.
6. Type **one** task (or tap a suggestion chip). Hold until CoS hands
   work to at least one CLI, one remote, and the blueprint pipeline.
   Kind labels must be readable without a voiceover.
7. Optional 2-second beat: suggestion chips on a **remote** thread
   (any kind — not Herdr-only).
8. Export 15–20s (hard cap 30s), mute, 16:9. Replace
   `docs/assets/readme/announce-bridge.gif` (GIF or muted mp4 + GIF
   fallback). Update `announce-bridge.meta.json` (`live_capture: true`).
9. Re-run `uv run pytest tests/unit/test_req136_announce.py`.

#456 later drops `cli.gif` / `api.gif` / `remotes.gif` / `combined.gif`
into the **same** directory. Combined may reuse this hero.

---

## What this PR does **not** do

- Post the announce (Matthew / CoS timing).
- Claim a desktop installer ([ADR-003](./adr/003-desktop-packaging.md) /
  [#554](https://github.com/matthewhand/open-swarm/issues/554)).
- Claim cross-tool session ferry ([#531](https://github.com/matthewhand/open-swarm/issues/531)).
- Recapture the four #456 kit clips.
- Enable Neon or write a Fast-Forward preview host.
