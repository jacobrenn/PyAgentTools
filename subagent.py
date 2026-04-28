#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["click", "ollama"]
# ///
"""PyAgent external tool: subagent.

This script is auto-discovered by PyAgent when placed under
``~/.pyagent/tools/``. Each external tool is a runnable UV script
exposing two subcommands: ``describe`` and ``invoke``.

Add or replace dependencies in the ``# /// script`` block above and they
will be installed by uv on first run, in an isolated venv that does not
affect the PyAgent install itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import ollama

# Directory to store session histories
SESSIONS_DIR = Path.home() / ".pyagent" / "subagent_sessions"

TOOL_NAME = "subagent"
TOOL_DESCRIPTION = (
    "Invoke a specialized sub-agent (gemma4:26b) to process a task. "
    "You can provide a 'session_id' to maintain a conversation across multiple calls."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "description": "The prompt or task to send to the sub-agent.",
        },
        "session_id": {
            "type": "string",
            "description": "Optional ID to track conversation history. If omitted, it will be a single-turn interaction.",
        },
    },
    "required": ["input"],
}
TOOL_VERSION = "2"


def run_tool(*, input: str, session_id: str | None = None) -> str:
    """Invokes the gemma4:26b model via the Ollama SDK with optional session history."""
    try:
        messages = [{'role': 'user', 'content': input}]
        
        if session_id:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            session_file = SESSIONS_DIR / f"{session_id}.json"
            
            if session_file.exists():
                try:
                    history = json.loads(session_file.read_text(encoding="utf-8"))
                    messages = history + messages
                except (json.JSONDecodeError, OSError):
                    # If history is corrupted, start fresh
                    pass
            
            # Get response
            response = ollama.chat(
                model='gemma4:26b',
                messages=messages
            )
            content = response['message']['content']
            
            # Save updated history
            messages.append({'role': 'assistant', 'content': content})
            session_file.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")
            return content
        else:
            # Single turn
            response = ollama.chat(
                model='gemma4:26b',
                messages=messages
            )
            return response['message']['content']
            
    except Exception as e:
        return f"Error invoking sub-agent: {str(e)}"


@click.group()
def cli() -> None:
    """PyAgent external tool entry point."""


@cli.command()
def describe() -> None:
    """Print the JSON manifest used by PyAgent to register this tool."""
    click.echo(
        json.dumps(
            {
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "parameters": TOOL_PARAMETERS,
                "version": TOOL_VERSION,
            },
            ensure_ascii=False,
        )
    )


@cli.command()
@click.option(
    "--args-file",
    "args_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a JSON file containing the tool arguments.",
)
def invoke(args_file: Path) -> None:
    """Run the tool with arguments read from ``--args-file``."""
    try:
        arguments = json.loads(args_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        click.echo(f"Failed to read --args-file: {exc}", err=True)
        sys.exit(2)

    if not isinstance(arguments, dict):
        click.echo("--args-file must contain a JSON object.", err=True)
        sys.exit(2)

    try:
        result = run_tool(**arguments)
    except TypeError as exc:
        click.echo(f"Invalid tool arguments: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        click.echo(f"Tool error: {exc}", err=True)
        sys.exit(1)

    click.echo(result if result is not None else "")


if __name__ == "__main__":
    cli()
