# Hosting the mocked demo

Issue [#439](https://github.com/matthewhand/open-swarm-private/issues/439).
Spec: [REQ-882](./qa/REQ-882-demo-site-mocked-inference.md) / [#279](https://github.com/matthewhand/open-swarm-private/issues/279).

This is a **recorded** Operating Swarm: scripted chat turns, no API keys, no
host CLIs, no LAN remotes. Replies are samples.

## Local (no cloud)

```bash
make demo-build          # VITE_DEMO_MODE SPA → webui/frontend/dist
make demo-serve          # http://127.0.0.1:8765/  and  /chat
# or: python scripts/serve_demo_site.py --port 8765
```

`make demo-serve` refuses to start if `dist/index.html` is missing.

## Drop on any static host

After `make demo-build`, publish `webui/frontend/dist/`:

| Host | How |
|---|---|
| nginx | `root` that directory; `try_files $uri $uri/ /index.html;` |
| Cloudflare Pages / GitHub Pages | upload the `dist` folder; SPA fallback to `index.html` |
| Python anywhere | `python scripts/serve_demo_site.py --port 8080 --dist webui/frontend/dist` |

Do **not** point this dist at a live Django API. The demo build stubs
`fetch` and `WebSocket` in-page.

## Fly / Pages publish (optional)

`make demo-deploy` still **skips** without Fly or Pages credentials (CI stays
green). When you have tokens:

```bash
FLY_API_TOKEN=… make demo-deploy          # fly.demo.toml, SWARM_DEMO_MODE=1
# or CLOUDFLARE_API_TOKEN=… / GITHUB_PAGES_DEPLOY=1
```

## Honesty

The SPA demo banner states that inference is mocked. Do not advertise the
hosted URL as a live multi-agent cluster.
