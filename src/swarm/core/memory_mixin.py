"""Memory mixin for blueprint conversation retrieval and persistence."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MemoryMixin:
    """Provides memory backend integration and context augmentation for blueprints."""

    _memory_backend: Any = None
    _memory_settings: dict[str, Any] = {}

    def _get_memory_instance(self, memory_type: str, memory_config: dict = None):
        """Helper to get a memory backend instance."""
        if not memory_type or memory_type.lower() == "none":
            return None
        from swarm.memory import get_memory_backend

        return get_memory_backend(memory_type, memory_config)

    @property
    def memory_backend(self):
        """The configured memory backend for this blueprint, or None."""
        return getattr(self, "_memory_backend", None)

    def _resolve_memory_settings(self) -> dict | None:
        """Resolve the opt-in 'memory' config block for this blueprint.

        Checks config["blueprints"][blueprint_id]["memory"] first, then the
        top-level config["memory"] block. Returns None when not configured.
        """
        cfg = getattr(self, "_config", None)
        cfg = cfg if isinstance(cfg, dict) else {}
        blueprints_section = cfg.get("blueprints", {})
        bp_id = getattr(self, "blueprint_id", "")
        bp_cfg = (
            blueprints_section.get(bp_id, {})
            if isinstance(blueprints_section, dict)
            else {}
        )
        mem_cfg = bp_cfg.get("memory") if isinstance(bp_cfg, dict) else None
        if mem_cfg is None:
            mem_cfg = cfg.get("memory")
        return mem_cfg if isinstance(mem_cfg, dict) else None

    def _init_memory_backend(self) -> None:
        """Resolve the optional memory backend from config and, when present,
        wrap run() so memories are retrieved before and stored after each run.

        Strictly a no-op when no "memory" block (with a "backend" key) is
        configured, or when the backend package is unavailable.
        """
        bp_id = getattr(self, "blueprint_id", "")
        try:
            mem_cfg = self._resolve_memory_settings()
            if not mem_cfg or not mem_cfg.get("backend"):
                return
            from swarm.memory import get_memory_backend

            backend = get_memory_backend(mem_cfg)
            if backend is None:
                return
            self._memory_settings = mem_cfg
            self._memory_backend = backend
            self._wrap_run_with_memory()
            logger.debug(
                f"Memory backend '{mem_cfg.get('backend')}' enabled for blueprint '{bp_id}'."
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize memory backend for '{bp_id}': {e}"
            )

    def _memory_user_id(self, user_id: str = None) -> str:
        return user_id or getattr(self, "_memory_settings", {}).get("user_id") or "default"

    def inject_memory_context(self, messages: list, user_id: str = None) -> list:
        """Prepend a system message with memories relevant to the latest user message.

        Returns ``messages`` unchanged when no backend is configured, no user
        message is present, or no relevant memories are found.
        """
        backend = self.memory_backend
        if backend is None or not messages:
            return messages
        bp_id = getattr(self, "blueprint_id", "")
        query = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user" and msg.get("content"):
                query = str(msg["content"])
                break
        if not query:
            return messages
        try:
            memories = backend.search(query, user_id=self._memory_user_id(user_id)) or []
        except Exception as e:
            logger.warning(f"Memory search failed for '{bp_id}': {e}")
            return messages
        memories = [str(m).strip() for m in memories if str(m).strip()]
        if not memories:
            return messages
        memory_text = "\n".join(f"- {m}" for m in memories)
        memory_message = {
            "role": "system",
            "content": f"Relevant memories from previous conversations:\n{memory_text}",
        }
        return [memory_message, *list(messages)]

    def store_run_memory(
        self, messages: list, run_chunks: list = None, user_id: str = None
    ) -> None:
        """Persist the conversation (input messages plus assistant output) after a run.

        No-op when no memory backend is configured; storage errors are logged,
        never raised.
        """
        backend = self.memory_backend
        if backend is None:
            return
        bp_id = getattr(self, "blueprint_id", "")
        conversation = [
            m
            for m in (messages or [])
            if isinstance(m, dict) and m.get("role") and m.get("content")
        ]
        for chunk in run_chunks or []:
            if not isinstance(chunk, dict):
                continue
            chunk_messages = chunk.get("messages") or []
            if isinstance(chunk_messages, dict):
                chunk_messages = [chunk_messages]
            for m in chunk_messages:
                if isinstance(m, dict) and m.get("content"):
                    conversation.append(
                        {"role": m.get("role", "assistant"), "content": m["content"]}
                    )
        if not conversation:
            return
        try:
            backend.add(conversation, user_id=self._memory_user_id(user_id))
        except Exception as e:
            logger.warning(f"Memory add failed for '{bp_id}': {e}")

    def _wrap_run_with_memory(self) -> None:
        """Wrap this instance's run() so memory retrieval/storage happen around each run.

        Only invoked when a memory backend is configured, so unconfigured
        blueprints keep their original run() untouched.
        """
        if getattr(self, "_memory_run_wrapped", False):
            return
        original_run = getattr(self, "run", None)
        if original_run is None:
            return

        async def run_with_memory(messages, **kwargs):
            user_id = kwargs.get("user_id")
            augmented = self.inject_memory_context(messages, user_id=user_id)
            collected = []
            async for chunk in original_run(augmented, **kwargs):
                collected.append(chunk)
                yield chunk
            self.store_run_memory(messages, collected, user_id=user_id)

        self.run = run_with_memory
        self._memory_run_wrapped = True
