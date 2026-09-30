# Operating Swarm Troubleshooting Guide

Having issues with Operating Swarm? Here are some common problems and solutions.

---

## 1. CLI or Blueprint Not Found
- Ensure `~/.local/bin` is in your `$PATH`.
- Try running the command directly: `~/.local/bin/codey`

## 2. API Errors or LLM Not Working
- Double-check your API key in `~/.config/swarm/.env`.
- Make sure your network connection is active.
- If using a custom endpoint, verify the URL and credentials.

## 3. Configuration Issues
- Review your config file: `~/.config/swarm/swarm_config.json`.
  - Look for typos, missing fields, or invalid JSON.
  - You can edit with any text editor (e.g., `nano`, `vim`, `code`).
- If you continue to have issues, **as a last resort** you can delete the config file:
  ```bash
  rm ~/.config/swarm/swarm_config.json
  ```
  - The system will regenerate a default config on next run, but you will need to reconfigure agents and LLMs.

### Server crash-loops on startup with `ImproperlyConfigured`
In production (`DJANGO_DEBUG` unset/false) the server **refuses to boot** until a
couple of env vars are set, exiting with e.g.:

```
django.core.exceptions.ImproperlyConfigured: DJANGO_SECRET_KEY environment
variable is required when DJANGO_DEBUG is not enabled (production).
```

Fix — set the required production vars (or enable dev mode):
- `DJANGO_SECRET_KEY` — any strong random string (`python -c "import secrets;print(secrets.token_hex(32))"`).
- `DJANGO_ALLOWED_HOSTS` — comma-separated hostnames (e.g. `example.com,www.example.com`).
- …or for local development only, set `DJANGO_DEBUG=true` to use insecure dev defaults.

The error names exactly which var is missing; it surfaces them one at a time, so
set both. See [CONFIGURATION.md](../CONFIGURATION.md) → Environment Variables.

### Startup warning: “API authentication is OFF”
In debug (or with `SWARM_ALLOW_NO_AUTH`) and no `API_AUTH_TOKEN` /
`SWARM_API_KEY`, the server can boot with the API open. Serving logs a warning
from `SwarmConfig._warn_if_api_auth_disabled`. Fine for local development — set a
token before binding to a network-facing interface.

## 4. Logs and Debugging
- Check logs at `~/.swarm/swarm.log` for error messages.
- Run CLI commands with increased verbosity if supported (e.g., `--verbose`).

## 5. Getting Help
- Use `swarm-cli --help` or `<blueprint> --help` for usage info.
- Review the [QUICKSTART](./QUICKSTART.md) and [DEVELOPER_GUIDE](./DEVELOPER_GUIDE.md).
- If all else fails, open an issue on the project’s GitHub or reach out to the community.

### Common CLI mismatches
- If docs mention `swarm-cli blueprints list` or `swarm-cli run`, use the current commands instead:
  - List blueprints: `swarm-cli list`
  - Install executable: `swarm-cli install <name>`
  - Launch installed executable: `swarm-cli launch <name> --message "..."`

---

## 6. Running Generated Blueprints in Restricted Environments

If you run a generated blueprint (from `swarm-cli wizard`) in a highly restricted sandbox (e.g., some CI or container sandboxes), you may see errors like:

```
PermissionError: [Errno 1] Operation not permitted (socketpair) … during asyncio event loop creation
```

What it means:
- The blueprint’s `__main__` uses `asyncio.run(...)`, which internally sets up an event loop using system primitives (e.g., socketpair). Some sandboxes prohibit these operations.

How to proceed:
- The blueprint file is valid and compiles; this is an environment restriction.
- Run the script on a normal shell or a less-restricted environment.
- Alternatively, import and run from Python where an event loop is already available and permitted, or disable the `__main__` block for CI-only checks (use `python -m py_compile` for syntax validation).

### Config and secrets location
- Config JSON: `~/.config/swarm/swarm_config.json`
- Secrets file: `~/.config/swarm/.env`
- Reference secrets in JSON using `${ENV_VAR}` (e.g., `"api_key": "${OPENAI_API_KEY}"`).

---



## 7. Browser automation / Playwright MCP

### REQ-45 — Browser (this machine)

The SPA **Browser control** pane defaults to Playwright on **this machine**
(``swarm.core.browser_control``). Same module is the agent tool from CLI, API,
or a remote seat. **Sandbox / Docker** and **SaaS** rows are grey TODO — they
are not wired (do not pretend they work). Desktop/OS control is out of scope
(#341 stub).

Missing Playwright or Chrome returns a structured error (``ok: false``) and
must not crash the process. Tests inject ``StubBrowser`` — there is no fake
success path for a live page. Optional attach: ``SWARM_CHROME_CDP``.

The dismissible **runtime banner** is about where the *app* is running
(``SWARM_RUNTIME_MODE``), not which browser provider is selected. Missing env
is honest unknown — never a green isolated sandbox.

### Playwright MCP (blueprint capability)

Blueprints that declare a ``browser`` capability (e.g. ``whiskeytango_foxtrot``,
``jeeves``) expect the official **microsoft/playwright-mcp** server
(``npx -y @playwright/mcp@latest``). Operating Swarm auto-provisions it in the tool
catalog when missing from config, but it still needs Node/npx available on the
host and a successful MCP process start.

There is **no stub browser that fakes success**. If Playwright MCP is not
configured or fails to start, tools should report:

```
browser automation unavailable: no playwright MCP server
```

(see ``swarm.core.browser_tools.browser_unavailable_error``).

Fix checklist:
- Ensure Node.js / ``npx`` is on ``PATH`` for the server process.
- Optionally pin a ``playwright`` entry under ``mcpServers`` in
  ``swarm_config.json`` (command ``npx``, args ``["-y", "@playwright/mcp@latest"]``).
- Confirm with ``GET /v1/blueprints/<id>/tools`` that ``satisfied.browser`` is
  ``playwright`` and that the process can actually spawn ``npx``.
- First run may download Chromium; allow network or pre-install browsers.

---

## 8. MoA / `swarm-cli moa` common failures

See [MOA.md](./MOA.md) for the model, flags, and team path. Short fixes:

| Symptom | What it means | Fix |
|---------|---------------|-----|
| Grok seats `ok=False` / auth-ish stderr (“not signed in”, login, etc.) | Live `--backend grok` runs local `grok -p`; Operating Swarm does **not** supply xAI credentials. | Sign in with the Grok CLI itself; probe with `swarm-cli cli-agents --check-auth`. Use `--backend fake` for offline/CI. |
| `Error: --team requires --workdir` (exit **2**) | Team mode needs a specialist write workspace. `--cwd` is panel read context only. | Pass both: `--team --workdir /path/to/ws`. |
| `workdir … is outside the workspaces root` (exit **2** / API error text) | Absolute `--workdir`/`params.workdir` outside `SWARM_WORKSPACES_DIR` (default XDG `…/swarm/workspaces`). | Use a relative path under that root, set `SWARM_WORKSPACES_DIR`, or for local CLI only set `ALLOW_UNRESTRICTED_WORKDIR=true`. |
| `--permission approve-all` refused (exit **5**) | Panelists are read-only; `approve-all` is never valid for MoA seats. | Use `approve-reads` (default) or `deny-all`. Specialists still write under `--team`. |
| Soft panel / team failure (exit **1**, payload still printed) | Unusable panel (`ok_count=0`) skips specialists and determination artifacts; or a specialist returns `ok=False`. CLI also prints a `MoA team soft-fail:…` stderr line. Not a silent fake success. | Inspect `--json` / `-v` opinions and specialist `ok` fields; fix backend auth/responses or `--team-tasks` purposes. |
| Broken `~/.cache` (or other XDG) symlink | `ensure_swarm_directories_exist` is best-effort per root — CLI import should not crash on a bad cache path. | Repair or remove the broken symlink; config/data dirs can still be created. Pin `XDG_*` / `HOME` if testing. |

**Tip:** Most issues are caused by misconfigured API keys, missing dependencies, or a corrupted config file. Reviewing or resetting your config often resolves stubborn problems.
