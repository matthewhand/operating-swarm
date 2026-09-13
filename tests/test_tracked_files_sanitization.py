import re
import subprocess
from pathlib import Path

FORBIDDEN_PATTERNS = [
    (re.compile(r"\b10\.0\.0\.\d{1,3}\b"), "Private 10.0.0.x IP address"),
    (re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"), "Private 192.168.x.x IP address"),
    (re.compile(r"\bubuntu-gtx\b", re.IGNORECASE), "Private hostname 'ubuntu-gtx'"),
    (re.compile(r"\bubuntu-max\b", re.IGNORECASE), "Private hostname 'ubuntu-max'"),
]

# Paths allowed to skip (e.g. this test itself)
EXEMPT_FILES = {
    "tests/test_tracked_files_sanitization.py",
}

def test_no_sensitive_data_in_tracked_files():
    """Ensure no private LAN IPs or internal hostnames exist in any tracked git files."""
    repo_root = Path(__file__).resolve().parent.parent
    tracked = subprocess.check_output(["git", "ls-files"], cwd=repo_root, text=True).splitlines()

    violations = []
    for rel_path in tracked:
        if rel_path in EXEMPT_FILES:
            continue
        full_path = repo_root / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Binary file
            continue

        for pattern, label in FORBIDDEN_PATTERNS:
            match = pattern.search(content)
            if match:
                violations.append(f"{rel_path}: matches {label} -> '{match.group(0)}'")

    assert not violations, "Found sensitive data in tracked git files:\n" + "\n".join(violations)
