import re
import shutil
import subprocess


APPLICATION_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "paint": "mspaint.exe",
    "visual studio code": "code.exe",
    "vscode": "code.exe",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
}


def launch_application(app_name: str) -> str:
    """Launch a named Windows app or an executable found on PATH, without a shell."""
    normalized_name = " ".join(app_name.lower().split())
    if normalized_name in APPLICATION_ALIASES:
        executable_name = APPLICATION_ALIASES[normalized_name]
    elif re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._+-]{0,63}", app_name.strip()):
        executable_name = app_name.strip()
    else:
        return "Application name must be a simple app name, not a path or command."

    executable_path = shutil.which(executable_name)
    if not executable_path:
        return (
            f"Could not find '{app_name}' on PATH. "
            "Use a supported app name or add its executable to PATH."
        )

    try:
        subprocess.Popen([executable_path], shell=False)
        return f"Opening {app_name}."
    except OSError as error:
        return f"Failed to open {app_name}: {error}"
