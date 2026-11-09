"""
time_info.py — Current date and time utilities for system prompt injection.
"""
from datetime import datetime


def get_current_time_info() -> str:
    """Return a human-readable current date and time string."""
    now = datetime.now()
    return now.strftime("Current date and time: %A, %B %d, %Y at %I:%M %p")
