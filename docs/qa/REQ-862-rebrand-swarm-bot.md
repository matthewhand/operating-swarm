# REQ-862 — Project Rebrand: open-swarm → operating-swarm (Operating Swarm / OS) (#252)

> Rebrand the project from **open-swarm** to **Operating Swarm** (shorthand: **OS**), establishing its unified architectural positioning as a provider-agnostic agent operating layer, standalone execution harness, and peer-to-peer federated system.

**Issue:** [#252](https://github.com/matthewhand/open-swarm-private/issues/252)

---

## 1. Executive Summary & Brand Positioning

The project is rebranding from **open-swarm** to **Operating Swarm** (shorthand: **OS**), superseding the earlier "Swarm Bot" proposal.

### 1.1 The Core Triad
Operating Swarm is simultaneously:
1. **A complete agentic harness** in its own right (native OS execution mode).
2. **A compatibility and orchestration layer** for existing external agentic harnesses (e.g. Hermes).
3. **A peer-to-peer system** that can connect to and compose recursively with other Operating Swarm instances.

> [!IMPORTANT]
> **Do not describe OS as only a UI, wrapper, gateway, adapter, or supervisor.**  
> OS provides its own native agentic execution while orchestrating external harnesses and peer nodes under a common abstraction.

### 1.2 Distilled Intent & Official Brand Tagline

> **"Treat external harnesses and peer instances as one common abstraction."**

This tagline captures the purest, best-distilled intent of the project: eliminating artificial architectural divides between native execution runtimes, third-party frameworks, and federated peer instances.

**Header Placement Requirement:**  
This tagline and the architecture hero diagram (`assets/brand/operating-swarm-hero-diagram.svg`) must be featured directly beneath the project name in the top `README.md` hero header:
```markdown
# Operating Swarm (OS)
> Treat external harnesses and peer instances as one common abstraction.

<p align="center">
  <img src="assets/brand/operating-swarm-hero-diagram.svg" alt="Operating Swarm Architecture Overview" width="750" />
</p>
```

The hero diagram visualizes the central OS hub radiating out across 5 core connection paths:
- **API** (OpenAI · MCP · A2A)
- **Remote** (Other OS · hosted agents)
- **Embedded** (SDKs · plugins · adapters)
- **WebUI** (Browser · local UI via WebSocket)
- **CLI** (Hermes · TruForge · OpenCode)


### 1.3 Required Positioning Statement
> *"Operating Swarm is a provider-agnostic agent operating layer and harness. It provides its own agentic interface while also connecting to existing harnesses and other Operating Swarm instances. Sessions can persist while switching between providers, harnesses, and remote OS nodes."*

### 1.4 Guardrails (What to Avoid)
Ensure documentation and user-facing copy avoid implying that:
- OS is only a frontend for Grok.
- OS requires Grok or any specific provider.
- OS replaces existing agentic harnesses.
- External harnesses are subordinate to OS.
- Another OS instance is a fundamentally different integration type from a harness.
- The WebUI, CLI, or API is the entire product.

---

## 2. The 7-Layer Architectural Model

The project architecture is structured into seven distinct layers:

```
+-------------------------------------------------------------------------------+
|                               INTERFACES                                      |
|   • OS WebUI: Primary Grok-style interface (chat, teams, visual orchestration) |
|   • OS CLI:   Command-line interface (TUI features planned)                   |
|   • OS API:   OpenAI-compatible server endpoint (OS endpoint / OS server)     |
+-------------------------------------------------------------------------------+
                                       |
+-------------------------------------------------------------------------------+
|                             OS CORE / RUNTIME                                 |
|   • Provider-agnostic & harness-agnostic session routing and state store      |
|   • Persistent Session abstraction (survives provider/harness swaps)         |
+-------------------------------------------------------------------------------+
             |                                 |                       |
             v                                 v                       v
+------------------------+  +---------------------------+  +--------------------+
|       OS HARNESS       |  |     EXTERNAL HARNESSES    |  |      OS PEERS      |
| Native agentic runtime |  | Adapters for Hermes, etc. |  | Federated OS nodes |
+------------------------+  +---------------------------+  +--------------------+
```

1. **OS Core / OS Runtime**: The provider-agnostic and harness-agnostic session, routing, and orchestration layer.
2. **OS Harness**: Operating Swarm's native agentic execution mode.
3. **OS WebUI**: The primary Grok-style web interface.
4. **OS CLI**: The command-line interface (TUI features pending).
5. **OS API**: The OpenAI-compatible server endpoint where model slugs map directly to agent or harness names (referred to in documentation as the **"OS endpoint"** or **"OS server"** to avoid confusion with an operating system kernel API).
6. **External Harness Integrations**: Adapters for Hermes and other existing agentic frameworks.
7. **OS Peer Integrations**: Connections to other Operating Swarm instances (enabling recursive composition and peer federation).

---

## 3. Name Evaluation & Selection Rationale

| Candidate | Status | Evaluation Finding |
| :--- | :--- | :--- |
| `open-swarm` | **Current (Deprecated)** | Direct collision with an existing, more popular, and unrelated open-source project on GitHub. |
| `Swarm Bot` | **Rejected** | Exact-name collisions with at least 4 unrelated GitHub projects (`SwarmBotMC`, `ethersphere/swarm-bot`, `ERC-BPGC/swarm_bots`, `firstandthird/swarm-bot`). |
| `GrokSwarm`, `GrokHive` | **Rejected** | xAI common-law trademark risk. Combining visual similarity to Grok with "Grok" in the name creates unacceptable confusion risk. Decision: keep Grok-style UI, drop "Grok" from product name. |
| Mythology & MTG terms (~50 evaluated: *Janus*, *Argus*, *Pantheon*, *Olympus*, *Themis*, *Elysium*, *Sovereign*, *Nomos*, *CommandZone*) | **Rejected** | All yielded exact-name collisions on GitHub. Clean alternatives (*Demiurge*, *SwarmCortex*, *Regent-UI*) lacked synergy with our visual branding. |
| **Operating Swarm (OS)** | **Selected** | **Zero GitHub collisions.** Preserves existing "OS" logo and monogram; functions as an intentional double entendre with "Operating System" directing multi-agent processes. |

---

## 4. Repository & Package Registry Strategy

### 4.1 GitHub Lifecycle
1. **Immediate Reservation**: Create the `operating-swarm` private repository on GitHub to protect the namespace.
2. **Staging Phase**: Maintain active daily development and stabilization in `open-swarm-private`.
3. **Initial Live Commit**: Upon validating a stable, functional milestone, publish the curated initial commit to `operating-swarm` to launch the live project.

### 4.2 PyPI & npm Namespace Protection
- **Unclaimed Status**: Verified that `operating-swarm` is unclaimed across GitHub, PyPI, and npm.
- **Reservations**:
  - **PyPI**: Claim `operating-swarm` (plus `operating-swarm-cli`, `operating-swarm-server`).
  - **npm**: Claim `operating-swarm-webui` (plus `@operating-swarm` scope).
- **Legacy PyPI Deprecation (`open-swarm`)**:
  - Maintainer owns the legacy `open-swarm` package on PyPI.
  - Publish a final deprecation stub release on `open-swarm` displaying an installation warning and pointing users to `operating-swarm` (`install_requires=["operating-swarm"]`).
  - Cross-link old and new listings to preserve download history and credibility.

### 4.3 Documentation Rules
- **First-Mention Disambiguation**: On first mention in any guide, explicitly spell out:  
  > *"Operating Swarm (OS) exposes three interfaces: the OS WebUI, OS CLI, and OS API (OpenAI-compatible)."*
- **Visual Continuity**: Preserve existing bee and hive motifs (honeycomb geometric patterns, hexagon marks, amber accents). Keep UI branding independent from provider branding.

---

## 5. Touchpoint Inventory & Migration Tasks

| Category | Target / Scope | Planned Action |
| :--- | :--- | :--- |
| **Frontend UI** | `webui/frontend/index.html`<br>`SettingsSheet.tsx`<br>`package.json` | Update `<title>` to `Operating Swarm`<br>Brand headers to `Operating Swarm`<br>Rename package to `operating-swarm-webui`<br>Preserve `.os-` CSS class prefix |
| **Backend & Django** | `templates/base.html`<br>`swarm_cli.py`<br>`swarm_api.py` | Title to `Operating Swarm`<br>CLI banner to `Operating Swarm CLI (OS CLI)`<br>API banner to `Operating Swarm API (OS Server)` |
| **Packaging** | `pyproject.toml` | Update name to `operating-swarm`<br>Script entrypoints: `operating-swarm`, `os-cli`, `os-api` (with compatibility shims) |
| **Documentation** | `README.md`<br>`USERGUIDE.md`<br>`DEVELOPMENT.md` | Overhaul positioning to Operating Swarm (OS)<br>Document 7-layer architecture and session mobility<br>Scrub standalone "Grok" and "Swarm Bot" naming |

---

## 6. Acceptance Criteria

- [ ] Issue [#252](https://github.com/matthewhand/open-swarm-private/issues/252) updated with the Operating Swarm (OS) title, 7-layer model, and registry strategy.
- [ ] A new reader can understand that Operating Swarm is simultaneously a standalone harness, an integration layer, and a peer that can compose with other Operating Swarm instances.
- [ ] Definitions provided for `node`, `instance`, `harness`, `provider`, `session`, `adapter`, and `peer`.
- [ ] Common abstraction of "harness" documented for both external harnesses and other OS instances.
- [ ] Concrete session migration example provided (moving between provider, external harness, native OS harness, and peer OS node).
- [ ] PyPI deprecation plan for `open-swarm` and reservation plan for `operating-swarm` on PyPI and npm defined.
- [ ] Brand touchpoints in WebUI, CLI, templates, and `pyproject.toml` inventoried and aligned to OS naming.
- [ ] The official brand tagline *"Treat external harnesses and peer instances as one common abstraction."* is featured in the top `README.md` hero header and documentation overview.
- [ ] The hero architecture diagram `assets/brand/operating-swarm-hero-diagram.svg` is embedded in the top hero section of `README.md`.


