"""Local task board operations, used after explicit approval for mutations."""

import json
import tempfile
from pathlib import Path

from config import BASE_DIR

TASK_FILE = BASE_DIR / "database" / "tasks.json"


def manage_tasks(action: str, task: str = "") -> str:
    """Add, remove, list, or clear the local task board."""
    normalized_action = action.strip().lower()
    try:
        tasks = json.loads(TASK_FILE.read_text(encoding="utf-8")) if TASK_FILE.exists() else []
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read the task board: {error}") from error
    if not isinstance(tasks, list) or any(not isinstance(item, str) for item in tasks):
        raise RuntimeError("The task board has an invalid format.")

    if normalized_action == "list":
        if not tasks:
            return "No tasks currently on the board."
        return "Current Tasks:\n" + "\n".join(f"- {item}" for item in tasks)
    if normalized_action == "add" and task:
        tasks.append(task)
        result = f"Added task: '{task}'"
    elif normalized_action == "remove" and task:
        if task not in tasks:
            return f"Task '{task}' not found."
        tasks.remove(task)
        result = f"Removed task: '{task}'"
    elif normalized_action == "clear":
        tasks.clear()
        result = "All tasks cleared."
    else:
        raise ValueError("Use 'add', 'remove', 'list', or 'clear' with a valid task.")

    temporary_path: str | None = None
    try:
        TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=TASK_FILE.parent,
            prefix=".tasks-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(tasks, temporary_file, ensure_ascii=False, indent=4)
            temporary_file.flush()
        Path(temporary_path).replace(TASK_FILE)
    except OSError as error:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        raise RuntimeError(f"Could not save the task board: {error}") from error
    return result
