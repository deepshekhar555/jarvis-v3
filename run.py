"""
run.py — Entry point for J.A.R.V.I.S backend server.
Run with: python run.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def main():
    console.print()
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]     J.A.R.V.I.S[/bold cyan]\n"
            "[dim]Just A Rather Very Intelligent System[/dim]\n\n"
            "[green]>  Starting local server on http://127.0.0.1:8000[/green]\n"
            "[dim]Open your browser and go to http://localhost:8000[/dim]"
        ),
        title="[bold white]JARVIS AI[/bold white]",
        border_style="cyan",
        expand=False,
        padding=(1, 4)
    ))
    console.print()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="warning",
    )

if __name__ == "__main__":
    main()
