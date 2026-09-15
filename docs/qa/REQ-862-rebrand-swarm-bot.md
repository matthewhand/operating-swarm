# REQ-862 — Project Rebrand to "Swarm Bot" (#252)

> Rebrand the project from **Open Swarm** to **Swarm Bot**, establishing its primary positioning:
> **"Swarm Bot: A single bot to control all your swarms (Hermes, TrueForge, etc.)"**

**Issue:** [#252](https://github.com/matthewhand/open-swarm-private/issues/252)

---

## 1. Executive Summary & Brand Positioning

The project is rebranding from **Open Swarm** to **Swarm Bot**.

### Key Value Proposition
- **Single Bot Control Plane**: Swarm Bot acts as the single orchestrator and unified interface to command, monitor, and coordinate all downstream swarm instances, remote agent hubs, and execution environments — including **Hermes**, **TrueForge**, **Herdr**, OpenMousBot, and local CLI agents.
- **Consistent Identity**: Transitioning user-facing text, page titles, CLI branding, and documentation from "Open Swarm" to "Swarm Bot", while preserving stability for internal module references (`swarm.*`).

---

## 2. Touchpoint Audit & Inventory

A codebase-wide analysis reveals:
- **`Open Swarm` (case-insensitive)**: ~420 occurrences
- **`open-swarm` (hyphenated)**: ~813 occurrences

### 2.1 Categorized Touchpoint Breakdown

| Category | File Scope | Key Touchpoints | Planned Rebrand Action |
| :--- | :--- | :--- | :--- |
| **Frontend UI (Web Client)** | `webui/frontend/` | • `index.html` (`<title>Open Swarm</title>`)<br>• `SettingsSheet.tsx` (brand header `Open Swarm`)<br>• `package.json` (`name: open-swarm-webui`)<br>• Dialog titles, splash copy, ARIA labels | • Change title to `Swarm Bot`<br>• Update header to `Swarm Bot`<br>• Update `package.json` description and metadata<br>• Keep CSS namespace `.os-` for layout stability or alias to `.sb-` |
| **Backend & Django UI** | `src/swarm/templates/`<br>`src/swarm/views/`<br>`src/swarm/` | • `templates/base.html` (`<title>Open Swarm</title>`)<br>• `templates/account/login.html` (splash text)<br>• Error pages and Django admin titles<br>• `swarm_cli.py` & `swarm_api.py` banner/help text | • Update base title & brand labels to `Swarm Bot`<br>• Update CLI banner/help: `Swarm Bot CLI`<br>• Update tagline: "A single bot to control all your swarms" |
| **Project & Packaging** | `pyproject.toml`<br>`docker-compose*.yml`<br>`Dockerfile` | • `pyproject.toml` (`name = "open-swarm"`, `description = ...`)<br>• `[project.scripts]` entry points<br>• Container image names and compose services | • Update description in `pyproject.toml` to: *"Swarm Bot: A single bot to control all your swarms (Hermes, TrueForge, etc.)"*<br>• Add `swarm-bot` script entry point (pointing to `swarm.core.swarm_cli:app`) alongside existing `swarm-cli`<br>• Update package name to `swarm-bot` (or preserve PyPI alias) |
| **Documentation & Guides** | `README.md`<br>`USERGUIDE.md`<br>`DEVELOPMENT.md`<br>`docs/` | • Hero titles & overview statements<br>• Architecture descriptions<br>• Quickstart commands (`git clone`, install guides) | • Update hero title to `# Swarm Bot`<br>• Add central positioning callout: *"A single bot to control all your swarms (Hermes, TrueForge, etc.)"*<br>• Retain historic references in `docs/archive/` and changelog |
| **Brand Assets** | `assets/brand/`<br>`static/brand/` | • SVGs, favicons, logos | • Update `<title>` tags inside SVGs from `Open Swarm` to `Swarm Bot`<br>• Maintain existing geometric bee / brand marks |

---

## 3. Implementation Phasing

To avoid breaking existing CI, installations, and active test suites, the rebrand is structured in three phases:

### Phase 1: User-Facing Brand & Messaging (Immediate)
- Update WebUI page titles (`index.html`, `base.html`).
- Update UI header text in `SettingsSheet.tsx` and Django templates.
- Update `README.md`, `USERGUIDE.md`, and top-level documentation with the new positioning statement:
  > *"Swarm Bot: A single bot to control all your swarms (Hermes, TrueForge, etc.)"*
- Add `swarm-bot` executable entry point in `pyproject.toml` (`swarm-bot = "swarm.core.swarm_cli:app"`).

### Phase 2: Packaging & CLI Polish
- Update `pyproject.toml` project description and metadata.
- Update `webui/frontend/package.json` name to `swarm-bot-webui`.
- Update CLI banners and help outputs to display `Swarm Bot`.

### Phase 3: Architectural & Repository Alignment (Low Risk)
- Coordinate any repository rename (`open-swarm` -> `swarm-bot`) with GitHub redirect configuration.
- Internal Python package `src/swarm/` stays unchanged to avoid breaking hundreds of imports.

---

## 4. Acceptance Criteria

- [ ] WebUI `<title>` and Django `<title>` display **Swarm Bot**.
- [ ] Header in `SettingsSheet.tsx` displays **Swarm Bot**.
- [ ] `README.md` features the updated title and statement: *"A single bot to control all your swarms (Hermes, TrueForge, etc.)"*.
- [ ] `pyproject.toml` provides a `swarm-bot` console script command.
- [ ] Vitest and Pytest test suites continue to pass with no broken imports or stale title assertions.
- [ ] A dedicated unit test `tests/unit/test_req862_rebrand_swarm_bot.py` validates title and brand honesty.
