# REQ-102 — README rewrite plan (look-only)

**Status (2026-09-05):** Product-truth rewrite landed in
[#785](https://github.com/matthewhand/open-swarm/pull/785) (closed #466).
Shape follow-up is [#791](https://github.com/matthewhand/open-swarm/issues/791)
(mermaid / layout / CI on [docs/DEVELOPER.md](../DEVELOPER.md)). This file
stays the look-only inventory / version-honesty table — do not treat it as
the live README.

Look-only investigation for [Issue #466](https://github.com/matthewhand/open-swarm/issues/466)
(REQ-102). This file proposed a new README direction. It did **not** rewrite
`README.md` on `main` in the look-only PR. No product code, no secrets, no live host, no
golden-journey.

**As-of:** `origin/main` @ `83a07cc5`
(`feat(webui): agent editor is agent-scoped; Blueprint is a picker (#404)`).

**Method:** full read of root `README.md` (403 lines) and
`pyproject.toml` `[project]` metadata; PyPI JSON
`https://pypi.org/pypi/open-swarm/json` (2026-09-04); `gh release list` /
`gh api …/releases` / `gh api …/tags` on `matthewhand/open-swarm`;
cross-check of README history commits and git tags. Chrome check:
`webui/frontend/src/App.tsx` (`/` and `/chat` mount `ChatPage` + left rail).
No Neon. No `:8001`. No secrets. No GIF filming.

**Siblings (cite, do not redo):**

| Sibling | What it already covers | This file |
|---------|------------------------|-----------|
| [PR #460](https://github.com/matthewhand/open-swarm/pull/460) `docs/debt/qa-wave3-structure-docs.md` (open; not on `main` yet) | Full `docs/` IA: keep/merge/archive/delete for every guide; chrome-honesty conflict; Team/Blueprint noun pile; MoA/Fusion cluster | README-only outline + version honesty. Do **not** re-inventory `docs/` |
| [Issue #456](https://github.com/matthewhand/open-swarm/issues/456) (REQ-97) | Near-release GIF showcase for CLI / API / remotes / combined teams | Park media. Do **not** film or swap GIFs here |
| [Issue #452](https://github.com/matthewhand/open-swarm/issues/452) (REQ-95) | Folder / docs structure | Out of scope |
| [Issue #463](https://github.com/matthewhand/open-swarm/issues/463) (REQ-100) | Herdr remotes are SSH-shaped, not HTTP like OpenMousBot / Hermes / Rakazo | README remotes copy must say this; no Herdr code here |
| [Issue #315](https://github.com/matthewhand/open-swarm/issues/315) | Harness vision docs | Out of scope |

**Product direction to promote (Matthew, 2026-09):** Grok-like SPA chrome
(left rail + selected-agent chat). Three agent modes — **API-owned agents**,
**CLI agents** (`opencode` / `grok` / `agy` / …), **remotes** (OpenMousBot /
Hermes / Rakazo / nested open-swarm; **Herdr is SSH-shaped** per #463).
**Teams** combine all three via openai-agents **handoff / agent-as-tool**.
Downplay or remove Blueprint Builder / `django_chat` / old MoA-first /
dual-web-UI emphasis where it fights that pitch.

---

## 1. Section inventory (current `README.md`)

Actions are for the **later implementer rewrite**, after Matthew picks the
outline. This PR does not apply them.

| # | Current section | Lines (approx.) | Action | Why |
|---|-----------------|-----------------|--------|-----|
| 1 | Title + project image | 1–5 | **rewrite** | Keep a mark; drop or shrink the wide splash if it fights Grok chrome. Logo file stays. |
| 2 | Opening: “Blueprints… two ways (CLI / API)” | 7–14 | **rewrite** | Pitch is now three agent modes + combined teams, not “blueprint as CLI or API.” Attribution sentence can move to a one-liner under History or Acknowledgements. |
| 3 | Elevator pitch (blueprint anywhere + web dashboard + memory) | 14 | **rewrite** | “Web dashboard” and “opt-in memory” bury the differentiator. Memory is still unvalidated (Roadmap). |
| 4 | Hero `docs/screenshots/landing.png` (“the dashboard”) | 16–19 | **delete** from README (park PNG) | Frame is the 2026-08-19 catalog Home (rainbow Quick Actions + top-nav). Live `/` is Grok rail + `ChatPage` (`App.tsx`). Recapture is a later tour ticket, not this rewrite. See #460 §2.4 and `qa-wave2-screenshots-tour.md`. |
| 5 | Hero `docs/demo/cli-and-api.gif` (zeus CLI + API) | 21–24 | **demote** | Keep the file; do not lead with zeus/MoA-era terminal loop. Replacement four-demo set is **#456** (do not film now). |
| 6 | Status: beta + 1100+ tests + “both web UIs” | 26 | **rewrite** | See §4. Dual-UI boast fights the SPA-chrome pitch. Test count and Alpha/beta disagree with package metadata. |
| 7 | Vision / Orchestration Patterns callout | 28 | **demote** | Keep a link. Do not open the README with “start at VISION.” Pitch first. |
| 8 | Quickstart (CLI) — clone, `list`, `launch codey`, `install` | 32–51 | **rewrite** | Becomes the **CLI-agent** quickstart (`cli-agents --init`, `launch cli_agent` / a named CLI). `install` (PyInstaller) is an advanced aside, not step 3. |
| 9 | `swarm-cli` command dump + **MoA team path** block | 53–67 | **demote** | Command encyclopedia belongs in `USERGUIDE.md`. MoA `--team` is a real engine but must not be the first multi-agent story. Park the snippet in `docs/MOA.md`. |
| 10 | Quickstart (API server) — compose + curl `/v1/*` | 69–86 | **rewrite** | Keep curl against `/v1/models` + chat/responses. Lead with an **API-owned agent** (`model` = a swarm agent / blueprint id), not `suggestion` as the only example. |
| 11 | API paragraph: CLI wrap + **Web UI Django-canonical / SPA experimental** | 88 | **rewrite** | CLI wrap stays, as the CLI-agent path. Kill “SPA is experimental; Django trailing-slash is day-to-day.” That is ADR-001-era copy. Product chrome is the Grok SPA. Django operator pages become a **link**, not the pitch. |
| 12 | Pinokio (local sideload) | 90–98 | **keep** (short) | Honesty constraint still true (not in the public catalog). One short block or a link is enough; do not grow it. |
| 13 | Architecture (two mermaid diagrams: gateway + consensus modes) | 102–142 | **rewrite** | First diagram should be **three agent kinds → one Team**. Current diagrams teach “blueprint = strategy over CLIs” and MoA/fusion modes (`cli_fusion` / `cli_map` / `persona_council`). Those stay in `docs/ORCHESTRATION_PATTERNS.md`. |
| 14 | Core Concepts — Agents / Blueprints / Team / Profiles / Persona·MoA / MCP / CLI fusion / Skills / Inference profiles / config JSON | 146–194 | **rewrite** + **demote** | Keep **Team** (handoff members) and the three kinds. Keep a one-line Blueprint = Python recipe / `model` id (GLOSSARY). Demote Profiles (`/v1/teams` alias), Persona/MoA, MCP, Skills, inference profiles, and the full `swarm_config.json` example to linked docs. |
| 15 | Bundled Blueprints tables (flagship + CLI fusion) | 198–222 | **demote** | A short “recipes you can `model:`” link to `docs/BLUEPRINT_LIBRARY.md` / `docs/EXAMPLES.md`. Do not list `codey`/`geese`/`jeeves` as the product. Drop “Agent Creator in the web UI” as a scaffold pitch (Blueprint Builder / creator is the old path). |
| 16 | Environment Variables table | 226–244 | **demote** | Move to `CONFIGURATION.md`. README install can name `OPENAI_API_KEY` / `API_AUTH_TOKEN` only. Django-named vars stay in config docs (REQ-56: Settings System copy does not say Django). |
| 17 | Developer — gateway vs workers + request sequence mermaid | 248–311 | **delete** from README (park) | Correct and useful; wrong front door. Park under `docs/ASYNC_RESPONSES.md` / `DEVELOPMENT.md`. |
| 18 | History gantt + evidence table | 313–347 | **rewrite** | Replace the gantt/table with the **short 1-line history** in §3. Keep the dated evidence in this file or `docs/archive/` so implementers do not lose it. |
| 19 | Development (pytest, ruff, SPA build, ADR-001 operator UI) | 349–375 | **demote** | Contributors use `CONTRIBUTING.md`. Drop the ADR-001 “supported operator UI is Django” sentence from the README. |
| 20 | Documentation map (14+ links) | 361–375 | **rewrite** | Short **Links** footer: USERGUIDE, GLOSSARY, REMOTE_HARNESSES, HERDR, CLI_FUSION, AUTH, CONTRIBUTING. Do not duplicate the full IA (#460). |
| 21 | Roadmap / Unfinished Features | 379–387 | **demote** | One honest line + link to `FEATURE_STATUS.md` / `ROADMAP.md`. Do not re-assert “SPA scope ADR-001 / Django canonical” as a shipped win on the front door. |
| 22 | Acknowledgements & Attribution | 389–393 | **keep** (short) | One or two sentences. OpenAI Swarm → openai-agents. |
| 23 | License | 395–397 | **keep** | MIT + NOTICE. |
| 24 | Contributing | 399–403 | **keep** (short) | Pointer to `CONTRIBUTING.md`. Fix the Alpha/beta clash there in a later honesty pass (not this PR). |

---

## 2. Proposed README outline

Target order after Matthew GO (implementer rewrite; **not this PR**):

```
# Open Swarm

1. Pitch (5–8 lines + optional one chrome still — not landing.png)
2. Short history (1-liners, §3)
3. Three agent modes
   3a. CLI agents — opencode / grok / agy / …
   3b. API-owned agents — OpenAI-compat /v1
   3c. Remotes — OpenMousBot / Hermes / Rakazo / nested open-swarm
       + Herdr is SSH-shaped (#463), not “another HTTP remote”
4. Combined teams — handoff / agent-as-tool (the differentiator)
5. Install
6. Links
7. Status / license / contributing (compact)
```

### 2.1 Pitch (draft direction, not final copy)

Open Swarm is a Grok-like agent workspace: a left rail of agents and a
chat with the one you picked. Agents come in three kinds — **API** (owned
by this process), **CLI** (your installed `opencode` / `grok` / `agy` / …),
and **remote** (OpenMousBot, Hermes, Rakazo, or another open-swarm). A
**Team** puts any mix of those three in one roster so they can see and
talk via openai-agents **handoff** and **agent-as-tool**.

One OpenAI-compatible door (`/v1/chat/completions`, `/v1/responses`) is
how other clients reach the same agents. The SPA is the product chrome;
Django operator pages and Blueprint recipes stay available, they are not
the headline.

Do **not** lead with: Blueprint Builder, `django_chat`, Mixture-of-Agents
as the first team story, “two web UIs,” or “SPA is experimental.”

### 2.2 History placement

Immediately under the pitch. Evolution only. No marketing essay. See §3.

### 2.3 CLI-agent quickstart (sketch)

```bash
# after Install
export OPENAI_API_KEY="..."      # or whatever the chosen CLI already uses
uv run swarm-cli cli-agents --init --write --check-auth
uv run swarm-cli launch cli_agent --message "What CLIs can you see?"
```

Point at `docs/CLI_FUSION.md` for failover / fusion. Do not open with
`launch codey` or `swarm-cli moa --team`.

### 2.4 API-agent quickstart (sketch)

```bash
cp .env.example .env
docker compose up -d
curl -sf http://localhost:8000/v1/models
curl -sf http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${API_AUTH_TOKEN}" \
  -d '{"model":"<api-owned-agent-id>","messages":[{"role":"user","content":"ping"}]}'
```

Name the `model` field as “which agent (or recipe) handles this.” One
line that `/` is the Grok SPA when `webui/frontend/dist/` is built.

### 2.5 Remote quickstart (sketch)

```bash
uv run swarm-cli remotes          # catalog; empty until + add (#384 / REQ-59)
# add OpenMousBot / Hermes / Rakazo / nested open-swarm (HTTP)
uv run swarm-cli remotes place omb
```

Label **OpenMousBot** (not OMB) in user copy — #456 / REQ-59. Nested
open-swarm is another process + its own store; do not add this instance
as its own remote.

**Herdr:** local Herdr wraps CLIs on this box. A *remote* Herdr is
**SSH to that Herdr host**, then talk to the CLIs it wraps. It is not
the same kind as OpenMousBot / Hermes / Rakazo. Pointer: `docs/HERDR.md`
and #463. Do not invent a live LAN example.

### 2.6 Combined teams (the differentiator)

One short story: a Team roster with `{kind: api|cli|remote|herdr}`
members that **handoff / as_tool** to each other (`/v1/agent-team/` or
`/v1/team-rosters/` — GLOSSARY names). One `curl` or `swarm-cli remotes`
snippet that places a remote next to a CLI and an API agent.

Do **not** use `swarm-cli moa --team` as this story (that path is
scripted specialists after read-only consensus, no openai-agents).
Do **not** call `/v1/teams` aliases a Team (Profiles).

GIF/montage for this block is **#456**, near release.

### 2.7 Install

Lead with source + `uv` (what `main` actually runs):

```bash
git clone https://github.com/matthewhand/open-swarm.git
cd open-swarm
uv sync --all-extras
```

Then a **version-honest** PyPI line:

> PyPI `open-swarm` latest is **0.5.4** (2026-06-19) — same as GitHub
> Release `v0.5.4`. `main` is ahead of that cut. `pip install open-swarm`
> does **not** include Grok chrome, remotes catalog, or combined-team
> work landed after June. Prefer clone until the next release.

Pinokio: git URL sideload only (keep the honesty line).

### 2.8 Links (short)

- CLI reference: `USERGUIDE.md`
- Nouns: `docs/GLOSSARY.md`
- Remotes: `docs/REMOTE_HARNESSES.md` · Herdr: `docs/HERDR.md`
- CLI wrap / fusion: `docs/CLI_FUSION.md`
- Auth: `docs/AUTH.md`
- Status board: `FEATURE_STATUS.md`
- Vision (adapt + orchestrate): `docs/VISION.md`
- Contributing: `CONTRIBUTING.md`

No second documentation-map essay. Full IA lives in #460.

---

## 3. Draft 1-liner history

Evolution only. Dates from git tags / the commits the current README
already cites. Implementer may trim; do not add slogans.

- **2024-12** — Started as a derivative of OpenAI’s experimental Swarm; Django REST API in the same week (`c3a092c4`, 2024-12-26).
- **2026-02** — First git tag `0.0.1` (2026-02-20). No GitHub Release and no PyPI `0.0.1`; PyPI of that era is timestamp `0.1.*` builds.
- **2026-04** — React / DaisyUI web UI (`9077902b`, 2026-04-04).
- **2026-06-10/11** — FOSS cut `v0.3.0` (MoA + cleanup). GitHub Release published 2026-06-10; git tag date 2026-06-11.
- **2026-06-16** — `v0.4.0` CLI Agent Fusion (wrap installed CLIs as `model` ids).
- **2026-06-18/19** — `v0.5.x` `/v1/responses` + last **published** cut `v0.5.4` (2026-06-19). Release title still leads with `django_chat`.
- **2026-07+** — Remotes, Team handoff members, Herdr, Grok-like SPA chrome on `main` — **not** in 0.5.4.
- **2026-08-18** — ADR-001 recorded Django trailing-slash as canonical operator UI; SPA kept `/` + `/chat` only (`3d870d62`).
- **2026-09** — Product front door flips: Grok SPA chrome + three agent kinds + combined teams. ADR-001 Django-primary copy leaves the README.

The current README gantt/table is accurate on those git dates (see §4).
It is the wrong *length* and the wrong *emphasis* (MoA / Django UI / dual
web) for the new pitch. Park the mermaid + evidence table in
`docs/archive/` or keep them only here.

---

## 4. Version honesty table

Sources pulled 2026-09-04:

| Source | Latest / fact |
|--------|----------------|
| `pyproject.toml` | `version = "0.5.4"` · `description = "Open Swarm: Orchestrating AI Agent Swarms with Django"` · classifier `Development Status :: 3 - Alpha` · `Framework :: Django :: 4.2` |
| PyPI `open-swarm` | Latest **0.5.4**, uploaded 2026-06-19T01:29:30Z, not yanked. **Summary still: “Open Swarm: Orchestrating AI Agent Swarms with Django”.** 105 published versions: semver `0.3.0`–`0.5.4` plus 84 timestamp `0.1.<epoch>` wheels (2025-03-27 … 2026-06-02). No `0.0.1`, no `0.1.0`. |
| GitHub Releases | 21 releases, `v0.3.0` … `v0.5.4`. Latest **v0.5.4** published 2026-06-19T01:29:02Z, name **“v0.5.4 — django_chat resolves its LLM profile.”** None draft/prerelease. |
| Git tags | Those 21 `v*` tags plus **`0.0.1`** (2026-02-20, sha `29b61b15`). No `v0.0.1`. |

**FLAG:** PyPI summary / `pyproject.toml` description still sell **Django**.
That is the first thing `pip index` / pypi.org shows. The README rewrite
cannot fix the published wheel; a later release must change
`project.description` (and ideally the Alpha classifier) so PyPI stops
contradicting the SPA / three-mode pitch. Call that out in the
implementer README install note; do not silently pretend `pip install`
is the Grok-chrome product.

### 4.1 Every version / status claim in today’s README

| README claim | Where | Verdict | Evidence |
|--------------|-------|---------|----------|
| **Status: beta** | L26 | **stale** vs package | `pyproject.toml` + PyPI classifier = **3 - Alpha**. `CONTRIBUTING.md` L3 = “alpha-stage.” Pick one word in the rewrite; changing the classifier is a release, not a README-only edit. |
| Core + CLI + OpenAI API + websocket + **both web UIs** working | L26 | **stale / fights pitch** | Dual-UI is what 2026-09 wants downplayed. Live SPA is Grok rail + chat; Django operator pages still exist. “Both working” oversells parity (README itself later says SPA is not at parity). |
| **1100+ test suite** | L26, L353 | **stale (low)** | `FEATURE_STATUS.md` still cites **673** passed @ `4c7e1b28`. This tree has **2302** `def test_` in `tests/` plus **460** frontend `it(`/`test(` (static count, suite not re-run). Do not invent a new badge until someone records a real pytest total. Suggested rewrite: “keyless pytest + frontend unit tests” with no integer, or a number taken from a fresh CI run. |
| Verified in Docker | L26 | **plausible / keep-light** | Compose + Dockerfile exist; not re-verified here. |
| `v0.3` MoA · gantt 2026-06-11–12 | L328 | **match** (minor date skew) | Tag `v0.3.0` creatordate 2026-06-11; GitHub Release + PyPI **0.3.0** are **2026-06-10**. Table L342 “v0.3.0 MoA \| tag v0.3.0” is the tag date. |
| `v0.4` CLI fusion · 2026-06-16–17 | L329 | **match** | Tag/Release/PyPI `0.4.0` 2026-06-16; `0.4.11` 2026-06-17. |
| `v0.5` responses · 2026-06-18–19 | L330 | **match** | `v0.5.0` 2026-06-18; `v0.5.4` 2026-06-19. |
| Tag **0.0.1** · 2026-02-20 | L326, L340 | **match** as a **git tag only** | Tag exists. **Missing** from GitHub Releases and PyPI. Honest. |
| Changelog **0.1.0 / 2024-01-01** is not a tag (omitted) | L315 | **match** | `CHANGELOG.md` still has `## [0.1.0] - 2024-01-01`. No tag, no PyPI `0.1.0`. |
| v0.5.4 · 2026-06-19 | L345 | **match** | PyPI + GitHub latest. |
| Initial commit 2024-12-21 | L338 | **match** | `872018a0`. |
| Django REST API · 2024-12-26 · `c3a092c4` | L339 | **match** | Commit message + date. |
| React Web UI · 2026-04-04 · `9077902b` | L341 | **match** | Commit exists. |
| CLI fusion · 2026-06-16 · `976cbd49` | L343 | **match** | |
| `/v1/responses` · 2026-06-18 · `50492380` | L344 | **match** | |
| Worker gates · 2026-07-22 · `ff014180` | L346 | **match as git**; **missing from published** | After `v0.5.4`. `main` ≠ PyPI. |
| ADR-001 · 2026-08-18 · `3d870d62` | L347 | **match as git**; **missing from published** | Same. Also **direction-stale**: 2026-09 pitch supersedes Django-primary README copy. |
| PyPI package name `open-swarm` (comment) | L35 | **match** | Install snippet is **clone + uv**, not `pip install`. |
| Pinokio **not** in the public catalog | L92 | **keep** (honesty) | Unchanged constraint (#363). |
| SPA **experimental** / not at parity; Django is day-to-day operator UI | L88, L360, L383 | **direction-stale** | True as ADR-001 text; false as the 2026-09 front-door story. `App.tsx`: `/` is `ChatPage`. |
| `cli-and-api.gif` / `landing.png` exist | L17, L22 | **files exist**; **pixels stale** | GIF on disk (zeus/API/MoA-era). `landing.png` is catalog Home, not Grok chrome. Replacement media = #456 + tour recapture, not this PR. |

### 4.2 Claims the README does **not** make (gaps)

| Gap | Note |
|-----|------|
| No “latest release is 0.5.4” near the title | Readers who `pip install` get June 2026. Say so. |
| No warning that `main` ≫ 0.5.4 | Remotes, Grok chrome, rosters, Herdr, agent editor are unreleased. |
| Latest GitHub Release **title** is `django_chat` | Front-door of Releases fights the new pitch even if the README is rewritten. Flag for the next release notes; out of scope to retitle old releases. |
| `docs/QUICKSTART.md` still says `pip install --user open-swarm` | Install-story clash (#460 §2.2). Fix in the implementer README; do not rewrite QUICKSTART in this PR. |
| `docs/VISION.md` “What is built today **(v0.5.4)**” | Version pin is the published cut; body lists later CLI patterns. Honesty later; not a README rewrite. |

---

## 5. Older content to remove from the README or park in `docs/`

Move or drop from the **front door** only. Do **not** mass-delete the
targets in the implementer README PR either — park, then link.

| Content | Park / remove | Destination (later) |
|---------|---------------|---------------------|
| `landing.png` hero + “the dashboard” | **remove** from README | Stay in `docs/screenshots/` until recapture (`qa-wave2-screenshots-tour.md`, `tests-ci.md` D-01). Do not recapture here. |
| `cli-and-api.gif` as lead demo | **demote** | Keep `docs/demo/cli-and-api.gif`. New CLI/API/remote/team GIFs = **#456**. |
| MoA team-path bash block | **remove** from README | Already documented in `docs/MOA.md`. |
| Full `swarm-cli` command dump | **remove** | `USERGUIDE.md`. |
| Dual-web-UI / ADR-001 “Django is canonical, SPA experimental” | **remove** from README | Keep ADR-001 as a historical decision; addendum belongs with #460 chrome honesty, not a silent ADR rewrite in the README PR. |
| Blueprint Builder / Agent Creator scaffold pitch | **remove** | Wizard stays in USERGUIDE. Creator/Builder is not the 2026-09 pitch. |
| `django_chat` as a product story | **not in README body today** — keep it that way | Blueprint still exists (`src/swarm/blueprints/django_chat`). Latest GitHub Release *name* still leads with it — release-notes problem, not a README include. |
| Flagship blueprint table (`codey`, `geese`, `jeeves`, …) | **demote** | `docs/BLUEPRINT_LIBRARY.md` / `src/swarm/blueprints/README.md`. |
| CLI-fusion mode table as architecture | **demote** | `docs/CLI_FUSION.md` + `docs/ORCHESTRATION_PATTERNS.md`. |
| Full env-var table (Django-named keys) | **demote** | `CONFIGURATION.md`. |
| Gateway/workers + `/v1/responses` sequence mermaid | **remove** from README | `docs/ASYNC_RESPONSES.md` / Developer guide. |
| History gantt + 8-row evidence table | **remove** from README | This file §3–§4; optional `docs/archive/` copy. |
| 14-link documentation map | **shrink** | §2.8. Full map is #460 IA, not the README. |
| Roadmap checkbox list (SPA scope, MCP server, memory, fusion follow-ups) | **shrink** | `FEATURE_STATUS.md` / `ROADMAP.md`. |
| `docs/GUIDED_TOUR.md` / `USER_JOURNEY.md` as “start here” | **demote** | Those tours still describe Home · Chat top-nav (#460 §2.4). Link only after recapture. |

**Do not park by rewriting those deep docs in the README implementer PR.**
Pointer + one honesty sentence is enough.

**Copy nits for the later rewrite (not this PR):**

- User-facing remote name is **OpenMousBot** (REQ-59 / #456). Internal id
  `omb` is fine in CLI. `docs/REMOTE_HARNESSES.md` / GLOSSARY still say
  OpenMausBot / OMB in places — that is a docs-IA follow-up, not a
  mass rename here.
- Do not put LAN IPs (`198.51.100.30`, Fly URLs, hostnames) in the README.
  `docs/REMOTE_HARNESSES.md` already has operator LAN facts; keep them
  out of the front door.
- Herdr ≠ HTTP remotes (#463).

---

## 6. Do not do yet

Until Matthew GO on the outline, and until the named Issues unblock:

1. **Do not rewrite `README.md` on `main`.** This file is the plan. One
   implementer cloud later (#466 success item 4).
2. **Do not mass-delete or move `docs/`.** No archive sweep, no IA
   execution. That is #460 / #452. Cite `qa-wave3-structure-docs.md`;
   do not redo it.
3. **Do not film or swap GIFs / mp4s.** Near-release media is
   [Issue #456](https://github.com/matthewhand/open-swarm/issues/456).
   Keep the existing `cli-and-api.gif` on disk.
4. **Do not recapture `landing.png` or the journey lock.** Screenshot
   registry + captions must move together (`tests-ci.md` D-01,
   `qa-wave2-screenshots-tour.md`). A README that claims “Grok rail”
   while still embedding the catalog PNG is worse than no hero.
5. **Do not retitle GitHub Releases or yank PyPI.** Flag only.
6. **Do not change `pyproject.toml` description / classifiers** in the
   README implementer PR unless Matthew asks for a release-prep commit.
   The Django summary stays a known PyPI lie until a real publish.
7. **Do not convert `docs/requirements/`** or edit existing
   `docs/debt/{core,webui,tests-ci,django-spa-overlap}.md`.
8. **Do not enable Oracle or Neon.** Do not bounce a live host.
9. **Do not remount** deleted SPA Builder / Teams / Settings pages to
   make old tour PNGs true.
10. **No `Fixes` / `Closes` on #466** from this look-only PR. Refs only.
    Implementer rewrite is a later Issue after outline GO.

---

## 7. Suggested implementer checklist (after GO)

Not this PR. When Matthew picks the outline:

- [ ] Replace pitch + history + three quickstarts + combined-team + install + links.
- [ ] Drop dual-UI / Builder / MoA-first / `landing.png` hero.
- [ ] State PyPI **0.5.4** + Django summary + `main` is ahead.
- [ ] Leave GIF slots as “coming (#456)” or keep the old gif captioned as historical CLI/API, not the new chrome.
- [ ] Link GLOSSARY for Team vs Profiles vs roster; do not teach `/v1/teams` as composition.
- [ ] OpenMousBot in user copy; Herdr called out as SSH-shaped.
- [ ] No secrets, no LAN inventory, no `Fixes #466` until the rewrite lands and Matthew agrees it matches.

---

## Method / out of scope

- Read-only vs `README.md`, `pyproject.toml`, PyPI JSON, GitHub
  Releases/tags, `App.tsx` routes, GLOSSARY / ADR-001 / HERDR /
  REMOTE_HARNESSES / CHANGELOG / FEATURE_STATUS / CONTRIBUTING /
  QUICKSTART, and the open #460 structure note.
- Did **not** rewrite README, run golden-journey, recapture screenshots,
  publish to PyPI, or edit other `docs/debt/*` files.
- Test integers in §4 are **static counts**, not a CI total.
