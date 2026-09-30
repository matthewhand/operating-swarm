"""``seat_doctor`` — which seats are broken, and the exact thing to do about it.

Read-only. Enumerates every api / cli / remote seat, probes each with the
cheapest check that can prove something (``--deep`` spends more), and prints
one line per broken seat: the bucket, the evidence behind it, and the concrete
operator action. ``--json`` emits the same report for scripting.

Examples
--------
::

    python -m django seat_doctor
    python -m django seat_doctor --kind remote
    python -m django seat_doctor --all --json
    python -m django seat_doctor --deep --limit 20

Nothing is written: no config, no library, no secrets store, no database row.
Credentials are referenced by env var *name* only and every emitted string is
scrubbed before it is printed.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from swarm.core.seat_doctor import (
    MAX_SEATS,
    VALID_KINDS,
    format_report,
    report_payload,
)


class Command(BaseCommand):
    help = (
        "seat_doctor: read-only diagnostic for every api/cli/remote seat. "
        "Prints one line per broken seat with the evidence bucket and the "
        "concrete operator action. No mutations."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit the report as JSON (no secrets, no raw credentials).",
        )
        parser.add_argument(
            "--deep",
            action="store_true",
            help=(
                "Spend more per seat: a real provider round trip for CLI seats and "
                "a real remote list. Without it only the minimal probes run."
            ),
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="show_all",
            help="Include unverified/ok rows (default: broken only).",
        )
        parser.add_argument(
            "--kind",
            action="append",
            choices=sorted(VALID_KINDS),
            help="Restrict to one kind (repeatable). Default: all three.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=MAX_SEATS,
            help=f"Cap on seats probed (default: {MAX_SEATS}).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        payload = report_payload(
            deep=bool(options.get("deep")),
            limit=int(options.get("limit") or MAX_SEATS),
            kinds=options.get("kind") or None,
        )
        if options.get("as_json"):
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=False))
            return
        self.stdout.write(format_report(payload, show_all=bool(options.get("show_all"))))
        totals = payload.get("totals") or {}
        if not totals.get("broken"):
            self.stdout.write(self.style.SUCCESS("No broken seat found."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"{totals.get('broken')} broken seat(s) — every row names the fix."
                )
            )
