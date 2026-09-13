# README Demo Capture Instructions

> **Purpose:** Live recapture checklist for the four compact README demo slots (CLI agents, API agents, Remote agents / OpenMousBot, Combined team). No secrets, no LAN dumps, no `:8001` until Matthew GO for capture host.

---

## Slots

| Slot | File | Caption |
|------|------|---------|
| 1 | `assets/readme/cli-agents.gif` | "CLI agents — Grok / OpenCode / agy" |
| 2 | `assets/readme/api-agents.gif` | "API agents — OpenAI-compatible owned thread" |
| 3 | `assets/readme/remote-agents.gif` | "Remote agents — OpenMousBot" |
| 4 | `assets/readme/combined-team.gif` | "Combined team — CLI plus API plus OpenMousBot" |

---

## Capture Requirements

### General
- **Duration:** 15–20 seconds each
- **Resolution:** 1280×800 minimum (clean browser window, no OS chrome)
- **Format:** GIF (preferred) or mp4 + GIF fallback
- **Size target:** ≤500 KB per asset
- **No secrets** in frame (API keys, tokens, hostnames)
- **No live LAN** traffic visible — no private-range hosts (`192.168.*.*`, `10.*.*.*`, `172.16–31.*.*`) in address bars, terminals, or window titles
- **No `:8001`** — use local `docker compose` at `localhost:8000` unless capture host is explicitly approved. Do not show Neon or any cloud DB in frame

### Slot 1: CLI agents
**Command:** `uv run swarm-cli cli-agents --init --write --check-auth`
**Show:** Agent discovery, list, and `swarm-cli launch cli_agent --message "What CLIs can you see?"`

### Slot 2: API agents
**Command:** Start compose, then `curl -sf http://localhost:8000/v1/chat/completions -H "Authorization: Bearer $API_AUTH_TOKEN" -d '{"model": "codey", "messages": [{"role": "user", "content": "Explain this repo structure"}]}'`
**Show:** `/v1/models` listing, streaming response from blueprint-backed API agent

### Slot 3: Remote agents (OpenMousBot)
**Prerequisite:** OpenMousBot running locally (or mocked)
**Command:** `uv run swarm-cli remotes place <openmousbot_id>` → `swarm-cli launch openmousbot --message "What can you do?"`
**Show:** Remote catalog, add, list, and a short interaction

### Slot 4: Combined team
**Prerequisite:** Demo roster seeded (`scripts/seed_demo_agents.py --reset`)
**Command:** `/chat?team=demo` → send a task that triggers CLI → API → Remote handoff
**Show:** Multi-agent coordination across kinds — the API agent delegates to the CLI agent via agent-as-tool, then hands off to the remote OpenMousBot seat

---

## Recording Toolchain

```bash
# Preferred: Gifox (macOS) / Peek (Linux) / ShareX (Windows)
# Fallback: ffmpeg + ImageMagick

# Example (Linux, Peek):
peek --duration=20 --fps=10 --delay=2 --output=cli-agents.gif

# Compression (gifsicle, lossless):
gifsicle -O3 --lossy=30 input.gif -o output.gif

# Verify size:
ls -lh *.gif
```

---

## Post-Capture Checklist

- [ ] All four GIFs ≤ 500 KB each
- [ ] No secrets/API keys visible
- [ ] No LAN hostnames/IPs visible
- [ ] Captured on approved host only
- [ ] Assets placed in `assets/readme/`
- [ ] README references updated (auto if filenames match)
- [ ] Commit with message: `docs(readme): REQ-97b live demo GIFs for CLI/API/Remote/Combined slots`

---

## Regeneration from open-swarm Captures

Source captures live in open-swarm repo at:
- `docs/demo/captures/raw_*.txt` — raw terminal output
- `docs/demo/captures/scene{1,2,3,4}.txt` — staged scenes
- `scripts/render_demo_gif.py` — renderer

To regenerate:
```bash
cd /path/to/open-swarm
python scripts/render_demo_gif.py --input docs/demo/captures/scene1.txt --output /path/to/open-swarm-private/assets/readme/cli-agents.gif
python scripts/render_demo_gif.py --input docs/demo/captures/scene2.txt --output /path/to/open-swarm-private/assets/readme/api-agents.gif
python scripts/render_demo_gif.py --input docs/demo/captures/scene3.txt --output /path/to/open-swarm-private/assets/readme/remote-agents.gif
python scripts/render_demo_gif.py --input docs/demo/captures/scene4.txt --output /path/to/open-swarm-private/assets/readme/combined-team.gif
```

---

## CI Integration (Future)

Add to `.github/workflows/demo-recapture.yml`:
```yaml
name: Demo Recapture Check
on:
  workflow_dispatch:
  schedule:
    - cron: '0 0 * * 0'  # weekly
jobs:
  check-assets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify demo assets exist and are <500KB
        run: |
          for f in assets/readme/*.gif; do
            if [ ! -f "$f" ]; then
              echo "Missing: $f"
              exit 1
            fi
            size=$(stat -c%s "$f")
            if [ $size -gt 512000 ]; then
              echo "Too large: $f ($size bytes)"
              exit 1
            fi
          done
```

---

## Related Issues/PRs

- **REQ-97** (original posters): #456 / PR #869
- **REQ-97b** (live captures): This issue
- **REQ-136** (announce hero): #529 / PR #872
- **Demo agent seeding:** `scripts/seed_demo_agents.py`

---

## Notes

- SVG posters remain as fallbacks until live captures are available
- The announce-bridge.gif (REQ-136) is a separate 15–20s storyboard at `docs/assets/readme/announce-bridge.gif`
- Historical terminal loop `docs/demo/cli-and-api.gif` is NOT part of this set