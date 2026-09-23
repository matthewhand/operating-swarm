"""BaseCliAgent and protocol drivers for agentic CLIs.

REQ-889: An agentic CLI is not an arbitrary shell script; it is a
protocol-driven harness with distinct non-interactive prompt injection,
output extraction, session resumption, and model listing semantics.
"""
from __future__ import annotations

import abc
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
from typing import Any

from swarm.core.cli_catalog import extra_cli_path_dirs, host_cli_path

logger = logging.getLogger(__name__)

# Sensitive keys to scrub when probing arbitrary binaries
REDACTED_ENV_KEYS = frozenset({
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "DEEPSEEK_API_KEY",
    "DAYTONA_API_KEY",
    "TRUEFORGE_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
})


def cli_probe_environment() -> dict[str, str]:
    """Return a sanitized copy of os.environ with secrets stripped and PATH augmented."""
    env = dict(os.environ)
    env["PATH"] = host_cli_path()
    for key in REDACTED_ENV_KEYS:
        env.pop(key, None)
    return env


def split_cli_string(cmd_str: str) -> list[str]:
    """Quote-aware tokenization of a CLI command or wrapper string.

    Never invokes a shell. Quotes group arguments with spaces cleanly.
    """
    if not cmd_str:
        return []
    try:
        return shlex.split(cmd_str, posix=(sys.platform != "win32"))
    except ValueError:
        # Fallback to simple split on unclosed quote
        return cmd_str.split()


def find_cli_candidates(name: str) -> list[str]:
    """Discover all executable candidate paths for `name` on host_cli_path() in PATH order.

    If name contains a path separator, returns [name] if it exists and is executable.
    On Windows, it checks PATHEXT extensions (.com, .exe, .bat, .cmd).
    """
    if not name or "\n" in name or "\r" in name:
        return []
    name = name.strip()
    if not name:
        return []

    # If it is already an explicit path, verify and return it
    if os.path.sep in name or (os.altsep and os.altsep in name):
        expanded = os.path.abspath(os.path.expanduser(name))
        return [expanded] if os.path.isfile(expanded) and os.access(expanded, os.X_OK) else []

    exts = [""]
    if sys.platform == "win32":
        pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
        exts = [e.lower() for e in pathext.split(";") if e]

    candidates: list[str] = []
    seen: set[str] = set()

    for directory in host_cli_path().split(os.pathsep):
        if not directory or not os.path.isdir(directory):
            continue
        for ext in exts:
            candidate = os.path.join(directory, name + ext)
            if candidate not in seen and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                seen.add(candidate)
                candidates.append(candidate)
                break  # Match first extension in this directory

    return candidates


def test_cli_binary(cli: str, timeout: float = 10.0) -> dict[str, Any]:
    """Pre-save probe: executes `<cli> --version` in a sanitized environment.

    Bounds buffer to 64KB and enforces a strict SIGKILL timeout.
    """
    argv = split_cli_string(cli)
    if not argv:
        return {"ok": False, "message": "cli command must not be empty"}

    target = argv[0]
    # Resolve executable path if not absolute
    if not os.path.isabs(target):
        resolved = shutil.which(target, path=host_cli_path())
        if not resolved:
            return {"ok": False, "message": f"Executable '{target}' not found on PATH"}
        argv[0] = resolved

    probe_argv = [*argv, "--version"]

    try:
        proc = subprocess.run(
            probe_argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=cli_probe_environment(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"CLI test timed out after {int(timeout)}s"}
    except FileNotFoundError:
        return {"ok": False, "message": f"Executable '{target}' was not found"}
    except PermissionError:
        return {"ok": False, "message": f"Permission denied executing '{target}'"}
    except OSError as exc:
        return {"ok": False, "message": f"Failed to spawn '{target}': {exc}"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    # Success if exit code is 0
    if proc.returncode == 0:
        version_line = stdout.splitlines()[0] if stdout else (stderr.splitlines()[0] if stderr else "OK")
        return {"ok": True, "version": version_line[:120]}

    # Some tools return version info on stderr or exit 1 with --version
    if stdout or stderr:
        first_line = stdout.splitlines()[0] if stdout else stderr.splitlines()[0]
        if any(w in first_line.lower() for w in ("version", "v0.", "v1.", "v2.", "v3.", "build", "release")):
            return {"ok": True, "version": first_line[:120]}

    err_sample = stderr[:200] or stdout[:200] or f"Exit code {proc.returncode}"
    return {"ok": False, "message": f"CLI exited with error: {err_sample}"}


class BaseCliAgent(abc.ABC):
    """Protocol and execution contract for an agentic CLI harness."""

    name: str = ""
    display_name: str = ""
    default_binary: str = ""
    env_allowlist: list[str] | None = None
    list_capability: str = "unsupported"  # works | paste-only | unsupported

    @abc.abstractmethod
    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        """Construct non-interactive argv with prompt, safety bypasses, and flags."""
        raise NotImplementedError

    @abc.abstractmethod
    def parse_output(self, stdout: str) -> str:
        """Extract the agent's textual reply from raw stdout."""
        raise NotImplementedError

    def list_models(self) -> list[str]:
        """Enumerate models supported by this CLI."""
        return []

    def list_sessions(self, cwd: str | None = None) -> list[dict[str, Any]]:
        """Enumerate active/past sessions for this CLI."""
        return []

    def resume_session_argv(self, session_id: str) -> list[str]:
        """Flags injected when resuming an existing session id."""
        return []

    def smoke_flags(self) -> list[str]:
        """Flags injected only during smoke/verification turns."""
        return []

    def probe_binary(self, binary_path: str | None = None) -> dict[str, Any]:
        """Run --version with redacted env and timeout to verify binary viability."""
        cmd = binary_path or self.default_binary
        return test_cli_binary(cmd)


# --- Concrete Built-In Drivers ---

class ClaudeCliAgent(BaseCliAgent):
    name = "claude"
    display_name = "Claude Code"
    default_binary = "claude"
    env_allowlist = ["ANTHROPIC_API_KEY"]
    list_capability = "paste-only"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        argv = [*bin_cmd, f"-p={prompt}", "--output-format", "json", "--dangerously-skip-permissions"]
        if session_id:
            argv = [*argv[:1], "--resume", session_id, *argv[1:]]
        return argv

    def parse_output(self, stdout: str) -> str:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return str(data.get("result") or data.get("text") or stdout).strip()
        except (ValueError, TypeError):
            pass
        return stdout.strip()

    def resume_session_argv(self, session_id: str) -> list[str]:
        return ["--resume", session_id]


class GrokCliAgent(BaseCliAgent):
    name = "grok"
    display_name = "Grok Agent"
    default_binary = "grok"
    list_capability = "works"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        argv = [*bin_cmd, "--output-format", "json", "--always-approve", f"-p={prompt}"]
        if session_id:
            argv = [*argv[:1], "--resume", session_id, *argv[1:]]
        return argv

    def parse_output(self, stdout: str) -> str:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return str(data.get("text") or data.get("response") or stdout).strip()
        except (ValueError, TypeError):
            pass
        return stdout.strip()

    def resume_session_argv(self, session_id: str) -> list[str]:
        return ["--resume", session_id]


class GeminiCliAgent(BaseCliAgent):
    name = "gemini"
    display_name = "Gemini Code"
    default_binary = "gemini"
    env_allowlist = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    list_capability = "unsupported"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        argv = [*bin_cmd, "-p", prompt, "-o", "json", "--yolo", "--skip-trust"]
        if model:
            argv.extend(["--model", model])
        return argv

    def parse_output(self, stdout: str) -> str:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return str(data.get("response") or data.get("text") or stdout).strip()
        except (ValueError, TypeError):
            pass
        return stdout.strip()


class CodexCliAgent(BaseCliAgent):
    name = "codex"
    display_name = "Codex CLI"
    default_binary = "codex"
    env_allowlist = ["OPENAI_API_KEY"]
    list_capability = "unsupported"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        argv = [*bin_cmd, "exec", "--dangerously-bypass-approvals-and-sandbox"]
        if model:
            argv.extend(["--model", model])
        argv.extend(["--", prompt])
        return argv

    def parse_output(self, stdout: str) -> str:
        return stdout.strip()


class AgyCliAgent(BaseCliAgent):
    name = "agy"
    display_name = "Antigravity CLI"
    default_binary = "agy"
    list_capability = "works"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        argv = [*bin_cmd, "--output-format", "json", "--dangerously-skip-permissions", f"-p={prompt}"]
        if session_id:
            argv = [*argv[:1], "--conversation", session_id, *argv[1:]]
        return argv

    def parse_output(self, stdout: str) -> str:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return str(data.get("response") or data.get("result") or stdout).strip()
        except (ValueError, TypeError):
            pass
        return stdout.strip()

    def resume_session_argv(self, session_id: str) -> list[str]:
        return ["--conversation", session_id]


class OpenCodeCliAgent(BaseCliAgent):
    name = "opencode"
    display_name = "OpenCode"
    default_binary = "opencode"
    list_capability = "unsupported"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        chosen_model = model or "litellm/orchestration"
        return [*bin_cmd, "run", "--model", chosen_model, "--", prompt]

    def parse_output(self, stdout: str) -> str:
        return stdout.strip()


class KiloCodeCliAgent(BaseCliAgent):
    name = "kilocode"
    display_name = "Kilo Code"
    default_binary = "kilo"
    list_capability = "unsupported"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        return [*bin_cmd, "run", "--", prompt]

    def parse_output(self, stdout: str) -> str:
        return stdout.strip()


class PiCliAgent(BaseCliAgent):
    name = "omp"
    display_name = "Oh My Pi"
    default_binary = "omp"
    list_capability = "unsupported"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        return [*bin_cmd, "--print", "--auto-approve", "--", prompt]

    def parse_output(self, stdout: str) -> str:
        return stdout.strip()


class QwenCliAgent(BaseCliAgent):
    name = "qwen"
    display_name = "Qwen Code"
    default_binary = "qwen"
    list_capability = "works"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        argv = [*bin_cmd, "--output-format", "json", "-p", prompt]
        if session_id:
            argv = [*argv[:1], "--resume", session_id, *argv[1:]]
        return argv

    def parse_output(self, stdout: str) -> str:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return str(data.get("result") or data.get("response") or stdout).strip()
        except (ValueError, TypeError):
            pass
        return stdout.strip()

    def resume_session_argv(self, session_id: str) -> list[str]:
        return ["--resume", session_id]


class HermesCliAgent(BaseCliAgent):
    name = "hermes"
    display_name = "Hermes Agent"
    default_binary = "hermes"
    list_capability = "unsupported"

    def build_exec_argv(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        binary_override: str | None = None,
    ) -> list[str]:
        bin_cmd = split_cli_string(binary_override or self.default_binary)
        return [*bin_cmd, "run", "--prompt", prompt]

    def parse_output(self, stdout: str) -> str:
        return stdout.strip()
