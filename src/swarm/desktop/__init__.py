"""REQ-883 desktop packaging scaffold (loopback boot contract, no window).

Phase 0 of [#280](https://github.com/matthewhand/open-swarm-private/issues/280):
the frozen installer, pywebview window, and signed ``.dmg`` / ``.msi`` are
follow-up REQs (883B–F). This package pins the boot contracts the plan names
so they cannot silently drift: IPv4 loopback, Operating Swarm profile paths,
first-run secret materialization, and interactive PATH merge for host CLIs.
"""

from swarm.desktop.boot import (
    LOOPBACK_HOST,
    PRODUCT_NAME,
    desktop_process_env,
    desktop_profile_dir,
    loopback_url,
    materialize_secret_key,
    merge_interactive_path,
    pick_free_loopback_port,
    print_plan,
)

__all__ = [
    "LOOPBACK_HOST",
    "PRODUCT_NAME",
    "desktop_process_env",
    "desktop_profile_dir",
    "loopback_url",
    "materialize_secret_key",
    "merge_interactive_path",
    "pick_free_loopback_port",
    "print_plan",
]
