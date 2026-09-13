# REQ-801 — Bee avatar pack (theme + variant + accent + accessory)

> The `bee` avatar theme renders deterministic, geometric bees from an agent id.
> Variant, accent, and accessory are hashed from the id (stable per agent).
> All geometry reuses the shipped geometric WebUI mark (`assets/brand/webui-geometric.svg`,
> #778) — no third art style, no marketing fanfare marks in the rail.

**Extension (#171):** the original pack shipped **2 variants × 3 gold
accents** with no accessories; it looked samey across a roster. This spec
extends it to **6 variants × 6 accents + a 4-option accessory layer** so a rail
of bees is visibly distinct per agent while staying on-brand.

**Issues:** [#801](https://github.com/matthewhand/open-swarm/issues/801) (original),
[#171](https://github.com/matthewhand/open-swarm/issues/171) (extension).

**Note (2026-09-10):** the `restore/runtime` rebase had clobbered #820's factory
default (`blobs`) with `bee` in `avatarTheme.ts`. Restored #820: `defaultAvatarTheme()`
returns `blobs`, Bee stays opt-in, and the Settings picker is the REQ-828
installed-families checkbox list (labels rendered from `AVATAR_THEME_FAMILIES`).

## Requirement

1. **Theme** — `bee` is an opt-in avatar theme (`avatarTheme.ts`); default
   remains `blobs`. Custom avatar still wins over bee.
2. **Variants** (`BEE_VARIANTS`, hashed per agent, deterministic):
   - `side-on` — profile bee (head + striped abdomen + googly eyes), existing.
   - `face-only` — zoomed geometric head, existing.
   - `flying` — profile with spread wings and a flight trail.
   - `honeycell` — face framed by a honeycomb cell.
   - `bumblebee` — round, chunky body, no separated head ring.
   - `top-down` — plan view: head, thorax, striped abdomen, four wings.
3. **Accents** (`BEE_ACCENTS`, hashed per agent): the 3 shipped golds plus 3
   honey/amber/bronze additions (6 total), all from the amber brand family.
4. **Accessories** (`BeeAccessory`, hashed per agent, rendered only on
   face-visible variants): `none` | `blush` | `brow` | `sparkle`, drawn in the
   accent colour, each tagged with `os-bee-accessory os-bee-accessory--<name>`.
5. **Chrome contract** — the `<svg>` exposes `data-bee-variant`,
   `data-bee-accent`, `data-bee-accessory`, `data-bee-gaze`, `data-googly`
   so tests and CSS can target the pack; googly pupil wander + reduced-motion
   CSS remain.

## Acceptance criteria (lock test `tests/unit/test_req801_bee_avatar_theme.py`)

- [x] `BEE_VARIANTS` contains all 6 variants; every spec's variant ∈ the enum.
- [x] `BEE_ACCENTS` contains 6 accents; every spec's accent ∈ the enum.
- [x] `beeSpecForAgent` is deterministic per id and varies across ids.
- [x] `BeeAvatar.tsx` renders per variant with `data-bee-variant={spec.variant}`,
      and each new variant has a named renderer (`FlyingBee`, `HoneycellBee`,
      `BumbleBee`, `TopDownBee`).
- [x] Accessory layer renders `os-bee-accessory` with the variant class and the
      svg carries `data-bee-accessory`.
- [x] Geometric head path from `webui-geometric.svg` is reused; no `marketing-*`
      art in the rail.

## Locked sources

| File | Role |
|------|------|
| `webui/frontend/src/lib/beeAvatar.ts` | `BEE_VARIANTS` / `BEE_ACCENTS` / `BeeAccessory` / `beeSpecForAgent` |
| `webui/frontend/src/components/BeeAvatar.tsx` | variant renderers + accessory layer |
| `webui/frontend/src/lib/avatarTheme.ts` | `bee` opt-in enum |
| `webui/frontend/src/lib/__tests__/beeAvatar.test.ts` | Behaviour spec of record (vitest) |

## Test map

- `tests/unit/test_req801_bee_avatar_theme.py` — source-lock (this REQ).
- `webui/frontend/src/lib/__tests__/beeAvatar.test.ts` — spec determinism, full
  variant coverage, accessory coverage.