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

    async def apply_message_reaction(self, reaction):
            """Toggle one emoji reaction on a transcript turn (#1411).

            Mux turns run off the socket read loop, so this waits for every
            in-flight turn lock before it mutates or saves the transcript.
            """
            while True:
                ids = self._transcript_lock_ids()
                acquired = []
                try:
                    for agent_id in ids:
                        lock = self._agent_lock(agent_id)
                        await lock.acquire()
                        acquired.append(lock)
                    if self._transcript_lock_ids() != ids:
                        continue
                    await self._apply_message_reaction_body(reaction)
                    return
                finally:
                    for lock in reversed(acquired):
                        lock.release()

    async def _apply_message_reaction_body(self, reaction):
            import json as _json

            from swarm.core.message_reactions import (
                ACTOR_USER,
                normalize_emoji,
                reaction_event,
                toggle_reaction,
            )

            if not isinstance(reaction, dict):
                R.logger.warning("Ignoring malformed chat reaction frame: %.200r", reaction)
                return
            index = reaction.get("index")
            emoji = normalize_emoji(reaction.get("emoji"))
            if type(index) is not int or emoji is None:
                R.logger.warning("Ignoring malformed chat reaction frame: %.200r", reaction)
                return
            if index < 0 or index >= len(self.messages):
                R.logger.warning(
                    "Ignoring chat reaction index %s (transcript length %s)",
                    index,
                    len(self.messages),
                )
                return
            current = dict(self.messages[index])
            rows = toggle_reaction(current, emoji, ACTOR_USER)
            if rows is None:
                return
            self.messages[index] = current
            conversation_id = getattr(self, "conversation_id", None)
            if conversation_id:
                await self.save_conversation(conversation_id, self.messages)
            event = reaction_event(
                index=index,
                emoji=emoji,
                actor=ACTOR_USER,
                reactions=rows,
                agent_id=str(
                    getattr(self, "active_agent", None)
                    or getattr(self, "default_blueprint", None)
                    or ""
                ),
            )
            try:
                await self.send(text_data=_json.dumps(event))
            except Exception:
                R.logger.debug("Failed to emit reaction event", exc_info=True)


    @database_sync_to_async
    def fetch_conversation(self, conversation_id):
            """Fetch transcript: cache, then Django, then one-way JSON migrate.

            Load order matches ``GET /chat/thread/`` (``swarm.core.thread_load``):

            0. On-mode mint (REQ-171C-4) — refuse reuse before any row load.
            1. In-memory cache keyed by ``(user_id, conversation_id)``.
            2. Django rows (source of truth) — keeps ``ts`` / ``edited``.
            3. JSON disk when Django is empty (one-way migrate onto Django).

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
            """Insert new tail rows and update edited turns in place (#1440).

            A composer send adds exactly one ``ChatMessage``. Disconnect
            persists the same transcript again without inserting duplicates.

            Lookup is by conversation_id PK only (avoids IntegrityError when the
            row exists for another student); ownership is then validated.

            A trashed thread loads as empty. Disconnect must not write that
            empty memory back over the canonical rows (#1440).
            """
            from swarm.core.chat_db import conversation_is_trashed

            if conversation_is_trashed(self.user, conversation_id):
                return

            from swarm.core.transcript_roles import split_store

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

            from swarm.core.chat_repository import sync_transcript

            sync_transcript(
                self.user,
                conversation_id,
                turns,
                agent_id=str(agent_id or ""),
                ui_events=events,
            )
            if chat is None:
                return
            try:
                touch_session(chat, turns, agent_id=str(agent_id or ""))
            except Exception:
                R.logger.exception("Failed to touch Django session %s", conversation_id)
            # #731: background semantic retitle when the title is still raw.
            from swarm.core.agent_sessions import schedule_session_retitle
            schedule_session_retitle(chat, messages=turns)

            from swarm.core.chat_db import load_db_thread

            # #1722 repro C: this socket's ``self.messages`` is the snapshot it
            # hydrated with. Anything another writer appended in the meantime is
            # not in it, so publishing that list *alone* truncated the thread
            # for every later reconnect. The database is canonical — re-read it
            # and add the rows this snapshot predates.
            #
            # Additive, not a replacement: the socket's own turn dicts carry the
            # metadata it was given (a client ``ts``, a title), and a
            # ``load_db_thread`` projection re-derives those from the row.
            # Concatenation keeps both, and can only ever make the cache
            # longer, which is the safe direction for a cache.
            canonical = load_db_thread(self.user, conversation_id)
            cached_turns = list(turns)
            if canonical:
                for row in list(canonical[0])[len(cached_turns) :]:
                    cached_turns.append(row)
            R.IN_MEMORY_CONVERSATIONS[cache_key] = cached_turns
            R.IN_MEMORY_UI_EVENTS[cache_key] = list(events)


    @database_sync_to_async
    def delete_conversation(self, conversation_id):
            """
            Delete the conversation from DB if empty.
            """
            cache_key = R._conversation_cache_key(self.user, conversation_id)
            try:
                chat = R.ChatConversation.objects.get(conversation_id=conversation_id, student=self.user)
                # Trash hides the transcript in memory. Do not drop the row.
                if getattr(chat, "trashed_at", None) is not None:
                    return
                if not chat.messages.exists():  # Check if there are any messages before deleting
                    chat.delete()
                    if cache_key in R.IN_MEMORY_CONVERSATIONS:
                        del R.IN_MEMORY_CONVERSATIONS[cache_key]  # Cleanup memory cache
                    R.IN_MEMORY_UI_EVENTS.pop(cache_key, None)
            except R.ChatConversation.DoesNotExist:
                R.logger.warning(f"Attempted to delete non-existent conversation: {conversation_id} for user: {self.user}")
