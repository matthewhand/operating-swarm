# REQ-67 — Role chrome is the badge only

**Status:** this PR — in flight (#396)

> **Quoted issue (https://github.com/matthewhand/open-swarm/issues/396):**
>
> **Intent:** Roles are already marked by the role badge. Do not also colour the agent row (fill or border). That is too much chrome.
>
> **Success:**
> 1. Rail / sidepane agent rows have **no** role-based background fill, left-border accent, or outline. Default / support / safety (gate) / skeptic / CoS rows share the same row chrome as an ordinary agent.
> 2. The **role badge** (chip) remains the only role colour. Badge click behaviour (#356 / PR 370) is unchanged.
> 3. Selected / hover / hidden / working states stay as they are today — they are not role colours.
> 4. Tests: role rows do not use `os-agent-role-*` fill/border on the row (or equivalent classes removed); badge still present for those roles.
>
> **Constraints:**
> - Distinct from #356 (badge click pane) and #344. Do not fold into 344.
> - DaisyUI 5, React 18.
> - GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
> - No Neon. No secrets.
> - One Cursor cloud. PR must say `Fixes` this issue.
>
> **Owner:** open-swarm engineer + Cursor cloud. CoS: Open Swarm. Skeptic after the PR (text-only PASS/FAIL).

## Intent

Roles are already marked by the role badge. Do not also colour the agent row
(fill or border). That is too much chrome.

## Success

See the quoted issue above.

## Constraints

- Distinct from #356 (badge click pane) and #344. Do not fold into 344.
- DaisyUI 5, React 18.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- No Neon. No secrets.

## Owner

- CoS transcribes
- cloud implements (this PR)
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
