"""One-time approvals and a local audit trail for assistant side effects."""

import json
import logging
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import BASE_DIR

logger = logging.getLogger(__name__)

AUDIT_FILE = BASE_DIR / "database" / "action_audit.json"
APPROVAL_TTL_SECONDS = 300
MAX_AUDIT_EVENTS = 500
APPROVAL_RESULT_PREFIX = "JARVIS_APPROVAL_REQUIRED:"
_LOCK = threading.RLock()
_pending_actions: dict[str, dict[str, Any]] = {}

_ACTION_DESCRIPTIONS = {
    "task_add": "Add a task to the local task board",
    "task_remove": "Remove a task from the local task board",
    "task_clear": "Clear the local task board",
    "memory_remember": "Save a note to local memory",
    "memory_forget": "Delete a note from local memory",
    "project_save": "Save a project plan locally",
    "project_update": "Update a locally saved project plan",
    "project_delete": "Delete a locally saved project plan",
    "system_set_volume": "Change the system volume",
    "system_set_brightness": "Change the screen brightness",
    "image_generate": "Generate an image using the configured image provider and save it locally",
}


class ApprovalNotFoundError(ValueError):
    """Raised when an approval ID is unknown or has already been resolved."""


class ApprovalExpiredError(ValueError):
    """Raised when the approval period has elapsed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_audit_events() -> list[dict[str, str]]:
    if not AUDIT_FILE.exists():
        return []
    try:
        events = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read the action audit log: {error}") from error
    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or any(not isinstance(value, str) for value in event.values())
        for event in events
    ):
        raise RuntimeError("The action audit log has an invalid format.")
    return events


def _write_audit_events(events: list[dict[str, str]]) -> None:
    temporary_path: str | None = None
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=AUDIT_FILE.parent,
            prefix=".action-audit-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(events[-MAX_AUDIT_EVENTS:], temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
        Path(temporary_path).replace(AUDIT_FILE)
    except OSError as error:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        raise RuntimeError(f"Could not write the action audit log: {error}") from error


def _record_event(action_id: str, action_type: str, event: str) -> None:
    events = _read_audit_events()
    events.append(
        {
            "action_id": action_id,
            "action_type": action_type,
            "event": event,
            "timestamp": _utc_now().isoformat(),
        }
    )
    _write_audit_events(events)


def _expire_pending_actions() -> None:
    now = _utc_now()
    expired_ids = [
        action_id
        for action_id, action in _pending_actions.items()
        if action["expires_at"] <= now
    ]
    for action_id in expired_ids:
        action = _pending_actions.pop(action_id)
        _record_event(action_id, action["action_type"], "expired")


def request_approval(
    action_type: str,
    payload: dict[str, Any],
    details: str = "",
) -> str:
    """Queue an allowlisted action and return a marker for the streaming layer."""
    if action_type not in _ACTION_DESCRIPTIONS:
        raise ValueError("This action type cannot be approved.")

    action_id = uuid4().hex
    now = _utc_now()
    expires_at = now + timedelta(seconds=APPROVAL_TTL_SECONDS)
    event = {
        "id": action_id,
        "action_type": action_type,
        "description": _ACTION_DESCRIPTIONS[action_type],
        "details": details[:500],
        "expires_at": expires_at.isoformat(),
    }

    with _LOCK:
        _expire_pending_actions()
        _record_event(action_id, action_type, "approval_requested")
        _pending_actions[action_id] = {
            "action_type": action_type,
            "payload": payload,
            "details": details[:500],
            "expires_at": expires_at,
        }

    return APPROVAL_RESULT_PREFIX + json.dumps(event)


def get_approval_event(tool_result: Any) -> dict[str, str] | None:
    """Decode a pending-action marker returned by an assistant tool."""
    if not isinstance(tool_result, str) or not tool_result.startswith(APPROVAL_RESULT_PREFIX):
        return None
    try:
        event = json.loads(tool_result[len(APPROVAL_RESULT_PREFIX):])
    except json.JSONDecodeError as error:
        raise RuntimeError("The pending approval event was malformed.") from error
    if not isinstance(event, dict) or any(not isinstance(value, str) for value in event.values()):
        raise RuntimeError("The pending approval event had an invalid format.")
    return event


def _execute_action(action_type: str, payload: dict[str, Any]) -> str:
    if action_type.startswith("task_"):
        from app.services.task_service import manage_tasks

        action = action_type.removeprefix("task_")
        return manage_tasks(action, payload.get("task", ""))

    if action_type.startswith("memory_"):
        from app.services.memory_service import manage_memory

        action = action_type.removeprefix("memory_")
        return manage_memory(action, payload.get("information", ""))

    if action_type.startswith("project_"):
        from app.services.project_plan_service import manage_project_plans

        action = action_type.removeprefix("project_")
        return manage_project_plans(
            action,
            payload.get("project_name", ""),
            payload.get("plan", ""),
        )

    if action_type == "system_set_volume":
        from app.services.system_control_service import set_volume

        return set_volume(payload["value"])

    if action_type == "system_set_brightness":
        from app.services.system_control_service import set_brightness

        return set_brightness(payload["value"])

    if action_type == "image_generate":
        from app.services.image_generation_service import generate_image_asset

        return generate_image_asset(payload["prompt"])

    raise ValueError("This action type cannot be executed.")


def resolve_approval(action_id: str, approve: bool) -> dict[str, str]:
    """Approve or deny a pending action; approved actions are consumed once."""
    with _LOCK:
        action = _pending_actions.get(action_id)
        if action and action["expires_at"] <= _utc_now():
            _pending_actions.pop(action_id)
            _record_event(action_id, action["action_type"], "expired")
            raise ApprovalExpiredError("This approval expired. Request the action again.")
        _expire_pending_actions()
        action = _pending_actions.get(action_id)
        if action is None:
            raise ApprovalNotFoundError("Approval not found, expired, or already resolved.")
        if not approve:
            _record_event(action_id, action["action_type"], "denied")
            _pending_actions.pop(action_id)
            return {"status": "denied", "result": "Action denied; no change was made."}

        _record_event(action_id, action["action_type"], "approved")
        _pending_actions.pop(action_id)

    try:
        result = _execute_action(action["action_type"], action["payload"])
    except Exception:
        with _LOCK:
            _record_event(action_id, action["action_type"], "failed")
        logger.exception("Approved action failed: %s", action["action_type"])
        raise

    with _LOCK:
        _record_event(action_id, action["action_type"], "executed")
    response = {"status": "executed", "result": result}
    if action["action_type"] == "image_generate":
        response["image"] = result
    return response


def get_audit_events(limit: int = 100) -> list[dict[str, str]]:
    """Return a bounded list of recent audit events without action payloads."""
    if not 1 <= limit <= MAX_AUDIT_EVENTS:
        raise ValueError(f"Limit must be between 1 and {MAX_AUDIT_EVENTS}.")
    with _LOCK:
        _expire_pending_actions()
        events = _read_audit_events()
    return list(reversed(events[-limit:]))


def get_pending_approvals() -> list[dict[str, str]]:
    """Return pending confirmation cards so the local UI can recover after reload."""
    with _LOCK:
        _expire_pending_actions()
        return [
            {
                "id": action_id,
                "action_type": action["action_type"],
                "description": _ACTION_DESCRIPTIONS[action["action_type"]],
                "details": action["details"],
                "expires_at": action["expires_at"].isoformat(),
            }
            for action_id, action in sorted(
                _pending_actions.items(),
                key=lambda item: item[1]["expires_at"],
            )
        ]
