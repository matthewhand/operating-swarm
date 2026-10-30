"""Approval mixin for blueprint tool execution and user prompts."""

import logging
from typing import Any, Callable
from rich.console import Console

logger = logging.getLogger(__name__)


class ApprovalMixin:
    """Provides user approval controls for blueprint actions and tool execution."""

    approval_required: bool = False
    console: Console = Console()

    def request_approval(
        self, action_type: str, action_summary: str, action_details: Any = None
    ) -> bool:
        """Prompt user for approval before executing an action.

        Returns True if approved, False if rejected, or edited action if supported.
        """
        try:
            from swarm.core.blueprint_ux import BlueprintUX

            ux = BlueprintUX(style="serious")
            box = ux.box(
                f"Approve {action_type}?",
                action_summary,
                summary="Details:",
                params=action_details,
            )
            self.console.print(box)
        except Exception:
            print(f"Approve {action_type}?\n{action_summary}\nDetails: {action_details}")
        while True:
            resp = (
                input("Approve this action? [y]es/[n]o/[e]dit/[s]kip: ")
                .strip()
                .lower()
            )
            if resp in ("y", "yes"):
                return True
            if resp in ("n", "no"):
                return False
            if resp in ("s", "skip"):
                return False
            if resp in ("e", "edit"):
                if action_details:
                    print("Edit not yet implemented; skipping.")
                    return False
                else:
                    print("No editable content; skipping.")
                    return False

    def execute_tool_with_approval(
        self,
        tool_func: Callable,
        action_type: str,
        action_summary: str,
        action_details: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a tool function with approval gate if approval_required is True."""
        if getattr(self, "approval_required", False):
            approved = self.request_approval(action_type, action_summary, action_details)
            if not approved:
                try:
                    self.console.print(f"[yellow]Skipped {action_type}[/yellow]")
                except Exception:
                    print(f"Skipped {action_type}")
                return None
        return tool_func(*args, **kwargs)
