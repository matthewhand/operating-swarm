# ADR-004: Virtualized infinite chat history

- **Status:** Proposed (look-only; no runtime change in this PR)
- **Date:** 2026-09-04
- **Issue:** [#575](https://github.com/matthewhand/open-swarm/issues/575) (REQ-163)
- **Related:** [ADR-001](../ADR-001-primary-ui.md) (SPA Chat only), [websocket chat](../websocket_chat.md), REQ-37 compact / summaries, REQ-143 centred status lines, REQ-117 collapsed code fences, REQ-149 capped overflow lists
- **Supersedes:** none
- **Numbering:** ADR-003 is reserved for desktop packaging (REQ-151 / #554, in-flight). This record is **004**.

**Decision:** **Primary `@tanstack/react-virtual` ≥ 3.14.** Fallback **`react-virtuoso` 4.x MIT `Virtuoso`**. Reject `react-window` / `react-virtualized` for Chat. Reject commercial `@virtuoso.dev/message-list`.

`@tanstack/react-query` is **already** in the SPA (`webui/frontend/package.json` `^5.8.4`). It is the data/cache layer, not a list virtualizer. Phase 2 wires `useInfiniteQuery` to the same thread the virtualizer windows. Do **not** pick Virtual *only* because Query is installed — they solve different problems. The pick is: headless attach to the existing DaisyUI `role="log"` scroller, plus published chat primitives (`anchorTo: 'end'`, `followOnAppend`, `scrollToEnd`, `isAtEnd`).

This ADR is Phase 0 of REQ-163. It does **not** add npm deps, change ChatPage, or paginate `GET /chat/thread/`.

No secrets are documented here.

---

## Issue quote (REQ-163)

**Intent:** Smooth scroll + windowed render + paginated/dynamic load of older messages.

**Success (phased):**

1. **Phase 0 (this Issue / look-only ADR):** Compare candidates (Virtuoso, TanStack Virtual, react-window, others) for: chat reverse-scroll, variable-height markdown bubbles, stick-to-bottom while streaming, jump-to-bottom, accessibility, DaisyUI/React 18 fit. Pick one primary + fallback. Note whether TanStack Query pairs for page fetching.
2. **Phase 1 Issue (spawn from ADR):** Implement virtualized transcript viewport on ChatPage.
3. **Phase 2 Issue:** Backend/API cursor pagination for older messages (if not already) wired to infinite load-on-scroll-up.
4. **Phase 3 (optional):** Virtualize other long lists (session picker) reusing the same lib.

**Constraints:** Don’t regress streaming / jump-to-bottom / centred info lines. No secrets. Fixes this Issue when Phase 0 ADR merges; link follow-up Issues.

Owner: Cursor look-only. CoS: Operating Swarm. Skeptic: recommendation quality.

---

## 1. Feasibility (what exists today)

Evidence is from `main` `9dbd9e6e` (2026-09-04). Chat is the SPA `/chat` surface (ADR-001). Django `templates/chat.html` is not the Grok-Bot transcript.

### 1.1 Transcript is a full-DOM map

`webui/frontend/src/pages/ChatPage.tsx` keeps every turn in `threads[threadKey]` and renders **all** `displayItems`:

- `displayItems.map` emits `ChatMessageBubble`, centred `.os-chat-status` (REQ-143), and nested `.chat-summary` (REQ-37).
- Heights are **variable and live**: GFM via `marked` (`ChatBubbleBody` / `renderSafeMarkdown`), tool-call popups, Compact blocks, collapsed fences (REQ-117).
- Empty state is a centred “Message {agent}” placeholder, not a bubble list.

There is **no** virtualizer in `webui/frontend/package.json`. Dependencies that matter:

| Package | Role today |
|---|---|
| `@tanstack/react-query` `^5.8.4` | Catalog/settings fetch (`blueprints`, `cli-agents`, `team-rosters`, remotes). **Not** thread history. |
| `react` `^18.2.0` | SPA runtime |
| `daisyui` `^5.0.0` | Chrome / utilities |
| `marked` `^15.0.12` | Safe markdown in bubbles |

Thread hydrate is a **manual** `useEffect` → `fetchAgentThread` (`webui/frontend/src/lib/agentChat.ts`), not `useQuery`.

### 1.2 Stick-to-bottom is a 48px pin + `scrollIntoView`

```text
pinnedToBottomRef (default true)
onScroll: distance-from-bottom < 48  →  pinned
useEffect([messages]): if pinned → listEndRef.scrollIntoView({ block: 'end' })
```

There is **no** jump-to-bottom control. If the user scrolls up, streaming must not yank them (`pinnedToBottomRef` already encodes that). “Jump-to-bottom” in Phase 1 is a **new** FAB/button when `!pinned`, calling the same end-align.

### 1.3 History API returns the whole transcript

`GET /chat/thread/?agent=&conversation_id=` (`src/swarm/views/chat_persist_views.py` `chat_thread`) loads JSON (`chat_store.load`) or Django `ChatMessage` rows and returns **`messages: [...]` with no `limit` / `cursor` / `next`**. PATCH edits by **integer `index`** into that full array. SPA keys hydrated rows as `` `hist-${index}-${message.role}` `` — unstable across prepend.

**Verdict:** Phase 1 can virtualize the in-memory list without an API change. Phase 2 must add cursor pagination **and** stop treating `index` as a UI-only pointer (keep the full list in Query cache for PATCH, or switch PATCH to a stable id).

### 1.4 Other lists (Phase 3 only)

REQ-149 already caps dense pickers with CSS overflow. Session picker / Settings catalogs are short compared to a multi-hour transcript. Do not virtualize them in Phase 1–2.

---

## 2. Comparison (2026-09-04 published packages)

Checked on the public npm registry: `@tanstack/react-virtual@3.14.10` (core `3.17.8`), `react-virtuoso@4.18.12`, `react-window@2.3.0`. Types for TanStack chat APIs were read from the published `virtual-core` package (`anchorTo`, `followOnAppend`, `isAtEnd`, `scrollToEnd`).

### 2.1 Scorecard (Chat requirements)

| Need | `@tanstack/react-virtual` ≥ 3.14 | `react-virtuoso` 4.x MIT `Virtuoso` | `react-window` 1.x / 2.x |
|---|---|---|---|
| Variable-height markdown | `measureElement` + `estimateSize`; remasures on stream/expand | Auto-measure; no size callback | v1 `VariableSizeList` + `resetAfterIndex`; v2 `useDynamicRowHeight` — still app-owned cache |
| Reverse infinite (prepend older) | Key-stable prepend; `anchorTo: 'end'` keeps the visible item | `firstItemIndex` (start large, decrement; must stay **positive**) | No first-class prepend; community offset hacks |
| Stick-to-bottom while **streaming** (last row grows) | `anchorTo: 'end'` applies size delta when pinned | `followOutput` when already at bottom | Height-change jank; the “less smooth” path |
| Jump-to-bottom | `scrollToEnd()` + `isAtEnd(threshold)` | `atBottomStateChange` + `scrollToIndex` | DIY `scrollToItem` |
| DaisyUI / existing scroller | **Headless** — attach to `scrollBoxRef` | Owns a scroller; `components.Scroller` can wrap | Owns a scroller |
| React 18 + TS | Yes (`peer` 16–19) | Yes | Yes |
| a11y (`role="log"`, `aria-live`) | Keep our node; add sr-only live region for latest chunk | Possible via custom Scroller; easier to drop attrs | Same risk as any wrapper |
| License | MIT | MIT for `react-virtuoso`. **`@virtuoso.dev/message-list` is commercial** | MIT |
| Query pairing | Same org; `useInfiniteQuery` pages → `useVirtualizer` items. No shared runtime | Works with Query the same way (data in, window out) | Same |

### 2.2 `@tanstack/react-virtual` (primary)

Headless hook. We keep ChatPage’s overflow box, `data-agent-kind`, `data-messages-editable`, and tests that query that node.

Chat primitives in **3.14+** (do not accept 3.13):

- `anchorTo: 'end'` — end-anchored list; prepend and last-item **resize** stay pinned.
- `followOnAppend` — follow new turns only when already at end (streaming + send).
- `scrollToEnd({ behavior })` — jump-to-bottom.
- `isAtEnd(threshold)` / `scrollEndThreshold` — replace the 48px pin.
- `getItemKey` — **required** for prepend stability (index keys break).

Fits DaisyUI because we do not replace the scroller. Fits React 18. Bundle is small vs Virtuoso.

**Caveat:** the public “Chat guide” URL 404’d at writing. Implement from published types + the TanStack blog/example, not a missing doc page. If streaming remasure or iOS rubber-band fights the new APIs, fall back to Virtuoso (below).

### 2.3 `react-virtuoso` MIT `Virtuoso` (fallback)

The long-standing “smooth” chat recipe:

- `followOutput` (`true` / `'smooth'` / `(isAtBottom) => …`)
- `firstItemIndex` + `startReached` for load-older
- `alignToBottom` / `initialTopMostItemIndex`
- `atBottomStateChange` for a FAB

Auto-measure is easier than rolling `measureElement`. The cost is an owned scroller (more ChatPage churn, more a11y wiring).

**Do not add `@virtuoso.dev/message-list`.** It is the dedicated chatbot widget and is **commercially licensed** (`VirtuosoMessageListLicense`). Operating Swarm stays MIT-only for Chat.

### 2.4 `react-window` / `react-virtualized` (reject for Chat)

`react-window` is the usual “less smooth” list: great for fixed rows, painful when the last markdown bubble grows every token. v2 `List` + `useDynamicRowHeight` still has no reverse-infinite / follow-output story. `react-virtualized` is the heavier parent — do not add.

### 2.5 Others (not candidates)

| Library | Why not |
|---|---|
| `@virtuoso.dev/message-list` | Commercial license |
| CSS `overflow-anchor` | Does not fix prepend or windowed DOM |
| `use-stick-to-bottom` | Complement, not a virtualizer |
| Home-grown `IntersectionObserver` | Reimplements the hard parts badly |

---

## 3. TanStack Query vs TanStack Virtual

| | `@tanstack/react-query` (already installed) | `@tanstack/react-virtual` (add in Phase 1) |
|---|---|---|
| Job | Fetch, cache, stale/revalidate | Window the DOM |
| Today | Blueprints / CLI / remotes / teams | — |
| Thread history | Manual `fetchAgentThread` in `useEffect` | — |
| Phase 1 | Unchanged (full thread still one GET) | Window `displayItems` |
| Phase 2 | `useInfiniteQuery` on cursor pages | Same virtualizer; `count` grows as pages prepend |

They compose; they do not replace each other. A Query page can hold 50 messages while the virtualizer mounts ~15 bubbles.

---

## 4. Recommendation

**Primary:** add `@tanstack/react-virtual` **≥ 3.14** (pin `^3.14.0` so chat APIs cannot resolve to 3.13).

**Fallback:** `react-virtuoso` 4.x `Virtuoso` (MIT only) if a Phase 1 spike shows streaming remasure or scroller-attach bugs.

**Why primary is Virtual, not Virtuoso:**

1. ChatPage already has a working, tested scroller. Headless attach is a smaller, safer delta than replacing it.
2. 3.14 chat APIs map 1:1 to stick-to-bottom, streaming growth, jump-to-bottom, and keyed prepend.
3. Phase 2 pagination is `useInfiniteQuery` — already the SPA data idiom.
4. FOSS: we never need the commercial Message List.

**Why not Virtual “because Query exists”:** Query does not window a list. If Virtual’s new chat APIs fail the spike, switching to Virtuoso does **not** require dropping Query.

**Skeptic (recommendation quality):**

- Virtuoso’s chat recipe is older and more documented; Virtual’s chat APIs are new. The fallback exists for that reason.
- Virtualization removes off-screen nodes: in-page Find will miss them; `aria-live` on the log may not announce if the live node is unmounted. Phase 1 keeps a **sr-only live region** for the latest assistant chunk (connection status already has one).
- REQ-117 fence expand and tool popups must remasure (`measureElement` / Virtuoso auto-resize).
- Do not virtualize until it pays: `align`/empty state stays for 0 items; overscan ~6–8 rows.

---

## 5. Phase 1–2 implement Issues (file after merge)

These are ready-to-file bodies. This look-only PR cannot open them. Link the new numbers here when filed.

### Phase 1 — Virtualize ChatPage transcript

**Title:** `REQ-163 Phase 1: Virtualize ChatPage transcript (@tanstack/react-virtual)`

**Depends on:** this ADR merged.

**Intent:** Window the in-memory transcript so large restored threads do not mount every bubble.

**Success:**

1. Add `@tanstack/react-virtual` `^3.14.0` to `webui/frontend` (no other new UI libs).
2. Extract a `ChatTranscript` (or equivalent) that virtualizes `displayItems` (bubbles, `.os-chat-status`, `.chat-summary`). Keep WS / hydrate / edit on ChatPage.
3. Attach the virtualizer to the existing scroll box (`role="log"`, `aria-live`, `data-agent-kind`, `data-messages-editable`).
4. `anchorTo: 'end'` + `followOnAppend` while pinned; do **not** yank a user who scrolled up (preserve today’s 48px pin semantics).
5. **Jump-to-bottom** control when `!isAtEnd`; `scrollToEnd()`.
6. Stable item keys (stop `` `hist-${index}-${role}` ``). Streaming last row remasures.
7. No regression: streaming, REQ-143 centred status, REQ-37 summaries, in-place edit, Compact, empty state.
8. sr-only live region for the latest assistant text.
9. Vitest: existing ChatPage tests stay green (mock `scrollIntoView` / virtualizer as needed). Optional Playwright: 200 fake turns → bounded mounted bubbles + jump-to-bottom.
10. **No** `GET /chat/thread/` pagination in this Issue.

**Constraints:** DaisyUI/React 18. No commercial Virtuoso package. No secrets. If the 3.14 APIs fail a spike, switch to fallback `react-virtuoso` and note it on the Issue.

**Out of scope:** backend cursor, session picker virtualization, many-agents-at-once.

### Phase 2 — Cursor pagination + reverse infinite load

**Title:** `REQ-163 Phase 2: Cursor-paginate GET /chat/thread/ + load-older on scroll-up`

**Depends on:** Phase 1 merged.

**Intent:** Dynamically load older turns instead of hydrating the entire JSON/DB transcript into the first paint.

**Success:**

1. `GET /chat/thread/` accepts `limit` + cursor (`before` timestamp or `before_index`). Default response is the **newest** page. Payload includes `has_older` / `next_before` (names TBD, documented on the Issue).
2. Existing callers with no cursor still get a bounded first page (pick a default e.g. 100) — do not silently truncate without `has_older`.
3. SPA: `useInfiniteQuery` (`@tanstack/react-query`, already installed) with `queryKey: ['chat-thread', agent, conversationId]`. `fetchNextPage` = older page.
4. Virtualizer: prepend pages with **stable keys**; `anchorTo: 'end'` so the viewport does not jump. Trigger older-load near the top (intersection or `startIndex === 0`).
5. **PATCH edit:** today’s `index` is against the **full** stored array (`chat_persist_views.chat_thread`). Either (a) keep the full message list in Query cache (DOM stays windowed) so `index` remains valid, or (b) add a stable message id and PATCH by id. Do not PATCH a window-relative index.
6. Compact / summaries (REQ-37) `span.start` / `span.end` stay conversation-absolute.
7. Tests: API pagination + SPA infinite-query prepend without scroll jump; edit still persists.

**Constraints:** No Neon. JSON store + Django `ChatMessage` both honour the cursor. No secrets.

**Out of scope:** Phase 3 other lists; changing WS streaming.

### Phase 3 (optional, not an Issue yet)

Reuse the same virtualizer for session picker / Settings catalogs **only if** a list regularly exceeds ~200 rows. REQ-149 overflow caps cover today’s UI.

---

## 6. Phase 1 sketch (implement later — not this PR)

```tsx
// Illustrative — do not land in this look-only PR.
const parentRef = scrollBoxRef
const virtualizer = useVirtualizer({
  count: displayItems.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 96,
  getItemKey: (index) => keyOf(displayItems[index]),
  measureElement: (el) => el.getBoundingClientRect().height,
  anchorTo: 'end',
  followOnAppend: true,
  scrollEndThreshold: 48,
  overscan: 8,
})
```

Jump-to-bottom: `virtualizer.scrollToEnd({ behavior: 'smooth' })` when `!virtualizer.isAtEnd(48)`.

---

## 7. Consequences

- Phase 0 closes #575 (this ADR).
- Phase 1–2 stay parked until Issues are filed and scheduled.
- Chat Find-in-page will not search unmounted bubbles (document in Phase 1 UX copy if needed).
- Bundle: one MIT virtualizer in the SPA; Query stays.

## 8. Rejected alternatives

| Alt | Why not |
|---|---|
| Virtuoso MIT as primary | Better docs; worse fit for the existing scroller / a11y attrs. Kept as fallback. |
| `@virtuoso.dev/message-list` | Commercial license. |
| `react-window` | Weak streaming + reverse-scroll. |
| Query-only (no virtualizer) | Cache ≠ DOM window. |
| Paginate API before virtualizing | First paint still mounts every returned bubble; window first. |
| Home-grown window | Reimplements prepend/follow poorly. |
