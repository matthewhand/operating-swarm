# QA reports

Look-only audits below are **no runtime product change**. Issue #136 is an
implementation checklist (kind-chat e2e). Issue #157 is the shared fleet
Success checklist (docs only), not a look-only audit.

| Surface | REQ / Issue | Report |
|---------|-------------|--------|
| **Fleet patterns (shared Success: remote prove, same-origin, health, herdr, hide, infra CI)** | private #157 | [FLEET-PATTERNS.md](./FLEET-PATTERNS.md) |
| **Kind-chat e2e (auth + CLI/API/Blueprint/Team)** | private #136 | [ISSUE-136-kind-chat-e2e.md](./ISSUE-136-kind-chat-e2e.md) |
| **`software_dev` workdir / Runner path** | private #150 | [ISSUE-150-software-dev-runner.md](./ISSUE-150-software-dev-runner.md) |
| **`software_dev` remote workdir (SSH)** | private #148 | [ISSUE-148-software-dev-remote-workdir.md](./ISSUE-148-software-dev-remote-workdir.md) |
| **Fleet patterns (OpenSSH argv note)** | private #157 | [ISSUE-157-fleet-patterns.md](./ISSUE-157-fleet-patterns.md) (pointer only; does not close #157) |
| **B — left rail / agents / favourites / hidden / blueprints-as-agents** | REQ-171 [#596](https://github.com/matthewhand/open-swarm/issues/596), coordinates [#595](https://github.com/matthewhand/open-swarm/issues/595) ([`:8001` confirm](https://github.com/matthewhand/open-swarm/issues/595#issuecomment-5537343790)) | [REQ-171-surface-b-rail-agents.md](./REQ-171-surface-b-rail-agents.md) |
| **Final skeptic sweep — Matthew asks vs delivered** | REQ-126 [#516](https://github.com/matthewhand/open-swarm/issues/516) | [REQ-126-final-skeptic-sweep.md](./REQ-126-final-skeptic-sweep.md) |

Umbrella [#596](https://github.com/matthewhand/open-swarm/issues/596) also asks for surfaces A (chat/composer/session) and C (CLI/API/remote harness). Those are sibling look-only reports, not this file.

## Requirement + lock specs (shipped features)

These are **feature requirement specs**, retro-fitted on top of shipped fixes:
requirements + acceptance criteria + a `tests/unit/test_req###_*.py`
source-lock so the spec cannot silently regress.

| REQ | Surface | Spec | Lock test |
|-----|---------|------|-----------|
| REQ-844 | Speech-bubble tails symmetric (private #166) | [REQ-844-speech-bubble-symmetry.md](./REQ-844-speech-bubble-symmetry.md) | `tests/unit/test_req844_speech_bubble_symmetry.py` |
| REQ-845 | Composer never locks / offline queue (private #167) | [REQ-845-composer-resilience.md](./REQ-845-composer-resilience.md) | `tests/unit/test_req845_composer_resilience.py` |
| REQ-846 | Team dropdown defaults CoS / first (private #169) | [REQ-846-team-default-session.md](./REQ-846-team-default-session.md) | `tests/unit/test_req846_team_default_session.py` |
| REQ-847 | Stale-hidden reconciliation (private #170) | [REQ-847-hidden-reconciliation.md](./REQ-847-hidden-reconciliation.md) | `tests/unit/test_req847_hidden_reconciliation.py` |
| REQ-848 | Right-click rail → new section (private #173) | [REQ-848-rail-pane-menu.md](./REQ-848-rail-pane-menu.md) | `tests/unit/test_req848_rail_pane_menu.py` |
| REQ-801 | Bee avatar pack incl. #171 extension | [REQ-801-bee-avatar-pack.md](./REQ-801-bee-avatar-pack.md) | `tests/unit/test_req801_bee_avatar_theme.py` |
