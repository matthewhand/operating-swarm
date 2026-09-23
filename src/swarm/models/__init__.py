import uuid

from django.db import models


class ChatConversation(models.Model):
    """One chat session scoped to an agent (REQ-105).

    Messages, info-blocks, and compact summaries belong to this row — not
    a loose agent-global blob. ``cli_session_id`` binds a CLI provider id
    when #468 imports; this model does not list provider sessions.
    """

    conversation_id = models.CharField(max_length=255, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    student = models.ForeignKey("auth.User", on_delete=models.CASCADE, blank=True, null=True)
    agent_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    snippet = models.CharField(max_length=255, blank=True, default="")
    labels = models.JSONField(blank=True, default=list)
    cli_session_id = models.CharField(max_length=128, blank=True, default="")
    context_meta = models.JSONField(blank=True, default=dict)

    class Meta:
        app_label = "swarm"
        verbose_name = "Chat Conversation"
        verbose_name_plural = "Chat Conversations"
        indexes = [
            models.Index(fields=["student", "agent_id", "-updated_at"], name="swarm_chat_agent_upd"),
        ]

    def __str__(self):
        return f"ChatConversation({self.conversation_id})"

    @property
    def messages(self):
        return self.chat_messages.all()

class ChatMessage(models.Model):
    """Stores individual chat messages within a conversation."""
    conversation = models.ForeignKey(ChatConversation, related_name="chat_messages", on_delete=models.CASCADE)
    sender = models.CharField(max_length=50)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    tool_call_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["timestamp"]
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"

    def __str__(self):
        return self.content[:50]


class ChatAttachment(models.Model):
    """Uploaded file attached to the next chat send (REQ-38).

    Bytes live under ``SWARM_USER_DATA_DIR/attachments`` (or
    ``SWARM_ATTACHMENTS_DIR``), keyed by owner + id. SQLite holds metadata
    only — no Neon, no secrets in fixtures.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="chat_attachments",
    )
    conversation_id = models.CharField(max_length=255, blank=True, default="")
    original_name = models.CharField(max_length=512)
    content_type = models.CharField(max_length=255, blank=True, default="")
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "swarm"
        verbose_name = "Chat Attachment"
        verbose_name_plural = "Chat Attachments"
        ordering = ["created_at"]

    def __str__(self):
        return f"ChatAttachment({self.original_name})"


class ConversationSummary(models.Model):
    """Nested compact of a conversation span (REQ-37).

    Raw turns stay in ``ChatMessage`` / JSON on disk. This row is the
    summarised equivalent used as model context going forward.
    ``span`` is inclusive raw-transcript offsets: ``{"start": int, "end": int}``.
    ``parent_summary`` points at an earlier summary nested inside this one.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        related_name="summaries",
        on_delete=models.CASCADE,
    )
    span = models.JSONField(default=dict)
    parent_summary = models.ForeignKey(
        "self",
        related_name="child_summaries",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    body = models.TextField()
    # #214: unticked = transcript stays for humans, but the summary (and its
    # span) stops feeding model context — a lightweight "new chat".
    include_in_context = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "swarm"
        ordering = ["created_at", "id"]
        verbose_name = "Conversation Summary"
        verbose_name_plural = "Conversation Summaries"

    def __str__(self):
        return f"ConversationSummary({self.pk}, {self.conversation_id})"


# Marketplace models live in a submodule; import them here so they are always
# registered with Django when the app loads. Otherwise a stray import of
# swarm.models.core_models at test collection registers them without
# migrations and breaks test-database serialization.
from swarm.models.core_models import (  # noqa: E402
    Blueprint,
    MarketplaceIndex,
    MCPConfig,
)
from swarm.models.herdr import HerdrAgent  # noqa: E402
from swarm.models.preferences import UserPreference  # noqa: E402

__all__ = [
    "ChatConversation",
    "ChatMessage",
    "ChatAttachment",
    "ConversationSummary",
    "Blueprint",
    "MCPConfig",
    "MarketplaceIndex",
    "HerdrAgent",
    "UserPreference",
]

