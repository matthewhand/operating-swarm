#!/usr/bin/env python3
"""Sequential WebUI agent QA sweep (issue #1357).

Sends a short deterministic prompt to **every configured agent** through the
Operating Swarm web UI (one agent at a time), records the response and latency,
saves a screenshot per agent, writes a Markdown + JSON report, and stands up a
temporary static webserver serving the evidence directory.

The sweep is deliberately non-fatal per seat: a slow, down, or misconfigured
agent is recorded as a non-passing outcome and the sweep continues.

Honesty rules this harness now enforces (all three were live bugs):

1. **Nothing advertised may be dropped.** ``/v1/agents/`` is the authoritative
   seat list; the enumerator emits one row per advertised id and shouts if it
   ever drops one. A run that covers fewer seats than the app advertises can
   never report ``PASS``.
2. **A prompt echo is not an answer.** Every seat lands in exactly one of the
   ``OUTCOMES`` below. ``answered`` requires a genuine model turn; verbatim
   prompt echoes, the seat's own banner and orchestrator panels that quote the
   prompt are classified separately and counted in the report.
3. **An evidence dir is never silently clobbered.** A fresh run into a
   non-empty ``--out`` refuses to start unless ``--resume`` or ``--force``.

Examples
--------
::

    # full sweep of every configured seat shown in the app rail
    .venv/bin/python scripts/sweep_webui_agents.py

    # full sweep of every seat /v1/agents/ advertises (never truncated)
    .venv/bin/python scripts/sweep_webui_agents.py --source api

    # quick smoke test (first 3 seats), no webserver
    .venv/bin/python scripts/sweep_webui_agents.py --limit 3 --no-server

    # re-run, skipping seats already recorded, with a 60s per-agent cap
    .venv/bin/python scripts/sweep_webui_agents.py --resume --timeout 60

Only the live backend origin is targeted by default (``http://127.0.0.1:8002``).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
import traceback
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8002"
DEFAULT_OUT = "/tmp/webui-agent-sweep"
DEFAULT_PORT = 8099

# First match wins. The dedicated testids are preferred over the generic one.
COMPOSER_SELECTORS = [
    '[data-testid="chat-message-input"] textarea',
    'textarea[aria-label="Chat message"]',
    "textarea",
]

ERROR_SELECTORS = [
    '[data-testid="flagrant-error"]',
    '[data-testid="send-failed"]',
    '[role="alert"]',
]

# Errors surfaced inside a normal assistant bubble still mean the seat failed.
ERR_PAT = re.compile(
    r"(?i)(\berror\b|\bfailed\b|\bfailure\b|not found|not configured|unknown remote|"
    r"no cli agents|invalid model|all cli candidates failed|exited \d|\b40\d\b|\b50\d\b|"
    r"timed out|unauthorized|\b401\b)"
)

# Reply text is read from the rendered markdown body of the bubble, which keeps
# it free of the avatar / timestamp chrome that wraps it.
JS_TRANSCRIPT = """() => [...document.querySelectorAll('[data-message-role]')].map(e => {
  const md = e.querySelector('[data-testid="chat-md"]');
  const text = ((md ? md.innerText : e.innerText) || '').trim();
  return {
    role: e.getAttribute('data-message-role'),
    streaming: !!e.querySelector('[data-streaming-partial]'),
    text,
  };
})"""


# --------------------------------------------------------------------------- #
# Outcome classification
# --------------------------------------------------------------------------- #
# "the sweep token appears somewhere in the last bubble" is not success. Seats
# that never reach a model routinely emit a bubble that *contains* the token: a
# verbatim echo of the prompt, the seat's own system-prompt banner, or an
# orchestrator panel that restates the prompt. All of those scored ``ok`` under
# the old rule, so a fleet that never produced a single model turn still read
# green. Every seat is now classified into exactly one of these outcomes and
# the report prints the count of each.
OUTCOMES = (
    # the seat ran a model turn and acknowledged the prompt token
    "answered",
    # a bubble appeared, but it is the prompt (or the token) handed back
    "echo_only",
    # a MoA/ensemble/orchestrator panel that merely quotes the prompt
    "orchestrator_artifact",
    # the seat's own system-prompt / "ready" banner, on screen before we sent
    "banner_only",
    # a final bubble, but the prompt token never appears in it
    "no_token",
    # error element, in-band failure string, or an exception
    "error",
    # no final bubble before the per-seat deadline
    "timeout",
    # the deep-link rendered no composer (seat does not mount)
    "no_ui",
    # enumerated but not swept yet
    "pending",
)

PASSING_OUTCOMES = ("answered",)

# A genuine model turn cannot happen instantly. The poll loop below samples at
# ~1.9s, so observed latencies are quantised: across the reference runs every
# real answer landed at >=4.9s while every echo/artifact landed at <=3.9s.
# This floor is used *only* to demote a token-only reply, where the text itself
# carries no other signal. Override with --min-answer-latency 0 to disable.
DEFAULT_MIN_ANSWER_LATENCY = 4.5

# Normalised similarity at/above which a reply is "the prompt, back again".
ECHO_SIMILARITY = 0.80

# Orchestrator / ensemble panels that restate the prompt instead of answering.
# Scanned against the reply with the sweep token masked out, because a seat id
# can legitimately contain one of these words (``cli_orchestrator``).
ORCHESTRATOR_PAT = re.compile(
    r"(?i)(orchestrator|consensus|participant opinions?|decision context|"
    r"read-only panel|synthesi[sz]ed by|---BEGIN BRIEF---|---END BRIEF---|\bpanel:)"
)

# Unambiguous "this seat cannot work" strings returned *as the reply* rather
# than through an error element, so ERR_PAT never saw them.
INBAND_FAIL_PAT = re.compile(
    r"(?i)(is not on path|is not installed|no [a-z0-9 _-]{0,40}is configured|"
    r"not a member of|cannot be started|provider is unusable)"
)

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s-]")


def normalise(text: str) -> str:
    """Casefold + strip punctuation + collapse whitespace, for text compare."""
    return _WS.sub(" ", _NON_WORD.sub(" ", (text or "").casefold())).strip()


def similarity(a: str, b: str) -> float:
    """Normalised 0..1 similarity of two texts (1.0 == identical)."""
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _mask(text: str, *needles: str) -> str:
    """Blank out needles so a quoted prompt cannot trip a content pattern.

    ``cli_orchestrator`` legitimately answers with the token
    ``SWEEP-CLI-ORCHESTRATOR-EF23``; scanning that for orchestrator markers would
    misread a real model turn as an orchestrator panel. Every word of the prompt
    is masked, not just the token, so ``---BEGIN BRIEF--- Intent: ... reply with
    the exact token "SWEEP-..."`` is judged on the panel around the quote.
    """
    out = text or ""
    for needle in needles:
        if not needle:
            continue
        out = re.sub(re.escape(needle), " ", out, flags=re.IGNORECASE)
    return out


def sweep_token(prompt: str, token: str) -> str:
    """Recover the full ``SWEEP-<agent>-<hash>`` token from the prompt.

    ``rec["token"]`` only stores the 4-char run hash, but the reply carries the
    whole token, so a token-only check against the bare hash never matches.
    """
    if not token:
        return ""
    for word in reversed((prompt or "").split()):
        word = word.strip("\"'.,;:!?()[]")
        if token.casefold() in word.casefold() and re.fullmatch(r"[A-Za-z0-9_-]+", word):
            return word
    return token


def classify_reply(
    *,
    prompt: str,
    reply: str,
    token: str = "",
    baseline: tuple | list = (),
    latency_s=None,
    error: str = "",
    min_latency: float = DEFAULT_MIN_ANSWER_LATENCY,
) -> dict:
    """Classify one seat's final bubble. Pure: no browser, no network, no clock.

    ``baseline`` is the set of bubble texts that were already on screen *before*
    the prompt was sent, which is how a seat's own banner is told apart from a
    model turn.
    """
    reply = (reply or "").strip()
    norm_prompt = normalise(prompt)
    norm_reply = normalise(reply)
    full_token = sweep_token(prompt, token)

    def done(outcome: str, reason: str, **extra) -> dict:
        return {
            "outcome": outcome,
            "reason": reason,
            "similarity": extra.pop("similarity", None),
            "echoed": bool(extra.pop("echoed", False)),
            **extra,
        }

    if not reply:
        return done("timeout", "timeout: no final assistant reply")

    error = (error or "").strip()
    if error and error not in reply:
        return done("error", f"error surfaced in the UI: {error[:160]}")
    if ERR_PAT.search(reply) or INBAND_FAIL_PAT.search(reply):
        return done("error", "failure string returned in-band as the reply")

    # The seat's own system-prompt / "Agent X ready." banner. This exact bubble
    # was on screen before we sent anything, so no model turn followed.
    if norm_reply and norm_reply in {normalise(t) for t in baseline}:
        return done("banner_only",
                    "the bubble is the seat's own pre-send banner — no model turn")

    # Exactly the requested token and nothing else. This is the shape a real
    # answer *and* a hand-echo both take, and the text carries no other signal,
    # so time is the only discriminator: a model turn cannot complete inside the
    # ~1.9s poll cadence. Checked before the echo rules below, which would
    # otherwise flag every genuine one-word answer as "the prompt, back again".
    if full_token and norm_reply == normalise(full_token):
        if min_latency and (latency_s is None or latency_s < min_latency):
            return done(
                "echo_only",
                f"token-only reply in {latency_s}s (under the {min_latency}s "
                "model-turn floor) — the seat never called a model",
                echoed=True,
            )
        return done("answered", "answered with the requested token")

    if ORCHESTRATOR_PAT.search(_mask(reply, full_token, token, *prompt.split())):
        return done("orchestrator_artifact",
                    "orchestrator/ensemble panel restating the prompt, not an answer")

    if norm_prompt and norm_prompt in norm_reply:
        return done("echo_only", "reply contains the prompt verbatim", echoed=True)

    sim = similarity(reply, prompt)
    if sim >= ECHO_SIMILARITY:
        return done("echo_only",
                    f"reply is a {sim:.0%} near-verbatim echo of the prompt",
                    similarity=round(sim, 3), echoed=True)

    if full_token and full_token not in reply:
        return done("no_token",
                    "replied, but the prompt token never appears in the reply",
                    similarity=round(sim, 3))

    return done("answered", "answered", similarity=round(sim, 3))


def reclassify(rec: dict, min_latency: float = DEFAULT_MIN_ANSWER_LATENCY) -> dict:
    """Re-derive ``outcome`` for a stored record.

    Classification is a pure function of the record's own fields, so a
    ``--resume`` run can re-judge results recorded by an older, laxer build of
    this harness instead of carrying a stale ``ok`` forward.
    """
    stored = rec.get("outcome")
    if stored in OUTCOMES and stored != "pending":
        rec = dict(rec)
        rec["status"] = stored
        return rec
    rec = dict(rec)
    reply = (rec.get("reply") or "").strip()
    status = rec.get("status")
    if status == "no_ui" or (not reply and status in ("error", "timeout")):
        rec["outcome"] = status or "error"
    else:
        verdict = classify_reply(
            prompt=rec.get("prompt", ""),
            reply=reply,
            token=rec.get("token", ""),
            latency_s=rec.get("latency_s"),
            error=rec.get("error", ""),
            min_latency=min_latency,
        )
        rec["outcome"] = verdict["outcome"]
        rec["reason"] = verdict["reason"]
    rec["status"] = rec["outcome"]
    return rec


def outcome_counts(rows: list) -> dict:
    """Count every row into the full outcome set, so zero rows are explicit."""
    counts = dict.fromkeys(OUTCOMES, 0)
    for r in rows:
        key = r.get("outcome") or r.get("status") or "pending"
        counts[key] = counts.get(key, 0) + 1
    return counts


def sweep_verdict(counts: dict, total: int, coverage: dict | None = None) -> str:
    """PASS only when every enumerated seat genuinely answered.

    A run that enumerated fewer seats than the app advertises can never be a
    PASS — a truncated sweep used to read as a green one.
    """
    answered = counts.get("answered", 0)
    if total and answered >= total and not (coverage or {}).get("short"):
        return "PASS"
    if any(counts.get(name) for name in PASSING_OUTCOMES):
        return "PARTIAL"
    return "FAIL"


def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def slug(text: str) -> str:
    """Filesystem / prompt safe slug for an agent id."""
    text = text.split(":")[-1] if text.startswith(("remote:", "team:", "herdr:")) else text
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "agent"


def kind_of(href: str) -> str:
    if "team=" in href:
        return "team"
    if "remote=" in href:
        return "remote"
    if "cli=" in href or "/cli_agent" in href:
        return "cli"
    return "api"


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError("no free port found")


# --------------------------------------------------------------------------- #
# Agent discovery
# --------------------------------------------------------------------------- #
JS_COLLECT_RAIL = """() => {
  const out = [];
  document.querySelectorAll('a').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!/blueprint=|remote=|team=|(\\b|&)cli=/.test(href)) return;
    const nameEl = a.querySelector('[data-testid="rail-agent-name"]');
    const name = ((nameEl ? nameEl.textContent : a.textContent) || '').trim();
    out.push({ href, name: name.slice(0, 80), agentId: a.getAttribute('data-agent-id') || null });
  });
  return out;
}"""

JS_SCROLL_RAIL = """() => {
  const link = [...document.querySelectorAll('a')].find(
    a => /blueprint=|remote=|team=|(\\b|&)cli=/.test(a.getAttribute('href') || ''));
  if (!link) return false;
  let el = link.parentElement, scroller = null;
  while (el && el !== document.body) {
    const s = getComputedStyle(el);
    if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 4) {
      scroller = el; break;
    }
    el = el.parentElement;
  }
  if (!scroller) {
    const before = window.scrollY;
    window.scrollBy(0, window.innerHeight * 0.8);
    return window.scrollY > before;
  }
  const before = scroller.scrollTop;
  scroller.scrollTop = Math.min(scroller.scrollHeight, before + scroller.clientHeight * 0.8);
  return scroller.scrollTop > before;
}"""


def collect_rail_agents(page, base: str) -> list[dict]:
    """Read the configured seats from the app rail (authoritative UI list).

    The rail is virtualized, so only visible rows live in the DOM. We use a
    tall viewport and then scroll the rail to the bottom, accumulating rows
    (deduped, in top-to-bottom order) until the DOM stops growing.
    """
    page.goto(base + "/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(7000)

    collected: dict[tuple, dict] = {}
    for _ in range(40):
        for r in page.evaluate(JS_COLLECT_RAIL):
            key = (r["href"], r["name"])
            collected.setdefault(key, r)
        if not page.evaluate(JS_SCROLL_RAIL):
            break
        page.wait_for_timeout(250)

    agents: list[dict] = []
    for i, r in enumerate(collected.values()):
        href = r["href"]
        aid = (r.get("agentId") or "").split(":", 1)[-1] or None
        agents.append(
            {
                "idx": i + 1,
                "id": aid or slug(r["name"]),
                "name": r["name"] or aid or f"agent-{i + 1}",
                "kind": kind_of(href),
                "seat_kind": kind_of(href),
                "url": base + href,
            }
        )
    return agents


def _agent_items(payload) -> dict:
    """Normalise every ``/v1/agents/`` payload shape to {id: agent}."""
    if isinstance(payload, list):
        return {str(a.get("id") or a.get("agent_id") or a.get("name")): a
                for a in payload if isinstance(a, dict)}
    agents = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
    items = agents.get("agents", payload.get("agents", payload))
    if isinstance(items, list):
        return {str(a.get("id") or a.get("agent_id") or a.get("name")): a
                for a in items if isinstance(a, dict)}
    return items or {}


def advertised_ids(payload) -> list:
    """Every seat id the app advertises. The enumerator must match this set."""
    return list(_agent_items(payload))


def seat_url(base: str, aid: str, agent: dict) -> str:
    """Deep link for one advertised seat.

    Every advertised seat gets a row. Routing by ``remote=`` / ``cli=`` where the
    seat is a remote/CLI seat and ``blueprint=`` for everything else, which is
    what the app rail itself links to.
    """
    atype = str(agent.get("agent_type") or "").lower()
    kind = str(agent.get("kind") or "").lower()
    if atype == "remote" or kind == "remote":
        return f"{base}/chat?remote={aid}"
    if atype == "cli" or kind == "cli":
        cli = (str(agent.get("cli") or "").strip()) or aid
        return f"{base}/chat?blueprint={aid}&cli={cli}"
    return f"{base}/chat?blueprint={aid}"


def seat_kind(agent: dict) -> str:
    """Report-facing kind: the four first-class seat kinds."""
    atype = str(agent.get("agent_type") or "").lower()
    kind = str(agent.get("kind") or "").lower()
    if atype == "remote" or kind == "remote":
        return "remote"
    if atype == "cli" or kind == "cli":
        return "cli"
    return "api"


def api_agent_rows(payload, base: str) -> list:
    """Turn a ``/v1/agents/`` payload into sweep rows — one per advertised seat.

    Regression guard for #1357: this used to end in ``else: continue``, which
    silently dropped every ``kind=blueprint`` / ``kind=personality`` seat. A
    live run reported 42 seats while ``/v1/agents/`` advertised 112, so a green
    sweep had never actually exercised 70 of them. Nothing is skipped here.
    """
    rows = []
    for aid, agent in _agent_items(payload).items():
        rows.append(
            {
                "idx": len(rows) + 1,
                "id": aid,
                "name": agent.get("name") or aid,
                "kind": seat_kind(agent),
                "seat_kind": agent.get("kind") or "",
                "agent_type": agent.get("agent_type") or "",
                "url": seat_url(base, aid, agent),
            }
        )
    return rows


def fetch_agents_payload(base: str) -> dict:
    with urllib.request.urlopen(base + "/v1/agents/", timeout=20) as resp:
        return json.load(resp)


def collect_api_agents(page, base: str) -> list:
    """Derive seats from the app's /v1/agents/ endpoint (authoritative list)."""
    payload = fetch_agents_payload(base)
    ids = advertised_ids(payload)
    agents = api_agent_rows(payload, base)
    missing = sorted(set(ids) - {a["id"] for a in agents})
    extra = sorted({a["id"] for a in agents} - set(ids))
    log(f"[sweep] /v1/agents/ advertises {len(ids)} seats; enumerated {len(agents)}")
    if missing or extra:
        log(f"[sweep] FATAL enumerator mismatch: dropped={missing[:20]} "
            f"unexpected={extra[:20]}")
    return agents


# --------------------------------------------------------------------------- #
# Single-agent turn
# --------------------------------------------------------------------------- #
def dismiss_overlays(page) -> None:
    for sel in (
        '[data-testid="demo-tour-banner"] button',
        'button[aria-label="Close"]',
    ):
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=800)
        except Exception:
            pass


def collect_error(page) -> str:
    for sel in ERROR_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count():
                txt = (loc.first.inner_text() or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
    return ""


def sweep_agent(browser, agent: dict, args) -> dict:
    """Send one prompt to one seat. Never raises."""
    rec = {
        "idx": agent["idx"],
        "id": agent["id"],
        "name": agent["name"],
        "kind": agent["kind"],
        "seat_kind": agent.get("seat_kind", ""),
        "url": agent["url"],
        "status": "error",
        "outcome": "error",
        "reason": "",
        "prompt": "",
        "reply": "",
        "error": "",
        "matched": False,
        "user_echoed": False,
        "latency_s": None,
        "elapsed_s": None,
        "screenshot": None,
        "stale": False,
        "started_at": now_iso(),
    }
    token = hashlib.sha1(f"{agent['id']}:{args.run_token}".encode()).hexdigest()[:4].upper()
    prompt = args.prompt.format(agent=slug(agent["id"]).upper(), token=token)
    rec["prompt"] = prompt
    rec["token"] = token
    rec["sweep_token"] = sweep_token(prompt, token)

    shot_name = f"{agent['idx']:02d}-{slug(agent['id'])}.png"
    shot_path = os.path.join(args.out, shot_name)
    t0 = time.time()
    ctx = None
    page = None
    try:
        ctx = browser.new_context(viewport={"width": 1440, "height": 1080})
        page = ctx.new_page()
        page.goto(agent["url"], wait_until="domcontentloaded", timeout=args.nav_timeout)
        page.wait_for_timeout(args.settle_ms)
        dismiss_overlays(page)

        composer = None
        deadline = time.time() + args.composer_timeout / 1000.0
        while time.time() < deadline and composer is None:
            for sel in COMPOSER_SELECTORS:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    composer = loc.first
                    break
            if composer is None:
                page.wait_for_timeout(250)

        if composer is None:
            rec.update(
                status="no_ui",
                outcome="no_ui",
                reason="no composer rendered (seat unavailable / invalid deep-link)",
            )
            try:
                page.screenshot(path=shot_path, full_page=True)
                rec["screenshot"] = shot_name
            except Exception:
                pass
            rec["elapsed_s"] = round(time.time() - t0, 1)
            return rec

        baseline = [m for m in page.evaluate(JS_TRANSCRIPT) if m["text"]]
        base_replies = len(baseline)
        baseline_texts = [m["text"] for m in baseline]
        users_before = page.locator('[data-message-role="user"]').count()

        composer.click()
        composer.fill(prompt)
        page.wait_for_timeout(150)
        t_prompt = time.time()
        composer.press("Enter")

        reply = ""
        deadline = t_prompt + args.timeout
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            try:
                msgs = [m for m in page.evaluate(JS_TRANSCRIPT) if m["text"]]
            except Exception:
                continue
            users_after = page.locator('[data-message-role="user"]').count()
            rec["user_echoed"] = users_after > users_before
            if not rec["user_echoed"] or len(msgs) <= base_replies:
                continue
            candidate = msgs[-1]
            if candidate["role"] not in ("assistant", "status"):
                continue
            if candidate["streaming"]:
                continue  # still streaming — let it finalise
            # confirm the last bubble is stable before accepting it
            page.wait_for_timeout(800)
            final = [m for m in page.evaluate(JS_TRANSCRIPT) if m["text"]]
            if final and final[-1]["text"] == candidate["text"] and not final[-1]["streaming"]:
                reply = candidate["text"]
                break

        rec["latency_s"] = round(time.time() - t_prompt, 1) if reply else None
        rec["reply"] = reply[:1500]
        rec["matched"] = bool(reply) and rec["sweep_token"] in reply

        error = collect_error(page)
        rec["error"] = error[:500]

        verdict = classify_reply(
            prompt=prompt,
            reply=reply,
            token=token,
            baseline=baseline_texts,
            latency_s=rec["latency_s"],
            error=rec["error"],
            min_latency=args.min_answer_latency,
        )
        if not reply and rec["error"]:
            verdict = {
                "outcome": "error",
                "reason": "error surfaced (no final reply)",
                "similarity": None,
                "echoed": False,
            }
        rec["outcome"] = verdict["outcome"]
        rec["status"] = verdict["outcome"]  # kept: the report key on this field
        rec["reason"] = verdict["reason"]
        rec["similarity"] = verdict.get("similarity")
        rec["echoed"] = verdict.get("echoed", False)

        try:
            page.screenshot(path=shot_path, full_page=True)
            rec["screenshot"] = shot_name
        except Exception as exc:
            rec["reason"] += f" | screenshot failed: {exc!r}"[:120]

    except Exception as exc:  # never fatal
        rec["status"] = "error"
        rec["outcome"] = "error"
        rec["reason"] = f"exception: {type(exc).__name__}: {exc}"[:300]
        rec["traceback"] = traceback.format_exc()[-800:]
        if page is not None and rec["screenshot"] is None:
            try:
                page.screenshot(path=shot_path, full_page=True)
                rec["screenshot"] = shot_name
            except Exception:
                pass
    finally:
        rec["elapsed_s"] = round(time.time() - t0, 1)
        try:
            if ctx is not None:
                ctx.close()
        except Exception:
            pass
    return rec


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _run_history(args, agents, counts, verdict, coverage) -> list:
    """One entry per run that has written into this evidence dir."""
    history = list(getattr(args, "run_history", []))
    entry = {
        "run_token": args.run_token,
        "started_at": getattr(args, "run_started_at", None) or now_iso(),
        "finished_at": now_iso(),
        "source": args.source,
        "base_url": args.base,
        "enumerated": len(agents),
        "verdict": verdict,
        "outcomes": counts,
        "coverage": coverage,
    }
    if history and history[-1].get("run_token") == entry["run_token"]:
        entry["started_at"] = history[-1].get("started_at", entry["started_at"])
        history[-1] = entry
    else:
        history.append(entry)
    return history


def write_reports(args, agents: list[dict], results: list[dict]) -> None:
    min_latency = getattr(args, "min_answer_latency", DEFAULT_MIN_ANSWER_LATENCY)
    results = [reclassify(r, min_latency) for r in results]

    by_id = {r["id"]: r for r in results}
    ordered, seen = [], set()
    for a in agents:
        seen.add(a["id"])
        ordered.append(
            by_id.get(a["id"])
            or {**a, "status": "pending", "outcome": "pending",
                "reason": "enumerated but not swept in this run", "stale": False}
        )
    # Rows recorded by an earlier run that this run's enumeration no longer
    # lists. They are kept (flagged ``stale``) so a second run into the same
    # --out can never silently delete a previous run's evidence.
    stale = [r for r in results if r["id"] not in seen]
    ordered += [{**r, "stale": True, "name": r.get("name") or r["id"]} for r in stale]
    ordered.sort(key=lambda r: (bool(r.get("stale")),
                                 r.get("outcome") in ("pending",), r.get("idx") or 0))

    counts = outcome_counts(ordered)
    coverage = dict(getattr(args, "coverage", None) or {})
    coverage.setdefault("advertised", None)
    coverage["enumerated"] = len(agents)
    coverage["source"] = args.source
    coverage["short"] = bool(
        coverage.get("advertised") is not None and len(agents) < coverage["advertised"]
    )
    verdict = sweep_verdict(counts, len(agents), coverage)
    total = len(agents)
    summary = {
        "total": total,
        "done": len([r for r in ordered if not r.get("stale")
                     and r.get("outcome") != "pending"]),
        "answered": counts.get("answered", 0),
        "not_answered": total - counts.get("answered", 0),
        "outcomes": counts,
        "stale_from_previous_run": len(stale),
        "coverage": coverage,
        "verdict": verdict,
    }

    meta = {
        "issue": 1357,
        "generated_at": now_iso(),
        "base_url": args.base,
        "run_token": args.run_token,
        "source": args.source,
        "prompt_template": args.prompt,
        "per_agent_timeout_s": args.timeout,
        "min_answer_latency_s": min_latency,
        "outcomes": list(OUTCOMES),
        "summary": summary,
        "run_history": _run_history(args, agents, counts, verdict, coverage),
        "agents": agents,
        "results": ordered,
    }
    with open(os.path.join(args.out, "results.json"), "w") as fh:
        json.dump(meta, fh, indent=2)

    # ---- Markdown ---------------------------------------------------------
    lines = [
        "# Operating Swarm — WebUI Agent Sweep (#1357)",
        "",
        f"- Generated: `{meta['generated_at']}`",
        f"- Verdict: **{verdict}**",
        f"- Origin: `{args.base}` (sequential, one agent at a time)",
        f"- Seat source: `{args.source}` — enumerated **{total}** · "
        + (f"advertised **{coverage['advertised']}**" if coverage.get("advertised")
           is not None else "advertised **unknown**")
        + ("  ⚠️ **INCOMPLETE COVERAGE**" if coverage["short"] else ""),
        f"- Prompt: `{args.prompt}`",
        f"- Per-agent timeout: `{args.timeout}s` · "
        f"model-turn latency floor: `{min_latency}s`",
        "",
        "## Outcome breakdown",
        "",
        "A reply only counts as `answered` when it is a genuine model turn. "
        "`echo_only` / `orchestrator_artifact` / `banner_only` / `no_token` are "
        "bubbles that do **not** mean the seat works.",
        "",
        "| Outcome | Seats |",
        "|---------|------:|",
    ]
    for name in OUTCOMES:
        lines.append(f"| `{name}` | {counts.get(name, 0)} |")
    lines += [
        "",
        f"- Summary: **{summary['done']}/{summary['total']}** swept · "
        f"**{summary['answered']} answered** · {summary['not_answered']} not answered"
        + (f" · {summary['stale_from_previous_run']} stale row(s) kept from an "
           "earlier run" if stale else ""),
        "",
        "| # | Agent | Kind | Outcome | Latency (s) | Matched | Response excerpt | Screenshot |",
        "|---|-------|------|---------|------------:|:-------:|------------------|------------|",
    ]
    for r in ordered:
        excerpt = (r.get("reply") or r.get("error") or r.get("reason") or "").replace("\n", " ")
        excerpt = excerpt.replace("|", "\\|")[:160]
        matched = "yes" if r.get("matched") else ("no" if r.get("reply") else "—")
        lat = r.get("latency_s")
        shot = r.get("screenshot") or ""
        shot_link = f"[{shot}]({shot})" if shot else "—"
        name = str(r.get("name", ""))
        if r.get("stale"):
            name += " _(stale: from an earlier run)_"
        lines.append(
            f"| {r.get('idx', '')} | {name} | {r.get('kind', '')} | "
            f"{r.get('outcome', r.get('status', ''))} | "
            f"{lat if lat is not None else '—'} | {matched} | "
            f"{excerpt} | {shot_link} |"
        )

    def _section(title, rows, empty="- None"):
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        if rows:
            for r in rows:
                why = (r.get("reason") or r.get("error") or r.get("reply") or "")
                why = why.replace("\n", " ")[:240]
                lines.append(f"- **{r.get('name')}** (`{r.get('id')}`, "
                             f"{r.get('kind')}) — {r.get('outcome')}: {why}")
        else:
            lines.append(empty)

    _section(
        "Not a real answer (echo / banner / orchestrator panel / token missing)",
        [r for r in ordered
         if r.get("outcome") in ("echo_only", "orchestrator_artifact",
                                 "banner_only", "no_token")],
    )
    _section(
        "Unreachable / failed seats",
        [r for r in ordered if r.get("outcome") in ("error", "timeout", "no_ui")],
    )
    _section(
        "Never swept",
        [r for r in ordered if r.get("outcome") == "pending"],
    )
    _section(
        "Stale rows kept from an earlier run in this --out",
        [r for r in ordered if r.get("stale")],
        empty="- None (nothing from an earlier run was displaced)",
    )
    lines.append("")
    with open(os.path.join(args.out, "report.md"), "w") as fh:
        fh.write("\n".join(lines))

    # ---- HTML gallery -----------------------------------------------------
    cls_map = {
        "answered": "ok",
        "echo_only": "warn",
        "orchestrator_artifact": "warn",
        "banner_only": "warn",
        "no_token": "warn",
        "error": "bad",
        "timeout": "bad",
        "no_ui": "bad",
    }
    rows = []
    for r in ordered:
        status = r.get("outcome") or r.get("status") or "pending"
        cls = cls_map.get(status, "na")
        why = html.escape(str(r.get("reason") or ""))
        excerpt = html.escape((r.get("reply") or r.get("error") or r.get("reason") or "")[:900])
        if r.get("screenshot"):
            thumb = (f'<a href="{r["screenshot"]}" target="_blank">'
                     f'<img loading="lazy" src="{r["screenshot"]}"></a>')
            link = f'<a href="{r["screenshot"]}" target="_blank">{r["screenshot"]}</a>'
        else:
            thumb, link = "", "&mdash;"
        stale = " <span class='id'>stale</span>" if r.get("stale") else ""
        rows.append(
            f'<tr class="{cls}"><td>{r.get("idx","")}</td>'
            f'<td>{html.escape(str(r.get("name","")))}{stale}'
            f'<div class="id">{html.escape(str(r.get("id","")))}</div></td>'
            f'<td><span class="k k-{html.escape(str(r.get("kind","")))}">{html.escape(str(r.get("kind","")))}</span></td>'
            f'<td>{html.escape(str(status))}<div class="id">{why}</div></td>'
            f'<td>{r.get("latency_s") if r.get("latency_s") is not None else "&mdash;"}</td>'
            f'<td class="reply">{excerpt}</td><td>{link}</td><td>{thumb}</td></tr>'
        )
    verdict_class = {"PASS": "ok", "PARTIAL": "warn", "FAIL": "bad"}[verdict]
    advertised = (f"{coverage['advertised']}" if coverage.get("advertised") is not None
                  else "unknown")
    coverage_note = (" &mdash; <b>INCOMPLETE COVERAGE</b>" if coverage["short"] else "")
    cards = "".join(
        f'<div class="card"><b>{counts.get(name, 0)}</b>{name}</div>'
        for name in OUTCOMES
    )
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Operating Swarm — WebUI Agent Sweep (#1357)</title>
<style>
:root{{color-scheme:dark}}
body{{background:#0e0e10;color:#e6e6e6;font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:24px}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:26px 0 6px}}
.meta{{color:#9aa;margin-bottom:14px}} .meta code{{color:#7dd3fc}}
.verdict{{display:inline-block;padding:2px 10px;border-radius:6px;font-weight:700;margin-left:8px}}
.verdict.ok{{background:#10201a;color:#7ef0c0}} .verdict.warn{{background:#2f2612;color:#fbbf24}}
.verdict.bad{{background:#2a1416;color:#ff9a9a}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}}
.card{{background:#1b1b1f;border:1px solid #2c2c33;border-radius:10px;padding:10px 16px;min-width:96px}}
.card b{{font-size:22px;display:block}}
table{{border-collapse:collapse;width:100%;margin-top:10px}}
th,td{{border:1px solid #2c2c33;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#1b1b1f;position:sticky;top:0;z-index:2}}
tr.bad td{{background:#2a1416}} tr.ok td{{background:#10201a}} tr.warn td{{background:#2f2612}}
.id{{color:#8aa;font-size:11px}}
.k{{padding:1px 6px;border-radius:6px;font-size:11px;background:#333}}
.k-cli{{background:#3a2f12;color:#fbbf24}} .k-api{{background:#12283a;color:#7dd3fc}}
.k-remote{{background:#2a1230;color:#e9a8ff}} .k-team{{background:#123024;color:#7ef0c0}}
.reply{{max-width:520px;white-space:pre-wrap;word-break:break-word}}
img{{width:190px;border:1px solid #333;border-radius:6px;display:block}}
a{{color:#7dd3fc}}
</style></head><body>
<h1>Operating Swarm — WebUI Agent Sweep<span class="verdict {verdict_class}">{verdict}</span></h1>
<div class="meta">Generated {meta['generated_at']} · origin <code>{html.escape(args.base)}</code>
· prompt <code>{html.escape(args.prompt)}</code> · {args.timeout}s/agent · sequential
· source <code>{html.escape(args.source)}</code> · enumerated <b>{total}</b> of
<b>{advertised}</b> advertised{coverage_note}</div>
<div class="cards">
<div class="card"><b>{summary['done']}/{summary['total']}</b>seats swept</div>
{cards}
</div>
<table><tr><th>#</th><th>Agent</th><th>Kind</th><th>Outcome</th><th>Latency (s)</th>
<th>Response</th><th>Screenshot</th><th>Thumb</th></tr>
{''.join(rows)}</table>
</body></html>"""
    with open(os.path.join(args.out, "index.html"), "w") as fh:
        fh.write(doc)


# --------------------------------------------------------------------------- #
# Webserver
# --------------------------------------------------------------------------- #
def start_server(out: str, port: int) -> dict:
    port = free_port(port)
    logfile = os.path.join(out, "server.log")
    logfh = open(logfile, "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", out],
        stdout=logfh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}/"
    time.sleep(1.0)
    alive = proc.poll() is None
    info = {"url": url, "pid": proc.pid, "port": port, "out": out, "alive": alive,
            "log": logfile, "started_at": now_iso()}
    with open(os.path.join(out, "server.json"), "w") as fh:
        json.dump(info, fh, indent=2)
    return info


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def out_dir_conflict(args) -> str:
    """Explain why a fresh run must not write into this ``--out``, else "".

    ``write_reports()`` rebuilds results.json / report.md / index.html from the
    *current* enumeration, so a second run into the same ``--out`` silently
    overwrites the first run's results. A stale green report then outlives the
    sweep that produced it. A fresh run therefore refuses unless the operator
    picks ``--resume`` (add to the existing run) or ``--force`` (overwrite).
    """
    if args.dry_run or args.resume or args.force:
        return ""
    clashes = [name for name in ("results.json", "report.md", "index.html")
               if os.path.exists(os.path.join(args.out, name))]
    if not clashes:
        return ""
    return (
        f"--out {args.out} already holds a previous sweep ({', '.join(clashes)}). "
        f"A fresh run would overwrite it. Re-run with --resume to add to it, "
        f"--force to overwrite deliberately, or pick a different --out / "
        f"SWEEP_OUT (e.g. --out {args.out}/run-{args.run_token})."
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Sequential WebUI agent sweep (#1357)",
        epilog="Verdict is PASS only when every advertised seat is classified "
               "'answered' and the run covered every seat /v1/agents/ "
               "advertises. Prompt echoes, orchestrator panels and a seat's own "
               "banner are reported separately and never count as a pass.",
    )
    ap.add_argument("--base", default=os.environ.get("SWEEP_BASE_URL", DEFAULT_BASE))
    ap.add_argument("--out", default=os.environ.get("SWEEP_OUT", DEFAULT_OUT))
    ap.add_argument("--source", choices=["rail", "api"], default="rail",
                    help="where to read the configured agent list from "
                         "(api = /v1/agents/, the authoritative list; rail is "
                         "virtualised and can under-count)")
    ap.add_argument("--limit", type=int, default=0, help="only sweep the first N agents")
    ap.add_argument("--timeout", type=float, default=120.0, help="per-agent reply timeout (s)")
    ap.add_argument("--nav-timeout", type=float, default=45000, help="page navigation timeout (ms)")
    ap.add_argument("--composer-timeout", type=float, default=25000,
                    help="composer render timeout (ms)")
    ap.add_argument("--settle-ms", type=int, default=3500, help="post-nav settle (ms)")
    ap.add_argument("--prompt", default="Reply with exactly: SWEEP-{agent}-{token}")
    ap.add_argument("--min-answer-latency", type=float,
                    default=DEFAULT_MIN_ANSWER_LATENCY,
                    help="a token-only reply faster than this is an echo, not a "
                         "model turn (0 disables)")
    ap.add_argument("--resume", action="store_true", help="skip agents already in results.json")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing evidence dir instead of refusing")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero unless the verdict is PASS")
    ap.add_argument("--no-server", action="store_true", help="do not start the temp webserver")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate configured agents and exit (no prompts)")
    ap.add_argument("--server-port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args(argv)

    if not args.base.startswith("http"):
        args.base = "http://" + args.base
    args.base = args.base.rstrip("/")
    args.run_token = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    args.run_started_at = now_iso()

    os.makedirs(args.out, exist_ok=True)
    log(f"[sweep] base={args.base} out={args.out} source={args.source} "
        f"timeout={args.timeout}s run_token={args.run_token}")

    conflict = out_dir_conflict(args)
    if conflict:
        log(f"[sweep] FATAL: refusing to clobber a previous sweep. {conflict}")
        return 5

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        log(f"[sweep] FATAL: playwright unavailable: {exc}")
        return 2

    server_info = None
    if not args.no_server:
        server_info = start_server(args.out, args.server_port)
        log(f"[sweep] evidence server: {server_info['url']} (pid {server_info['pid']}, "
            f"alive={server_info['alive']})")

    results_path = os.path.join(args.out, "results.json")
    previous: dict = {}
    existing: list[dict] = []
    if os.path.exists(results_path):
        try:
            with open(results_path) as fh:
                previous = json.load(fh)
        except Exception:
            previous = {}
    if args.resume:
        existing = previous.get("results", [])
        args.run_history = previous.get("run_history", [])
    else:
        args.run_history = previous.get("run_history", []) if args.force else []
    done_ids = {r["id"] for r in existing if r.get("status")}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        try:
            enum_ctx = browser.new_context(viewport={"width": 1440, "height": 2600})
            try:
                if args.source == "rail":
                    agents = collect_rail_agents(enum_ctx.new_page(), args.base)
                else:
                    agents = collect_api_agents(enum_ctx.new_page(), args.base)
            finally:
                enum_ctx.close()
        except Exception as exc:
            log(f"[sweep] FATAL: could not enumerate agents: {exc!r}")
            browser.close()
            return 3

        if not agents:
            log("[sweep] FATAL: no configured agents found")
            browser.close()
            return 4

        # The rail is virtualised, so it can silently under-count. Compare it
        # against the authoritative list: a short run can never be a PASS.
        try:
            advertised = len(advertised_ids(fetch_agents_payload(args.base)))
        except Exception as exc:
            log(f"[sweep] coverage check skipped: {exc!r}")
            advertised = None
        if advertised is None:
            args.coverage = {"advertised": None}
        elif len(agents) < advertised:
            args.coverage = {"advertised": advertised}
            log(f"[sweep] COVERAGE: enumerated {len(agents)} of {advertised} advertised "
                f"seats — INCOMPLETE (source={args.source} is truncated; "
                f"re-run with --source api). This run cannot be a PASS.")
        else:
            args.coverage = {"advertised": advertised}
            log(f"[sweep] coverage: enumerated {len(agents)} of {advertised} advertised seats")

        if args.limit:
            agents = agents[: args.limit]

        log(f"[sweep] {len(agents)} configured agents: "
            + ", ".join(a["id"] for a in agents))

        if args.dry_run:
            for a in agents:
                log(f"  {a['idx']:>3} {a['kind']:7} {a['id']:34} {a['url']}")
            log(f"[sweep] DRY RUN: {len(agents)} seats enumerated from "
                f"{args.source} (advertised: {advertised}) — no prompts sent")
            browser.close()
            return 0

        results = list(existing)
        for agent in agents:
            if args.resume and agent["id"] in done_ids:
                log(f"[{agent['idx']:>2}/{len(agents)}] {agent['id']}: skipped (resume)")
                continue
            rec = sweep_agent(browser, agent, args)
            results = [r for r in results if r["id"] != rec["id"]] + [rec]
            write_reports(args, agents, results)
            lat = f"{rec['latency_s']}s" if rec["latency_s"] is not None else "-"
            log(f"[{rec['idx']:>2}/{len(agents)}] {rec['id']} ({rec['kind']}) "
                f"{rec['outcome']} {lat} :: {(rec.get('reply') or rec.get('error') or rec.get('reason') or '')[:80]!r}")

        browser.close()

    write_reports(args, agents, results)
    with open(results_path) as fh:
        summary = json.load(fh)["summary"]
    log(f"[sweep] DONE verdict={summary['verdict']} "
        f"answered={summary['answered']}/{summary['total']} "
        + " ".join(f"{k}={v}" for k, v in summary["outcomes"].items() if v))
    if server_info:
        log(f"[sweep] report: {os.path.join(args.out, 'report.md')}")
        log(f"[sweep] gallery: {server_info['url']}index.html")
        log(f"[sweep] server URL={server_info['url']} PID={server_info['pid']} (left running)")
    else:
        log(f"[sweep] report: {os.path.join(args.out, 'report.md')}")
    if args.strict and summary["verdict"] != "PASS":
        log("[sweep] FAIL: --strict and the verdict is not PASS")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
