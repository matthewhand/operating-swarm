# ADR-008: Optional 3D robot avatar theme family (Reachy-inspired)

- **Status:** Accepted — Phase 0 ADR shipped; **Phases 1–3 implemented** (theme enabled in pickers, lazy WebGL pose-player, 2×2 body/head combo catalog, status→clip wire). See CHANGELOG / FEATURE_STATUS.
- **Date:** 2026-09-06 (amends the 2026-09-04 look-only draft that landed via [#675](https://github.com/matthewhand/open-swarm/pull/675))
- **Issue:** [#667](https://github.com/matthewhand/open-swarm/issues/667) (REQ-194)
- **Reachy report:** [reachy-3d-avatar-inspiration.md](../reports/reachy-3d-avatar-inspiration.md)
- **Related:** [#662](https://github.com/matthewhand/open-swarm/issues/662) (REQ-188C-3 one avatar-theme store — **closed**), [#346](https://github.com/matthewhand/open-swarm/issues/346) (REQ-34 Blobs, closed), [#540](https://github.com/matthewhand/open-swarm/issues/540) (REQ-144 Django prefs), [ADR-001](../ADR-001-primary-ui.md), [ADR-002](./002-config-ownership.md)
- **Inspiration (external):** [matthewhand/reachy-subconscious-expression-app](https://github.com/matthewhand/reachy-subconscious-expression-app) — [PR #10](https://github.com/matthewhand/reachy-subconscious-expression-app/pull/10) cited on #667. Public corroboration: [pollen-robotics/reachy-mini-desktop-app](https://github.com/pollen-robotics/reachy-mini-desktop-app).
- **Supersedes:** the 2026-09-04 draft’s **iframe-first** host path and **AnimationMixer / bone-name** rig. Those were parked as “pending Reachy audit.” The audit (PR #10 via #667) is now in the report.

**Decision:** add an **optional** Settings Rail theme family `robot3d` (“3D robot”) that can play idle / listen / working / dance-style **pose clips** without blocking chat.

1. **Theme key** = the existing Rail store `swarm_avatar_theme` (value `robot3d`). No second persist key for the theme. Combo pick is a **sub-key** only while the theme is `robot3d`.
2. **Host path** = **lazy `import()` of an extractable pose-player** on the **chat header** (one WebGL context). Do **not** iframe Glance. Do **not** add `three` to the chat graph until `robot3d` is selected.
3. **Playback** = baked `MiniPose` sequences (or a pose stream), **not** `THREE.AnimationMixer` skeletal clips. See the [Reachy report](../reports/reachy-3d-avatar-inspiration.md).
4. **Mix-and-match** (Phase 2) = `MiniPose` + head **attach offsets**, not bone-name swap.
5. Custom uploaded 2D `avatar_path` still wins. No Neon. No secrets.

This ADR + the Reachy report are **Phase 0** of REQ-194. Phase 0 is complete here. **Phases 1–3 are implemented** on the private mirror (`matthewhand/open-swarm-private`):

1. **Phase 1 — one mesh:** `robot3d` is now a selectable theme on the one Rail key; the chat header lazily `import()`s a WebGL pose-player (`webui/frontend/src/lib/robot3d/posePlayer.ts`) that poses an **original procedural robot** (primitives, MIT) from baked `MiniPose` clips (`clips.ts`) — idle/working required, listen/error/dance shared. WebGL-less environments render a static SVG robot; chat never blocks. `three` is code-split out of the main chat graph (ADR-008 §2 decision 2).
2. **Phase 2 — combos:** `catalog.ts` ships 2 bodies × 2 heads on one pose family (attach offsets, `headAttachment`); the combo sub-key (`swarm_robot3d_combo`) is active only while the theme is `robot3d` (§2.4 rules 1–5).
3. **Phase 3 — status wire:** `statusMap.ts` maps AgentStatus working/listen/error/happy → clips; `Robot3DAvatar` + fallback react to status; tests cover the mapping.

Follow-up bodies in §10 are retained as reference.

Evidence below is from `origin/main` at writing (`869aace9` and this branch). No secrets are documented. Use `${VAR}` names only.

---

## Issue quote (REQ-194)

**Intent:** Users can pick a 3D robot theme (not only Blobs / bland / Bee / upload) that feels alive like Reachy Mini’s 3D presence; later, swap body/head meshes without rewriting clips.

**Success (phased, from #667):**

1. **Phase 0 — ADRs:** Reachy report (stack, clip/rig contract, licensing) + open-swarm ADR (embed path, perf, theme settings key, event hooks). **This PR.**
2. **Phase 1 — One mesh:** Ship Reachy-like (or licensed) mesh + idle/working clips in SPA theme picker; chat never blocked on WebGL.
3. **Phase 2 — Combos:** Document bone/attachment contract; ≥2 body × ≥2 head that play the same clips. *(Contract is MiniPose + sockets — see report §2.4.)*
4. **Phase 3 — Status wire:** Map agent working/listen/error to animation states (optional mood later).

**Constraints (from #667):** Respect Reachy/URDF/Three LICENSE+NOTICE. No secrets. No Neon. Prefer extractable viewer package over forking the whole subconscious app. Coordinate Settings Rail avatar theme (#662 one-store). SaaS N/A.

---

## 1. What changed vs the 2026-09-04 draft

| 2026-09-04 draft | After PR #10 / this amend |
|---|---|
| Sibling Reachy audit still pending | Report landed: [reachy-3d-avatar-inspiration.md](../reports/reachy-3d-avatar-inspiration.md) |
| Iframe → extractable viewer as Phase 1 pick | **Lazy WebGL on chat header.** Iframe of Glance is **rejected**. Same-origin iframe of the *extracted* player is a fallback only if the lazy module pollutes the SPA |
| Clips = AnimationMixer / bone names | Clips = **`MiniPose` frame lists** (or pose stream) |
| Phase 2 = shared `bones[]` + guessed URDF names | Phase 2 = **attach offsets** + the same MiniPose fields |
| Rail keys `blobs` / `bland` only | Also **`bee`**. `#662` is **closed** — one store |
| Does not `Fixes` #667 | Phase 0 success line is satisfied; follow-ups in §10 |

---

## 2. Feasibility (what exists today)

open-swarm already has a **Settings Rail avatar theme** (`blobs` / `bland` / `bee`) on **one** persist key. Neither renderer is WebGL. The SPA `package.json` has no `three`, no R3F, no URDF loader.

A 3D family is feasible as a **new optional value** on that same Rail store — not as a rewrite of Blobs/Bee, and not as a merge into leftover Agent Router SVG packs.

The expensive parts are (1) isolation so chat never waits on GL, (2) vendoring/baking meshes the inspiration app gitignores, (3) a **shared MiniPose socket** so Phase 2 combos do not fork clips.

---

## 3. Today’s avatar map

`#662` closed: Settings → Rail → Avatar theme is the theme every Settings-reachable rail uses. One persist key. One picker.

### 3.1 Settings Rail store (canonical)

| Item | Value | Evidence |
|---|---|---|
| Keys | `blobs` (default), `bland`, `bee`, legacy `default` → `bland` | `webui/frontend/src/lib/avatarTheme.ts` |
| Reserved (not selectable) | `robot3d` | `ROBOT3D_THEME_RESERVED`; omitted from `AVATAR_THEMES` until Phase 1 |
| Persist | `localStorage.swarm_avatar_theme` | `AVATAR_THEME_STORAGE_KEY` |
| Same-tab event | `swarm:set-avatar-theme` | `AVATAR_THEME_SET_EVENT` |
| Default | `blobs`; storing Blobs **removes** the key | `saveAvatarTheme` / `defaultAvatarTheme` |
| Settings picker | Settings sheet → **Rail** → “Avatar theme” | `SettingsSheet.tsx` `RailPane` + `AvatarThemePicker.tsx` |
| Django twin | `/settings/` select `#os-avatar-theme` | `src/swarm/templates/settings_dashboard.html`; `src/swarm/static/js/chrome_avatar_theme.js` |
| Tests | persist + labels | `avatarTheme.test.ts`; `tests/unit/test_req155_avatar_theme.py`; `e2e/settings-sheet.spec.ts`; `e2e/bee-avatar-theme.spec.ts` |

Picker copy today: Default (static grey), Blobs (per-agent shapes + slit eyes), Bee (geometric brand marks, opt-in, never auto-applied). **Custom uploaded faces always win.**

`saveAvatarTheme('robot3d')` **persists since Phase 1** added the key (`webui/frontend/src/lib/avatarTheme.ts`); both the SPA picker and the Django `/settings/` twin offer an enabled **3D robot** option, and the combo sub-picker appears only while `robot3d` is active (ADR-008 §2 decision 1).

### 3.2 How faces render on the rail and in chat

Shared component: `webui/frontend/src/components/AgentAvatar.tsx` (Grok chrome — **not** `AgentSidebar/AgentAvatar.tsx`).

Resolution order:

1. **Custom `src`** (trimmed, non-empty, image not broken) → circular `<img>`, `data-agent-avatar="custom"`.
2. Else **theme `blobs`** → `BlobAvatar` SVG, `data-avatar-theme="blobs"`.
3. Else **theme `bee`** → Bee SVG, `data-avatar-theme="bee"`.
4. Else **theme `bland`** (and migrated `default`) → grey circle + silhouette.

| Surface | Size | What it paints | File |
|---|---|---|---|
| Left-rail conversation row | `sm` | `AgentAvatar` with `src={agent.avatar_path}` | `AgentSidebar.tsx` |
| Favourite tiles | `lg` | same | `AgentSidebar.tsx` |
| Chat header (non-team) | `lg` | same; `active` when streaming **or** WS `status === 'open'` | `ChatPage.tsx` |
| Avatar-only rail (`width ≤ 96px`) | still `sm` faces | names hide; faces stay | `railResize.ts` `AVATAR_ONLY_THRESHOLD` |

Blobs: deterministic shape + colour hashed from `agentId`. `prefers-reduced-motion: reduce` disables wander. Chat header currently marks `active` whenever the websocket is `open`, so eyes wander for the whole connected session — not only while a reply streams. Phase 3 must not copy that as “listen” without an explicit remap.

**Decision for 3D:** custom 2D `avatar_path` **still wins** over `robot3d`. Do not treat an arbitrary user glTF/URDF upload as Phase 1–2 (XSS / GPU / license risk). Combo picks are catalog ids, not free-form mesh URLs.

### 3.3 What does **not** use the Rail theme

| Surface | What it shows | Notes |
|---|---|---|
| Scale-out / team stacks | Coloured dots + pulse (`AvatarStack`) | REQ-66 / REQ-68. Do not spawn WebGL per stacked face |
| Grok chat **transcript** | No per-bubble face | Header only |
| Django operator rail | `os-agent-dot` colour marks | Not Blobs |
| Django library cards | custom img or Bert SVG | `blueprint_card.html` |

### 3.4 Leftover Agent Router packs (do not confuse)

`/agents` is still mounted (`App.tsx`) despite [ADR-001](../ADR-001-primary-ui.md). That page historically had a second SVG pack enum (`chassis` / `pixel` / …). `#662` unified persist onto `swarm_avatar_theme`. **Do not** add `robot3d` to any leftover pack enum. The Rail picker is the only place the 3D family appears.

---

## 4. Theme settings key

Add **one** Rail value (Phase 1; reserved in Phase 0):

| Persist value | Picker label | Meaning |
|---|---|---|
| `robot3d` | 3D robot | Optional family. Viewer + catalog live behind this key |

Keep `blobs` / `bland` / `bee` / legacy `default`. Unknown values still fall back to `blobs` (`isAvatarTheme`).

**#662 coordination (done, still binding):**

- Phase 1 extends `AVATAR_THEMES` in `avatarTheme.ts` **and** the Django `#os-avatar-theme` script so Settings ↔ Chat hops stay one key (`swarm_avatar_theme`).
- Do **not** introduce `swarm_avatar_theme_3d` or a second picker.
- Combo selection (Phase 2) is a **sub-key** only while `theme === robot3d`, e.g. `swarm_avatar_robot3d_combo` = `{ "body": "mini-full", "head": "mini-full" }` — ignored unless the theme is `robot3d`.
- After #540, both keys move to Django prefs with the rest of the UI prefs; localStorage seed-once.

Phase 0 stub: disabled option + link to this ADR (`ROBOT3D_ADR_HREF`). Django twin matches.

---

## 5. Embed path

#667: prefer an **extractable viewer package** over forking the subconscious app.
PR #10 via #667: prefer **lazy WebGL on the chat hero**; do **not** iframe Glance.

| Option | Verdict |
|---|---|
| **A. Lazy `import()` of an extractable pose-player on the chat header** | **Pick for Phase 1.** Separate async chunk; SPA `package.json` chat graph stays Three-free until the user selects `robot3d`; one WebGL context; `play(clipId)` is fire-and-forget |
| **B. Same-origin iframe of that extracted player only** | Allowed **fallback** if the lazy chunk still pollutes input latency or we need a hard realm teardown. Not the default. Still not Glance |
| **C. Iframe Glance / the whole subconscious app** | **Reject.** Operator chrome + daemon + emotion-wheel is out of scope (PR #10) |
| **D. Fork the whole Reachy app into `webui/`** | Reject |
| **E. Cross-origin hosted viewer** | Reject. Network + possible keys; #667 forbids secrets; offline local host must work |
| **F. N WebGL contexts (one per rail tile)** | Reject. Breaks §7 |

Presence vs tiles:

| Slot | Phase 1 | Why |
|---|---|---|
| Chat header (`lg`) | **One** live 3D instance (the presence slot) | Reachy-style “alive” chrome without N canvases |
| Rail rows / fav tiles / avatar-only rail | 2D **poster** (static frame or last 2D theme) | Narrow rail; WebGL per row would blow the budget |
| Scale-out stacks | unchanged dots | Different widget |
| Transcript bubbles | no face | Do not add GL to the message list |

Fallback: WebGL fail, `prefers-reduced-motion: reduce`, or chunk still booting → show Blobs (or the user’s last 2D theme). Chat chrome stays painted. First contentful chat paint must not wait on the dynamic import.

Teardown: `visibilitychange` / unmount → `pause`. Theme switch away from `robot3d` → dispose the renderer (release the GL context). Reuse one player across agent switches; `play()` / combo message only.

---

## 6. Event hooks (idle / listen / working)

Grok chat already has client-side signals — **no new WS mood channel in Phase 1**. Phase 1 may drive `idle` / `working` from these hooks (or a Settings “preview working”). Phase 3 makes the map canonical.

Suggested helper (implement later, not in this PR):

```ts
export type Robot3dClipId = 'idle' | 'listen' | 'working' | 'dance' | 'error'

export function robot3dClipFromChat(input: {
  streaming: boolean
  wsStatus: 'connecting' | 'open' | 'closed' | 'failed'
  toolRunning: boolean
  toolError: boolean
  composerFocused: boolean
}): Robot3dClipId {
  if (input.wsStatus === 'failed' || input.toolError) return 'error'
  if (input.streaming || input.toolRunning) return 'working'
  if (input.wsStatus === 'open' && input.composerFocused) return 'listen'
  return 'idle'
}
```

| Signal | Where today | Clip |
|---|---|---|
| No stream; WS not failed | `ChatPage` `streamingMessage`, `status` | `idle` |
| WS `open` + composer focused / awaiting user | WS status + focus (**not** a named `listen` flag today) | `listen` (Phase 3; do not treat “WS open” alone as listen — that is today’s Blob `active` bug) |
| Assistant streaming, or `tool_status` `running` | `chatWs.ts` `ToolStatus`; header stream timer | `working` |
| WS `failed` / `tool_status` `error` | `chatWs.ts`; Chat header `statusLabel` | `error` (Phase 3) |
| Optional celebration | Agent Router `happy` only today | `dance` (opt-in, never auto-loop on every reply) |

Inbound `type: "status"` frames on the consumer (`consumers.py`) are **text lines**, not a structured mood enum. Do not invent a server mood SoT until Phase 3 proves those lines are not enough.

Clip changes are fire-and-forget. The player crossfades `MiniPose` sequences; the composer and WS parser do not `await` a frame.

---

## 7. Perf budget (local SPA; do not FF `:8001`)

Implement PRs must not **deploy** to a live `:8001` host. The budget is what a local uvicorn+ASGI browser session will feel.

| Budget | Cap |
|---|---|
| Main SPA JS | **0** Three/URDF/GLTF parsers unless `robot3d` is selected (then the lazy chunk / package only) |
| WebGL contexts | **1** (header presence). Zero when theme is Blobs/bland/bee or a custom 2D face is showing |
| Rail / fav / stack | No GL. Poster or existing 2D |
| Chat first paint / send | Must succeed if the chunk is slow, blocked, or `webglcontextlost` |
| Frame rate | Idle ≤ 30 fps; pause when hidden; no work on `visibilityState === 'hidden'` |
| Payload (Phase 1) | One mesh + idle/working. Prefer a **decimated glTF**, not a research-size URDF+STL dump on every header mount. Exact MB after the chosen tag’s LICENSE check |
| CPU vs composer | Dropped frames must not stall `<input>` or `chatWs` parse |
| Memory | Dispose on theme-off; no leaked contexts across agent switches |
| A11y | Decorative (`aria-hidden`) like today’s faces; no second live region on the header |

No Neon. No new env secrets. Viewer config is public static + the Rail theme key.

---

## 8. Rig contract (pointer)

Normative `MiniPose`, clip JSON, mix-and-match rules, and `Robot3dRigManifest` live in the [Reachy report §2](../reports/reachy-3d-avatar-inspiration.md). This ADR does not re-guess Pollen bone strings.

Phase 1 ships one `kind: 'full'` mesh that already plays `idle` / `working`. Phase 2 must not land a second body or head until the manifest validator passes.

---

## 9. Phased success

### Phase 0 — this PR

- Reachy report: stack, pose/clip contract, licensing.
- This ADR: embed path, perf, theme key, event hooks.
- Optional stub shipped in Phase 0; **Phases 1–3 implemented** — enabled “3D robot” option on both pickers, lazy WebGL pose-player on the chat header, 2×2 body/head combo catalog, AgentStatus → clip wire.
- No mesh runtime from the licensed Reachy repo (original procedural robot only).

### Phase 1 — one licensed mesh + idle/working

- Extend `isAvatarTheme` / Django `#os-avatar-theme` / e2e with selectable `robot3d`.
- Header presence via lazy pose-player; rail posters.
- Custom `avatar_path` still wins.
- Fallback on GL failure / reduced motion.
- Honor LICENSE+NOTICE; extend root NOTICE if anything is vendored.
- Bake/vendor assets (inspiration STLs are gitignored).
- Still one persist key.

### Phase 2 — body/head combo catalog

- Validator + combo sub-key.
- Same `MiniPose` clips on every legal pair.
- No retargeter.

### Phase 3 — wire agent status / optional mood

- Map §6; optional `dance` not on every completion.
- Still no blocking `await` on clips.

---

## 10. Follow-up implement Issues (ready to file)

This agent’s `gh` is read-only, so these are **not** opened automatically. File them as children of #667 (or standalone after #667 closes) using the bodies below.

### 10.1 REQ-194 Phase 1

**Title:** REQ-194 Phase 1: `robot3d` theme + one licensed mesh (idle/working), chat never blocked

**Body:**

Parent: #667 (REQ-194). Graph: [ADR-008](https://github.com/matthewhand/open-swarm/blob/main/docs/adr/008-3d-robot-avatar-theme.md), [Reachy report](https://github.com/matthewhand/open-swarm/blob/main/docs/reports/reachy-3d-avatar-inspiration.md), inspiration [PR #10](https://github.com/matthewhand/reachy-subconscious-expression-app/pull/10).

**Intent:** Operators can opt into a 3D robot presence in the chat header without blocking send/paint.

**Success:**

1. `robot3d` is a real `swarm_avatar_theme` value (SPA + Django `#os-avatar-theme`). Default stays Blobs; Bee stays opt-in; custom `avatar_path` still wins.
2. One extractable pose-player, lazy-loaded on the header only. Playback is baked `MiniPose` sequences for `idle` + `working` — not AnimationMixer, not a live robot daemon, not an iframe of Glance.
3. Chat first paint / send succeeds if WebGL fails, `prefers-reduced-motion` is reduce, or the chunk is slow (2D fallback).
4. LICENSE+NOTICE of the chosen Reachy/Pollen/Three/URDF tag copied into root NOTICE. Meshes vendored or baked (inspiration STLs are gitignored). No secrets. No Neon. No FF `:8001`.

**Constraints:** One WebGL context. No Three on the main chat graph until selected. Coordinate the one-store key (closed #662). SaaS N/A.

### 10.2 REQ-194 Phase 2

**Title:** REQ-194 Phase 2: robot3d catalog — ≥2 bodies × ≥2 heads on one MiniPose rig

**Body:**

Parent: #667. Depends on Phase 1.

**Intent:** Swap body/head without rewriting clips.

**Success:**

1. Machine-checkable `Robot3dRigManifest` (report §2.5): socket offsets, rest height ± tolerance, required `idle`/`working`.
2. ≥2 bodies × ≥2 heads play the same baked MiniPose clips.
3. Combo persisted in `swarm_avatar_robot3d_combo` **only** while theme is `robot3d`.
4. Fail closed on illegal pairs. No runtime retargeter. No free-form mesh URLs.

### 10.3 REQ-194 Phase 3

**Title:** REQ-194 Phase 3: map chat/WS status to robot3d clips (idle/listen/working/error)

**Body:**

Parent: #667. Depends on Phase 1.

**Intent:** The header robot tracks agent state the way Blobs track idle/active — without the “WS open == active” false listen.

**Success:**

1. Implement `robot3dClipFromChat` (ADR-008 §6) or equivalent. `listen` requires composer focus / awaiting user, not merely WS `open`.
2. `working` from streaming or `tool_status` running. `error` from WS failed / tool error.
3. Optional `dance` is opt-in and never auto-loops on every completion.
4. Fire-and-forget; no new server mood SoT unless inbound `status` text is proven insufficient.

### 10.4 Related (already filed)

- **#540** prefs — migrate `swarm_avatar_theme` (+ combo sub-key) with other UI prefs; localStorage seed-once.
- **#662** one store — **closed**. Phase 1 must not reopen a second key.

---

## 11. Consequences

- Operators: optional 3D presence in the chat header (**Phases 1–3 live**); Blobs remain the default; bland, Bee, and custom 2D faces unchanged. The chat hero uses ONE WebGL context (ADR-008 §2 decision 2); every other AgentAvatar site shows the static SVG robot so a large rail cannot exhaust the browser's WebGL context limit.
- Implementers: no Three on the chat critical path; no N canvases; no combo UI before the MiniPose validator; no Glance iframe; no secrets; no Neon; no FF `:8001`.
- `/agents` leftover SVG packs stay leftover. Do not treat them as the 3D theme.
- This PR: Reachy report + this ADR + disabled picker stub. **Fixes #667** as **Phase 0 only**. Phases 1–3 are the §10 follow-ups.
