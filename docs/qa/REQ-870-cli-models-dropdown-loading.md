# REQ-870 — Ensure All CLI Agents List Models with Clear "Loading..." State (#260)

> Guarantees every CLI agent displays models in the model dropdown, and provides an immediate, prominent "Loading..." indicator when the dropdown is clicked while lazy model loading is in flight.

**Issue:** [#260](https://github.com/matthewhand/open-swarm-private/issues/260)

---

## 1. Context & Motivation

When routing tasks through CLI agents, operators need to select specific models (e.g. fast/lightweight vs deep reasoning tiers).
Currently:
1. **Missing Models**: Certain CLIs (such as `qwen` and `omp`) do not document entries in `LIST_MODELS` or `CLI_MODELS`, leading to an empty model list or a "No models discovered" warning.
2. **Missing Loading Feedback**: When models are lazy-loaded upon opening the dropdown, the UI does not always provide an immediate, clear "Loading..." feedback signal. As a result, the user cannot tell whether the dropdown is genuinely empty or if results are about to appear.

---

## 2. Requirements

### 2.1 Complete Model Availability for All CLIs
1. **Catalog Preset Fallbacks**:
   - In `src/swarm/core/cli_catalog.py`:
     - Add presets for all catalogued CLIs in `CLI_MODELS`:
       - `qwen`: `["qwen2.5-coder:32b", "qwen2.5-coder:7b", "qwen2.5:72b"]`
       - `omp`: `["litellm/orchestration", "gemini-2.5-flash", "claude-3-5-sonnet"]`
       - Ensure `grok`, `agy`, `gemini`, `claude`, `opencode`, and `codex` presets are maintained.
2. **Graceful Fallback on Probe**:
   - In `src/swarm/core/cli_models.py` (`probe_list_models`), if a live subprocess probe fails, times out, or is absent for a CLI, fall back to returning the known `CLI_MODELS` presets rather than returning an empty list.

### 2.2 Immediate Visual Loading Feedback on Dropdown Click
1. **Prominent "Loading..." Indicator**:
   - In `webui/frontend/src/components/NavbarRoutingPicker.tsx`:
     - When the model dropdown is open or focused and the models query is in-flight (`isFetching` or `isLoading`):
       - Render a prominent **"Loading..."** item with a loading spinner or animated dots.
       - Prevent showing "No options" or "No models discovered" until the query finishes with an empty result.
2. **Smooth Population**:
   - Once the query resolves, the "Loading..." indicator seamlessly transitions into the populated list of model options.

---

## 3. Acceptance Criteria

- [ ] Every CLI agent in the dropdown displays a list of selectable models (via live probe or verified catalog presets).
- [ ] Clicking on the model dropdown while a probe is in-flight displays an explicit **"Loading..."** state.
- [ ] No premature "No options" or "No models discovered" warning flashes while models are loading.
- [ ] `qwen` and `omp` have default models listed out of the box.
- [ ] **Tests**:
  - [ ] Python test in `tests/core/test_cli_models.py` asserting fallback presets for all catalog CLIs.
  - [ ] Vitest test in `webui/frontend/src/components/__tests__/NavbarRoutingPicker.test.tsx` asserting the "Loading..." state renders while `isFetching` is true.

---

## 4. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `src/swarm/core/cli_catalog.py` | CLI catalog presets | Add known default models for `qwen`, `omp`, and all catalogued CLIs. |
| `src/swarm/core/cli_models.py` | Models probe service | Fall back to catalog presets when live probe returns empty. |
| `webui/frontend/src/components/NavbarRoutingPicker.tsx` | Navbar routing picker UI | Render clear "Loading..." state during in-flight model queries. |
