"""#855 slice 2 — conversation persistence methods, moved verbatim.

fetch/save/delete/apply_message_edit: transcript storage + edit replay.
``@database_sync_to_async`` stays a direct import (no test patches it; an R-routed decorator would touch the deferred import at class-body time — a deadlock if the mixin is imported first).
"""
from __future__ import annotations

from channels.db import database_sync_to_async


import importlib


class _ConsumersRef:
    """Late-bound swarm.consumers handle (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.consumers"), name)


R = _ConsumersRef()


class ConversationsMixin:
    """Mixin host for the moved conversations methods (MRO-merged into DjangoChatConsumer)."""

    async def apply_message_edit(self, edit):
            """Replace one transcript turn and persist it (REQ-49)."""
            from swarm.core.agent_kind import can_edit_agent_messages

            agent = getattr(self, "active_agent", None) or getattr(self, "default_blueprint", None)
            if not can_edit_agent_messages(agent):
                R.logger.info("Ignoring message edit on non-API agent %s", agent)
                return
            if not isinstance(edit, dict):
                R.logger.warning("Ignoring malformed chat edit frame: %.200r", edit)
                return
            index = edit.get("index")
            content = edit.get("content")
            if type(index) is not int or not isinstance(content, str):
                R.logger.warning("Ignoring malformed chat edit frame: %.200r", edit)
                return
            if index < 0 or index >= len(self.messages):
                R.logger.warning(
                    "Ignoring chat edit index %s (transcript length %s)",
                    index,
                    len(self.messages),
                )
                return
            current = dict(self.messages[index])
            current["content"] = content
            current["edited"] = True
            self.messages[index] = current
            conversation_id = getattr(self, "conversation_id", None)
            if conversation_id:
                await self.save_conversation(conversation_id, self.messages)


    @database_sync_to_async
    def fetch_conversation(self, conversation_id):
            """Fetch transcript: cache, then JSON, then Django backfill.

            Load order matches ``GET /chat/thread/`` (``swarm.core.thread_load``):

            0. On-mode mint (REQ-171C-4) — refuse reuse before any row load.
            1. In-memory cache keyed by ``(user_id, conversation_id)``.
            2. JSON disk (source of truth) — keeps ``ts`` / ``edited``.
            3. Django ``R.ChatMessage`` rows when the JSON file is missing.

            Always returns a COPY: two tabs sharing a conversation must not mutate
            each other's in-flight transcript list (interleaved appends previously
            corrupted both and double-persisted merged turns on disconnect).
            """
            from swarm.core import chat_store
            from swarm.core.session_policy import resolve_on_mode_conversation
            from swarm.core.thread_load import load_thread

            agent_id = getattr(self, "default_blueprint", None) or getattr(
                self, "active_agent", None
            )
            # REQ-171C-4 / C-H7: mint or refuse reuse before loading the old Django row.
            if agent_id:
                minted = resolve_on_mode_conversation(self.user, agent_id, conversation_id)
                if minted is not None:
                    self.conversation_id = minted.conversation_id
                    conversation_id = minted.conversation_id
                    cache_key = R._conversation_cache_key(self.user, conversation_id)
                    R.IN_MEMORY_CONVERSATIONS[cache_key] = []
                    R.IN_MEMORY_UI_EVENTS[cache_key] = []
                    self.ui_events = []
                    return []

            cache_key = R._conversation_cache_key(self.user, conversation_id)
            if cache_key in R.IN_MEMORY_CONVERSATIONS:
                self.ui_events = list(R.IN_MEMORY_UI_EVENTS.get(cache_key, []))
                return list(R.IN_MEMORY_CONVERSATIONS[cache_key])

            on_mode = False
            default_cid = ""
            try:
                from swarm.core.agent_settings import is_new_chat_per_task

                if agent_id:
                    default_cid = chat_store.conversation_id_for(self.user, agent_id)
                    on_mode = bool(is_new_chat_per_task(agent_id))
            except Exception:
                R.logger.debug("new-chat-per-task check failed; using reuse fallback", exc_info=True)

            session_id = ""
            if conversation_id and (conversation_id != default_cid or on_mode):
                session_id = conversation_id

            loaded = load_thread(
                self.user,
                agent_id or "",
                requested_cid=conversation_id,
                session_id=session_id,
                default_cid=default_cid,
                fresh_task=on_mode,
            )
            if loaded.turns or loaded.events:
                R.IN_MEMORY_CONVERSATIONS[cache_key] = list(loaded.turns)
                R.IN_MEMORY_UI_EVENTS[cache_key] = list(loaded.events)
                self.ui_events = list(loaded.events)
                return list(loaded.turns)
            self.ui_events = []
            return []


    @database_sync_to_async
    def save_conversation(self, conversation_id, new_messages):
            """Replace DB messages with the current in-memory transcript.

            Disconnect always persists the full transcript. Without clearing
            prior rows, reconnect → disconnect would bulk_create duplicates.

            Lookup is by conversation_id PK only (avoids IntegrityError when the
            row exists for another student); ownership is then validated.
            """
            from swarm.core.transcript_roles import is_ui_only_role, split_store

            cache_key = R._conversation_cache_key(self.user, conversation_id)
            from swarm.core.agent_sessions import get_or_create_session, touch_session

            agent_id = getattr(self, "active_agent", None) or getattr(self, "default_blueprint", None)
            events = list(getattr(self, "ui_events", None) or [])
            turns, events = split_store(new_messages, events, stamp_seq=False)
            self.messages = list(turns)
            self.ui_events = list(events)
            try:
                chat = get_or_create_session(
                    self.user,
                    conversation_id,
                    agent_id=str(agent_id or ""),
                )
            except PermissionError:
                R.logger.warning(
                    "Refusing to save conversation %s: owned by another user (requested by %s)",
                    conversation_id,
                    self.user,
                )
                return

            chat_messages = [
                R.ChatMessage(
                    conversation=chat,
                    sender=message["role"],
                    content=message["content"],
                )
                for message in turns
                if not is_ui_only_role(message.get("role"))
            ]
            # Idempotent replace: delete then insert current transcript.
            R.ChatMessage.objects.filter(conversation=chat).delete()
            R.ChatMessage.objects.bulk_create(chat_messages)
            try:
                touch_session(chat, turns, agent_id=str(agent_id or ""))
            except Exception:
                R.logger.exception("Failed to touch Django session %s", conversation_id)
            # #731: background semantic retitle when the title is still raw.
            from swarm.core.agent_sessions import schedule_session_retitle
            schedule_session_retitle(chat, messages=turns)

            R.IN_MEMORY_CONVERSATIONS[cache_key] = list(turns)
            R.IN_MEMORY_UI_EVENTS[cache_key] = list(events)
            R._save_agent_json(
                self.user,
                getattr(self, "active_agent", None) or getattr(self, "default_blueprint", None),
                turns,
                conversation_id=conversation_id,
                ui_events=events,
            )


    @database_sync_to_async
    def delete_conversation(self, conversation_id):
            """
            Delete the conversation from DB if empty.
            """
            cache_key = R._conversation_cache_key(self.user, conversation_id)
            try:
                chat = R.ChatConversation.objects.get(conversation_id=conversation_id, student=self.user)
                if not chat.messages.exists():  # Check if there are any messages before deleting
                    chat.delete()
                    if cache_key in R.IN_MEMORY_CONVERSATIONS:
                        del R.IN_MEMORY_CONVERSATIONS[cache_key]  # Cleanup memory cache
                    R.IN_MEMORY_UI_EVENTS.pop(cache_key, None)
            except R.ChatConversation.DoesNotExist:
                R.logger.warning(f"Attempted to delete non-existent conversation: {conversation_id} for user: {self.user}")
