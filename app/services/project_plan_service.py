"""Local, user-controlled storage for software project plans."""

import json
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR

PROJECT_PLANS_DIR = BASE_DIR / "database" / "project_plans"
MAX_PROJECT_PLANS = 100
MAX_PROJECT_NAME_LENGTH = 80
MAX_PROJECT_PLAN_LENGTH = 30_000
_LOCK = threading.RLock()
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _validate_project_name(name: str) -> tuple[str, str]:
    normalized_name = name.strip()
    if (
        not normalized_name
        or len(normalized_name) > MAX_PROJECT_NAME_LENGTH
        or not normalized_name[0].isalnum()
        or any(not (character.isalnum() or character in " _-") for character in normalized_name)
    ):
        raise ValueError(
            "Project names must start with a letter or number and contain only "
            "letters, numbers, spaces, underscores, or hyphens."
        )

    slug = re.sub(r"[\s_-]+", "-", normalized_name.casefold()).strip("-")
    if slug.upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError("That project name is reserved by Windows.")
    return normalized_name, slug


def validate_project_plan_request(action: str, project_name: str, plan: str = "") -> None:
    """Validate a project-plan mutation without reading or changing saved plans."""
    normalized_action = action.strip().lower()
    if normalized_action not in {"save", "update", "delete"}:
        raise ValueError("Action must be 'save', 'update', 'list', 'read', or 'delete'.")
    _validate_project_name(project_name)
    if normalized_action in {"save", "update"}:
        if not plan.strip():
            raise ValueError("Provide the project plan content.")
        if len(plan) > MAX_PROJECT_PLAN_LENGTH:
            raise ValueError(
                f"Project plans must be {MAX_PROJECT_PLAN_LENGTH:,} characters or fewer."
            )


def _read_records(directory: Path) -> list[dict[str, str]]:
    if not directory.exists():
        return []
    try:
        plan_files = sorted(directory.glob("*.json"))
        records = []
        for plan_file in plan_files:
            data: Any = json.loads(plan_file.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("name"), str)
                or not isinstance(data.get("plan"), str)
                or not isinstance(data.get("created_at"), str)
                or not isinstance(data.get("updated_at"), str)
            ):
                raise RuntimeError(f"Saved project plan has an invalid format: {plan_file.name}")
            records.append(data)
        return records
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read saved project plans: {error}") from error


def _write_record(record: dict[str, str], path: Path) -> None:
    temporary_path: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".project-plan-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(record, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
        Path(temporary_path).replace(path)
    except OSError as error:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        raise RuntimeError(f"Could not save project plan: {error}") from error


def manage_project_plans(
    action: str,
    project_name: str = "",
    plan: str = "",
) -> str:
    """Save, update, list, read, or delete project plans stored locally."""
    normalized_action = action.strip().lower()
    if normalized_action not in {"save", "update", "list", "read", "delete"}:
        raise ValueError("Action must be 'save', 'update', 'list', 'read', or 'delete'.")

    if normalized_action == "list":
        with _LOCK:
            records = _read_records(PROJECT_PLANS_DIR)
        if not records:
            return "There are no saved project plans."
        names = sorted((record["name"] for record in records), key=str.casefold)
        return "Saved project plans:\n" + "\n".join(f"- {name}" for name in names)

    normalized_name, slug = _validate_project_name(project_name)
    if normalized_action in {"save", "update"}:
        if not plan.strip():
            raise ValueError("Provide the project plan content.")
        if len(plan) > MAX_PROJECT_PLAN_LENGTH:
            raise ValueError(
                f"Project plans must be {MAX_PROJECT_PLAN_LENGTH:,} characters or fewer."
            )

    with _LOCK:
        records = _read_records(PROJECT_PLANS_DIR)
        matching_record = next(
            (record for record in records if record["name"].casefold() == normalized_name.casefold()),
            None,
        )
        plan_path = PROJECT_PLANS_DIR / f"{slug}.json"

        if normalized_action == "read":
            if matching_record is None:
                return "I couldn't find that saved project plan."
            return f"Project plan: {matching_record['name']}\n\n{matching_record['plan']}"

        if normalized_action == "delete":
            if matching_record is None:
                return "I couldn't find that saved project plan."
            existing_path = PROJECT_PLANS_DIR / f"{_validate_project_name(matching_record['name'])[1]}.json"
            try:
                existing_path.unlink()
            except OSError as error:
                raise RuntimeError(f"Could not delete project plan: {error}") from error
            return f"Deleted the project plan '{matching_record['name']}'."

        if normalized_action == "save":
            if matching_record is not None:
                return "That project plan already exists. Use 'update' to replace it."
            if plan_path.exists():
                return "That project name conflicts with an existing plan name."
            if len(records) >= MAX_PROJECT_PLANS:
                return f"You can save at most {MAX_PROJECT_PLANS} project plans."

        if normalized_action == "update":
            if matching_record is None:
                return "I couldn't find that saved project plan to update."
            existing_slug = _validate_project_name(matching_record["name"])[1]
            plan_path = PROJECT_PLANS_DIR / f"{existing_slug}.json"

        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "name": matching_record["name"] if matching_record else normalized_name,
            "plan": plan.strip(),
            "created_at": matching_record["created_at"] if matching_record else timestamp,
            "updated_at": timestamp,
        }
        _write_record(record, plan_path)
        if normalized_action == "update":
            return f"Updated the project plan '{record['name']}'."
        return f"Saved the project plan '{record['name']}' locally."
