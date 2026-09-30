### Inference profiles — blueprint intent → backend (live)

A blueprint declares *what kind of thinking it wants* (intelligence / speed /
cost, each a 0–1 priority) instead of naming a model. Operating Swarm maps that to the
best-matching installed CLI by each backend's capability traits (see
`swarm.core.inference_profile`).

![intent to backend routing](../screenshots/skills/06-inference-profile.png)

**Live result** (`scripts/demo_inference_profile.py`, against the host's
installed CLIs using the default `CLI_TRAITS`):

| Desired profile | Resolved CLI | Why |
|---|---|---|
| `{intelligence: 1.0}` | **claude** | closest on the one axis asked for (0.95) |
| `{speed: 1.0, cost: 1.0}` | **gemini** | closest on speed (0.92) + cheapness (0.90) |
| `{0.6, 0.6, 0.6}` (balanced) | **opencode** | the genuine all-rounder (0.55/0.65/0.75 is nearest 0.6/0.6/0.6) |

All three resolved CLIs then answered the live prompt correctly (3/3).

#### How matching works

Selection is **distance-from-ideal**: the profile is a *target* and the backend
whose traits are closest (Euclidean distance) wins, measured **only over the
axes the blueprint specifies** — unspecified axes are "don't care" and never
penalize. So `{intelligence: 1.0}` picks the smartest backend regardless of how
fast or cheap it is, and "balanced" picks a true generalist (opencode here)
rather than whoever has the highest total capability. Tune the per-backend
`traits` in config to match your own plans/models.
