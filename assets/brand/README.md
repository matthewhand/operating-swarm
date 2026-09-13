# Open Swarm brand marks

Three approved looks from draft [#537](https://github.com/matthewhand/open-swarm/pull/537)
tasters, wired by surface ([#768](https://github.com/matthewhand/open-swarm/issues/768)).
Do not collapse them into one winner.

| Surface | Master | Source taster |
|---|---|---|
| Favicon / PWA / small chrome | `favicon-minimal.svg` | `tasters/option3-minimal-brand-mark.jpg` |
| WebUI navbar / splash / settings | `webui-geometric.svg` | `tasters/option1-geometric-bee.jpg` |
| Marketing / website fanfare | `marketing-cyber-swarm.svg` (+ `.png`) | `tasters/option2-cyber-swarm-bee.jpg` |

The README hero photo (`assets/images/openswarm-project-image.jpg`) stays the
photo banner. It is not the product mark.

No third-party stock bee. PR #487 clipart lives under `retired/` and is not
wired.

## Masters

| File | Use |
|---|---|
| `favicon-minimal.svg` | Colour minimal mark (gold `#EBA222` / black `#111111` on slate `#17212A`). Tab, PWA, Pinokio. |
| `favicon-minimal-mono.svg` | Single colour via `currentColor`. Masks / light UI. |
| `favicon-minimal-mono-on-dark.svg` | White bee on `#111111`. Dark chrome. |
| `webui-geometric.svg` | Geometric honeycomb bee on charcoal `#1D2226`. Operator navbar, login splash, Settings sheet. |
| `webui-geometric-mono.svg` | `currentColor` silhouette of the geometric bee. |
| `project-banner.svg` | README / project banner: logo surrounded by worker bees with CLI, API, Remote, Team, Blueprint bubbles. |
| `project-banner.png` | Raster of the project banner (1280×560). |
| `marketing-cyber-swarm.svg` | Faceted amber fanfare mark. Website / launch art. |
| `marketing-cyber-swarm.png` | Raster companion (SVG export). Photoreal taster stays in `tasters/`. |

Regenerate rasters (optional tools, not runtime deps):

```bash
uv run --with pillow --with cairosvg python scripts/export_brand_icons.py
```

That also copies the serving set into `webui/frontend/public/` and replaces
`assets/images/favicon.ico` with the minimal multi-size ICO.

## Raster set (checked in)

**Minimal colour (wired in the tab / Apple / PWA):**

| File | Size | Notes |
|---|---|---|
| `favicon.ico` | 16 / 32 / 48 | Minimal mark. Root `/favicon.ico`. |
| `favicon-16.png` | 16 | Minimal. |
| `favicon-32.png` | 32 | Minimal. |
| `favicon-48.png` | 48 | Minimal; baked into the ICO. |
| `apple-touch-icon.png` | 180 | Minimal (rounded slate tile). |
| `apple-touch-icon-120.png` | 120 | Extra size. |
| `apple-touch-icon-152.png` | 152 | Extra size. |
| `icon-192.png` | 192 | PWA `any`. |
| `icon-512.png` | 512 | PWA `any`. |

**Geometric (WebUI chrome):**

| File | Size | Notes |
|---|---|---|
| `webui-geometric-32.png` / `64` / `128` / `256` | those sizes | Navbar / splash rasters. SVG is preferred. |

**Mono (not every size is wired in `<head>`):**

| File | Size | Notes |
|---|---|---|
| `favicon-minimal-mono-16.png` / `32` / `192` / `512` | those sizes | Black silhouette, transparent. |
| `favicon-minimal-mono-on-dark-16.png` / `32` / `192` / `512` | those sizes | White bee on `#111111`. |

Tab favicon, `apple-touch-icon`, and the web manifest use the **minimal** mark.
Geometric is in-app chrome only. Cyber-swarm is marketing only.

## Wiring

- SPA `webui/frontend/index.html` → `/favicon.ico`, `/favicon-16.png`,
  `/favicon-32.png`, `/apple-touch-icon.png`, `/manifest.json` (minimal)
- SPA Settings sheet + public copies → `/webui-geometric.svg`
- Django `base.html` navbar + login splash → `{% static 'brand/webui-geometric.svg' %}`
- Django `brand_icons.html` heads → `{% static 'brand/favicon…' %}` (minimal)
- Django also serves the same files at the root URLs above so the SPA and
  default browser `/favicon.ico` requests are not the SPA `index.html`
- Pinokio launcher `icon` points at `favicon-minimal.svg`
- Marketing slot: `marketing-cyber-swarm.svg` / `.png`. The public website
  lives outside this repo; point launch pages at these files.

## Tasters

Source renders for the three looks: [`tasters/`](tasters/). Decision record:
[#537](https://github.com/matthewhand/open-swarm/pull/537).
