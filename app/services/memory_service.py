"""Explicit, user-controlled personal notes stored locally as JSON."""

import json
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR

MEMORY_FILE = BASE_DIR / "database" / "memory.json"
MAX_MEMORIES = 100
MAX_MEMORY_LENGTH = 500
MAX_CONTEXT_MEMORIES = 20
MAX_CONTEXT_LENGTH = 6000
_LOCK = threading.RLock()
_SENSITIVE_DATA_PATTERN = re.compile(
    r"\b(password|passcode|api[\s_-]?key|secret|access token|private key)\b",
    re.IGNORECASE,
)


def _read_memories(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or MEMORY_FILE
    if not path.exists():
        return []
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read saved memories: {error}") from error
    if not isinstance(content, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("text"), str)
        or not isinstance(item.get("created_at"), str)
        for item in content
    ):
        raise RuntimeError("Saved memories have an invalid format.")
    return content


def _write_memories(
    memories: list[dict[str, str]],
    path: Path | None = None,
) -> None:
    path = path or MEMORY_FILE
    temporary_path: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".memory-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(memories, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
        Path(temporary_path).replace(path)
    except OSError as error:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        raise RuntimeError(f"Could not save memories: {error}") from error


def manage_memory(action: str, information: str = "") -> str:
    """Remember, list, or forget user notes; deletion requires an exact match."""
    normalized_action = action.strip().lower()
    note = information.strip()

    validate_memory_request(normalized_action, note)

    with _LOCK:
        memories = _read_memories()
        if normalized_action == "remember":
            if any(memory["text"].casefold() == note.casefold() for memory in memories):
                return "I already have that note saved."
            memories.append(
                {
                    "text": note,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            memories = memories[-MAX_MEMORIES:]
            _write_memories(memories)
            return "Saved that note locally."

        if normalized_action == "list":
            if not memories:
                return "There are no saved notes."
            return "Saved notes:\n" + "\n".join(
                f"- {memory['text']}" for memory in memories
            )

        remaining = [
            memory for memory in memories
            if memory["text"].casefold() != note.casefold()
        ]
        if len(remaining) == len(memories):
            return "I couldn't find an exact matching saved note."
        _write_memories(remaining)
        return "Removed the matching note."


def validate_memory_request(action: str, information: str = "") -> None:
    """Validate a memory action without reading or changing the saved notes."""
    normalized_action = action.strip().lower()
    note = information.strip()
    if normalized_action not in {"remember", "list", "forget"}:
        raise ValueError("Action must be 'remember', 'list', or 'forget'.")
    if normalized_action == "remember":
        if not note:
            raise ValueError("Provide the note you want remembered.")
        if len(note) > MAX_MEMORY_LENGTH:
            raise ValueError(f"Notes must be {MAX_MEMORY_LENGTH} characters or fewer.")
        if _SENSITIVE_DATA_PATTERN.search(note):
            raise ValueError("Do not save passwords, API keys, tokens, or private keys.")
    if normalized_action == "forget" and not note:
        raise ValueError("Provide the exact note you want forgotten.")


def get_memory_context(path: Path | None = None) -> str:
    """Return a bounded set of saved notes for chat context."""
    with _LOCK:
        memories = _read_memories(path)
    notes = [memory["text"] for memory in memories[-MAX_CONTEXT_MEMORIES:]]
    context = "\n".join(f"- {note}" for note in notes)
    if len(context) > MAX_CONTEXT_LENGTH:
        context = context[-MAX_CONTEXT_LENGTH:]
    return f"User-saved notes (private local memory):\n{context}" if context else ""
