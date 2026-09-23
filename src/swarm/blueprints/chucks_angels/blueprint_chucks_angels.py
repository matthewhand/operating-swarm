"""
Chucks Angels Blueprint
"""
from collections.abc import AsyncGenerator
from typing import Any

from swarm.core.kind_bases import TeamKindBase  # Import the base class


class ChucksAngelsBlueprint(TeamKindBase): # Inherit from BlueprintBase
    """
    Blueprint for Chucks Angels. Coordinates angelic tasks, Chuck Norris style.
    """
    # --- Metadata for 'swarm-cli list' output ---
    metadata = {
        "name": "Chuck's Angels", # Or simply "chucks_angels" if you prefer programmatic names
        "abbreviation": "angels", # Or "chuck" or "cna" - choose a short, memorable one
        "version": "0.1.1", # Incremented version
        "description": "A blueprint for coordinating angelic tasks, Chuck Norris style.",
        "author": "Swarm Contributor", # Optional: Add author
        "emoji": "😇" # Optional: Add an emoji
    }
    # Old class attributes (now in metadata dict)
    # name: str = "Chuck's Angels"
    # version: str = "0.1.0"
    # description: str = "A blueprint for coordinating angelic tasks, Chuck Norris style."

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """
        The main execution method for the Chuck's Angels blueprint.

        Accepts **kwargs (e.g. ``stream=``) for compatibility with the
        OpenAI-compatible API layer, which always passes ``stream``.
        """
        self.console.print(f"[bold green]{self.metadata.get('name', 'Chucks Angels Blueprint')} ({self.blueprint_id}) activated![/bold green]")
        self.console.print(f"Received messages: {messages}")

        last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), "No user message found.")

        yield {
            "type": "message",
            "role": "assistant",
            "content": f"{self.metadata.get('name', 'Chucks Angels')} reporting for duty! Your last message was: '{last_user_message}'"
        }

        yield {
            "type": "message",
            "role": "assistant",
            "content": "Mission accomplished. Roundhouse kick style."
        }
