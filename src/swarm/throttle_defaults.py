"""Canonical default DRF throttle rates (no Django/DRF imports).

Imported by ``swarm.settings`` so the SPA read-burst defaults live in one
place. Kept dependency-free so tests can assert the numbers even though the
pytest suite disables throttling entirely (see ``settings.TESTING``).
"""

# Sustained budgets for mutating / unsafe requests.
ANON_RATE = "60/min"
USER_RATE = "120/min"

# Read-burst budgets for safe (read-only) requests: GET / HEAD / OPTIONS.
ANON_READ_RATE = "240/min"
USER_READ_RATE = "480/min"

# The width of every rate above, in seconds. DRF reads it from the
# ``N/min`` suffix; the telemetry log needs the same number to decide when a
# (client, endpoint) rejection bucket has closed, so it lives here rather than
# being written down a second time in the logging code.
RATE_WINDOW_SECONDS = 60
