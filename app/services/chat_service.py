"""
chat_service.py — Session management and conversation history storage.
Each session is a UUID. Conversations are saved as JSON files on disk.
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# In-memory session store: { session_id: [{"role": ..., "content": ...}, ...] }
_sessions: Dict[str, List[Dict]] = {}


def create_session() -> str:
    """Create a new session and return its ID."""
    session_id = str(uuid.uuid4())
    _sessions[session_id] = []
    return session_id


def get_session(session_id: str) -> Optional[List[Dict]]:
    """Get the message history for a session. Load from disk if not in memory."""
    if session_id in _sessions:
        return _sessions[session_id]
    # Try loading from disk
    loaded = _load_session_from_disk(session_id)
    if loaded is not None:
        _sessions[session_id] = loaded
        return loaded
    return None


def get_or_create_session(session_id: Optional[str]) -> str:
    """Get existing session or create a new one. Returns session_id."""
    if session_id:
        history = get_session(session_id)
        if history is not None:
            return session_id
    return create_session()


def add_message(session_id: str, role: str, content: str):
    """Add a message to a session and persist to disk."""
    from config import MAX_CHAT_HISTORY_TURNS
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })
    # Trim to max turns (each turn = user + assistant = 2 messages)
    max_messages = MAX_CHAT_HISTORY_TURNS * 2
    if len(_sessions[session_id]) > max_messages:
        _sessions[session_id] = _sessions[session_id][-max_messages:]
    # Persist
    _save_session_to_disk(session_id)


def get_history_messages(session_id: str) -> List[Dict]:
    """Get history formatted for LangChain (without timestamps)."""
    history = _sessions.get(session_id, [])
    return [{"role": m["role"], "content": m["content"]} for m in history]


def _save_session_to_disk(session_id: str):
    """Save session history to a JSON file."""
    try:
        from config import CHATS_DATA_DIR
        file_path = CHATS_DATA_DIR / f"{session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(_sessions[session_id], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Could not save session %s to disk: %s", session_id, e)


def _load_session_from_disk(session_id: str) -> Optional[List[Dict]]:
    """Load session history from disk."""
    try:
        from config import CHATS_DATA_DIR
        file_path = CHATS_DATA_DIR / f"{session_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Could not load session %s from disk: %s", session_id, e)
    return None
