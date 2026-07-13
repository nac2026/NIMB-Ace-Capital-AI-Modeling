"""Per-session conversation memory backed by Redis.

Key pattern:   `chat:session:{session_id}`
Value:         JSON array of {"role": "user|assistant", "content": str}
TTL:           2 hours of inactivity (refreshed on every write)

Why Redis (not Postgres): session memory is ephemeral — if the user drops off
for a day, the next conversation is effectively new. Redis' native TTL handles
this for free. Postgres `query_traces` is the permanent audit log.

History is capped at MAX_TURNS; older turns drop off to bound token spend."""
from __future__ import annotations
import logging
from dataclasses import dataclass

from nrc_storage import RedisClient

_log = logging.getLogger("nrc_orchestrator.conversation")

MAX_TURNS = 10        # user+assistant pairs retained; older pairs drop off
SESSION_TTL_S = 7200  # 2 hours of inactivity


@dataclass
class ChatTurn:
    role: str      # 'user' or 'assistant'
    content: str


class ConversationStore:
    """Append-and-truncate history per session_id."""

    def __init__(self, redis: RedisClient | None = None):
        self._redis = redis or RedisClient()

    def _key(self, session_id: str) -> str:
        return f"chat:session:{session_id}"

    def load(self, session_id: str) -> list[ChatTurn]:
        """Return the session's chat history, oldest first. Empty if new session."""
        raw = self._redis.get_json(self._key(session_id))
        if not raw:
            return []
        return [ChatTurn(role=t["role"], content=t["content"]) for t in raw]

    def append(self, session_id: str, *, user: str, assistant: str) -> None:
        """Append one user+assistant pair. Refreshes the session TTL."""
        history = self.load(session_id)
        history.append(ChatTurn(role="user", content=user))
        history.append(ChatTurn(role="assistant", content=assistant))
        # Keep the most recent MAX_TURNS*2 messages (one turn = user + assistant).
        if len(history) > MAX_TURNS * 2:
            history = history[-MAX_TURNS * 2:]
        self._redis.set_json(
            self._key(session_id),
            [{"role": t.role, "content": t.content} for t in history],
            ttl_seconds=SESSION_TTL_S,
        )

    def clear(self, session_id: str) -> None:
        """Forget everything for a session — used by 'new chat' buttons."""
        self._redis.delete(self._key(session_id))
