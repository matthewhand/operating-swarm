# REQ-865 — Responsive Navbar Element Prioritization (#255)

> Defines the element prioritization and degradation hierarchy for the top chat navbar when horizontal viewport width narrows (desktop → tablet → mobile). Sidepane expander buttons and essential action controls (dropdowns, session switcher, computer control, light/dark toggle) remain visible, while the agent avatar is prioritized and the agent name label fades out to the right.

**Issue:** [#255](https://github.com/matthewhand/open-swarm-private/issues/255)

---

## 1. Context & Motivation

On narrower screens (tablets ~768px down to smartphones ~375px), horizontal navbar real estate in `ChatPage.tsx` becomes constrained. Without an explicit layout hierarchy, interactive controls can wrap, trigger unwanted horizontal scrollbars, or push critical controls off-screen.

Users require:
1. **Immediate access to navigation & drawers**: Sidepane expanders must never disappear.
2. **Access to core action controls**: Routing dropdowns, session switchers, computer control, and theme toggles must stay visible and clickable.
3. **Graceful agent details handling**: The agent avatar must stay visible, while the agent name text absorbs the width compression by gracefully **fading out to the right** rather than wrapping or causing overflow.

---

## 2. Element Prioritization Hierarchy

| Priority Level | Elements | Responsive Behavior |
| :--- | :--- | :--- |
| **P1 (Top Priority — Never Obscured)** | **Sidepane expander buttons**<br>• Left rail toggle (`PanelLeft` button on `narrow`)<br>• Right drawer toggles | `shrink-0`; permanently visible across all viewport breakpoints. |
| **P2 (Core Action Controls)** | **Right-hand interactive cluster**:<br>• Routing picker dropdowns (`NavbarRoutingPicker`)<br>• Session switcher (`CliSessionSwitcher`)<br>• Computer control button (`ComputerControlStub`)<br>• Light/Dark theme toggle (`ThemeToggle`)<br>• Settings button | Keep visible; `flex items-center shrink-0 gap-1 sm:gap-2`. Padding/gap scales down gracefully on mobile (`gap-1`). |
| **P3 (Primary Identity)** | **Agent Icon / Avatar** (`AgentAvatar`) | `shrink-0`; permanently visible in identity card. |
| **P4 (Flexible Width Absorber)** | **Agent Name Label** (`{selectedAgentName}`) | `min-w-0 flex-1`; smoothly shrinks with a **CSS fade-out gradient to the right**. |
| **P5 (Secondary / Collapsible)** | • Edit pencil button (`.os-navbar-edit-btn`)<br>• Context token usage meter (`[data-testid="token-meter-button"]`) | On tablet/mobile (`< 640px`):<br>• Token meter hides or collapses to icon-only (`hidden sm:flex`).<br>• Edit pencil hides on mobile or reveals on tap/hover. |

---

## 3. Visual & Technical Implementation Specifications

### 3.1 Agent Name Label Fade-Out Gradient
Instead of an abrupt ellipsis cut (`truncate`) or text wrapping, the agent name button in `.os-navbar-identity-card` must use a CSS mask gradient fading to transparent at the right edge:

```css
/* Fade-out gradient for navbar identity title */
.os-navbar-identity-label {
  display: inline-block;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  /* Smooth 1.5rem fade to transparent at the right boundary */
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%);
  mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%);
}
```

### 3.2 Flex Containment & Gap Compression
- `.os-chat-header`:
  - `display: flex; align-items: center; justify-content: space-between; overflow: hidden;`
  - Gap adjusts responsively: `gap-1.5 sm:gap-3` (preventing spacing from wasting room).
- Left Identity Container (`.os-chat-header__identity`):
  - `flex: 1 1 auto; min-width: 0; max-width: max-content;`
  - Allows the identity cluster to yield width to the right-hand controls when horizontal space is tight.
- Right Control Container:
  - `flex: 0 0 auto; shrink-0;`
  - Prevents dropdowns, session switcher, computer control, and theme toggle from being clipped or pushed out.

---

## 4. Acceptance Criteria

- [ ] **Sidepane Expanders (P1)**:
  - [ ] On mobile/tablet viewport (`narrow`), the left sidebar toggle button is always visible (`shrink-0`) and clickable.
  - [ ] Right-hand drawer triggers remain visible.
- [ ] **Action Controls (P2)**:
  - [ ] Routing dropdowns (`NavbarRoutingPicker`), `CliSessionSwitcher`, `ComputerControlStub`, and `ThemeToggle` remain visible on screen widths down to 360px.
  - [ ] The header does not cause horizontal scrollbar or line-wrapping.
- [ ] **Agent Icon (P3)**:
  - [ ] The agent avatar (`AgentAvatar`) remains visible and unclipped (`shrink-0`).
- [ ] **Fading Agent Name Label (P4)**:
  - [ ] When screen width shrinks, the agent name label compresses and displays a smooth fade-out gradient to the right.
  - [ ] The text does not wrap to a second line.
- [ ] **Secondary Elements (P5)**:
  - [ ] Token meter hides on small screens (`hidden sm:flex`).
- [ ] **Tests**:
  - [ ] Vitest component tests in `webui/frontend/src/pages/__tests__/ChatPage.navbarResponsive.test.tsx` verifying element visibility and CSS classes under narrow viewport conditions.

---

## 5. Key File Locations

| File | Component / Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/pages/ChatPage.tsx` | Top navbar (`os-chat-header`) | Apply `shrink-0` to controls cluster, responsive `gap-1 sm:gap-2`, `hidden sm:flex` to token meter, and apply `.os-navbar-identity-label` to agent title. |
| `webui/frontend/src/index.css` | Global styling | Add `.os-navbar-identity-label` with `mask-image: linear-gradient(to right, ...)` and responsive header rules. |
