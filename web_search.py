#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "ollama",
#     "click",
# ]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
import ollama


TOOL_NAME = "web_search"
TOOL_DESCRIPTION = "Perform a web search to find current information on the internet."
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query to look up on the web.",
        }
    },
    "required": ["query"],
}
TOOL_VERSION = "1.0.0"


@click.group()
def cli() -> None:
    """Web Search Tool for PyAgent."""


def _jsonable(value: Any) -> Any:
    """Convert Ollama/Pydantic-ish responses into JSON-serializable data."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def run_tool(query: str) -> str:
    """Invoke Ollama web search and return JSON output."""
    if not query or not query.strip():
        raise ValueError("Missing 'query' argument.")

    response = ollama.web_search(query=query)
    return json.dumps(_jsonable(response), ensure_ascii=False, indent=2)


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
    "--args",
    "args_json",
    required=False,
    help="JSON object containing the tool arguments.",
)
@click.option(
    "--args-file",
    "args_file",
    required=False,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a JSON file containing the tool arguments. Deprecated; prefer --args.",
)
def invoke(args_json: str | None, args_file: Path | None) -> None:
    """Run the tool with arguments supplied via ``--args`` or ``--args-file``."""
    if args_json is not None and args_file is not None:
        click.echo("Use either --args or --args-file, not both.", err=True)
        sys.exit(2)

    if args_json is not None:
        source = "--args"
        raw_arguments = args_json
    elif args_file is not None:
        source = "--args-file"
        try:
            raw_arguments = args_file.read_text(encoding="utf-8")
        except OSError as exc:
            click.echo(f"Failed to read --args-file: {exc}", err=True)
            sys.exit(2)
    else:
        click.echo("Missing tool arguments. Provide --args JSON, or --args-file for legacy callers.", err=True)
        sys.exit(2)

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        click.echo(f"Failed to parse {source} as JSON: {exc}", err=True)
        sys.exit(2)

    if not isinstance(arguments, dict):
        click.echo(f"{source} must contain a JSON object.", err=True)
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
