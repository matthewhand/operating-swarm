"""#1337: the Fly swap reservation must apply at boot and must shrink.

A build ARG is not in the image environment, so ``fallocate -l ${SWAP_SIZE_MB}``
inside the shell CMD ran as ``fallocate -l M`` and the machine never booted.
``fallocate -l`` also does not shrink, so the 768M file already on the ~1 GB
volume stayed in place. The size is a runtime env var (default 384).
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ensure_swapfile.sh"
DOCKERFILE = REPO / "Dockerfile"
FLY = REPO / "fly.toml"


def _write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _stub_bin(tmp_path: Path, *, fallocate: str | None = None) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    # swapoff records whether the file still existed, so a test can prove it
    # runs before the unlink that actually returns the blocks.
    _write_stub(
        bindir,
        "swapoff",
        "#!/bin/sh\n"
        f'echo "swapoff $*" >> "{log}"\n'
        'if [ -e "$1" ]; then echo "swapoff saw file" >> "' + str(log) + '"; fi\n'
        "exit 0\n",
    )
    _write_stub(
        bindir,
        "mkswap",
        "#!/bin/sh\n" f'echo "mkswap $*" >> "{log}"\nexit 0\n',
    )
    _write_stub(
        bindir,
        "swapon",
        "#!/bin/sh\n" f'echo "swapon $*" >> "{log}"\nexit 0\n',
    )
    if fallocate is not None:
        _write_stub(bindir, "fallocate", fallocate)
    return bindir


def _run(tmp_path: Path, swap: Path, mb: str | None, *, fallocate: str | None = None):
    bindir = _stub_bin(tmp_path, fallocate=fallocate)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "SWAPFILE_PATH": str(swap),
    }
    if mb is not None:
        env["SWAP_SIZE_MB"] = mb
    return subprocess.run(
        ["sh", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_larger_swapfile_is_replaced_and_swapoff_runs_first(tmp_path: Path):
    swap = tmp_path / "vol" / "swapfile"
    swap.parent.mkdir()
    swap.write_bytes(b"OLD768" + b"\0" * (2 * 1024 * 1024 - 6))

    result = _run(tmp_path, swap, "1")

    assert result.returncode == 0, result.stderr
    assert swap.stat().st_size == 1024 * 1024
    assert not swap.read_bytes().startswith(b"OLD768")
    assert stat.S_IMODE(swap.stat().st_mode) == 0o600
    log = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "swapoff saw file" in log
    assert "mkswap " in log
    assert "swapon " in log
    assert log.index("swapoff saw file") < log.index("mkswap ")


def test_matching_size_is_not_reallocated(tmp_path: Path):
    swap = tmp_path / "swapfile"
    payload = b"KEEP" + b"\0" * (1024 * 1024 - 4)
    swap.write_bytes(payload)
    result = _run(
        tmp_path,
        swap,
        "1",
        fallocate="#!/bin/sh\necho fallocate-called >&2\nexit 99\n",
    )
    assert result.returncode == 0, result.stderr
    assert swap.read_bytes() == payload
    assert "fallocate-called" not in result.stderr


def test_leading_zero_is_decimal_not_octal(tmp_path: Path):
    swap = tmp_path / "swapfile"
    result = _run(tmp_path, swap, "01")
    assert result.returncode == 0, result.stderr
    assert swap.stat().st_size == 1024 * 1024


def test_bad_size_does_not_touch_the_existing_file(tmp_path: Path):
    swap = tmp_path / "swapfile"
    swap.write_bytes(b"keep-me")
    for bad in ("768M", "abc", "0", "00", "", "-1", "12 8"):
        log = tmp_path / "calls.log"
        log.unlink(missing_ok=True)
        result = _run(tmp_path, swap, bad)
        assert result.returncode != 0, bad
        assert swap.read_bytes() == b"keep-me"
        assert not log.exists()


def test_over_half_the_volume_warns_and_still_allocates(tmp_path: Path):
    swap = tmp_path / "swapfile"
    result = _run(
        tmp_path,
        swap,
        "513",
        fallocate="#!/bin/sh\ntouch \"$3\"\nexit 0\n",
    )
    assert result.returncode == 0, result.stderr
    assert "WARNING: SWAP_SIZE_MB=513" in result.stderr
    assert "mkswap " in (tmp_path / "calls.log").read_text(encoding="utf-8")


def test_unset_path_is_a_noop(tmp_path: Path):
    result = subprocess.run(
        ["sh", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "SWAP_SIZE_MB": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_fallocate_failure_does_not_enable_swap(tmp_path: Path):
    swap = tmp_path / "swapfile"
    result = _run(
        tmp_path,
        swap,
        "1",
        fallocate="#!/bin/sh\nexit 1\n",
    )
    assert result.returncode != 0
    log = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "mkswap " not in log
    assert "swapon " not in log


def test_dockerfile_delegates_to_the_script():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "sh scripts/ensure_swapfile.sh" in text
    assert "fallocate -l" not in text
    assert "ARG SWAP_SIZE_MB" not in text
    script = SCRIPT.read_text(encoding="utf-8")
    assert "mb=384" in script
    assert "fallocate -l" in script
    assert "swapoff" in script
    assert SCRIPT.stat().st_mode & 0o111


def test_fly_toml_sets_the_size_at_runtime():
    text = FLY.read_text(encoding="utf-8")
    assert "SWAP_SIZE_MB = '384'" in text
    assert not any(line.strip() == "[build.args]" for line in text.splitlines())
    assert "min_machines_running = 1" in text
    assert 'SWAPFILE_PATH = "/mnt/sqlite_data/swapfile"' in text
