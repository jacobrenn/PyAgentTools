#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["click"]
# ///
"""PyAgent external tool: calculator.

This script is auto-discovered by PyAgent when placed under
`~/.pyagent/tools/`. Each external tool is a runnable UV script
exposing two subcommands: `describe` and `invoke`.

Add or replace dependencies in the `# /// script` block above and they
will be installed by uv on first run, in an isolated venv that does not
affect the PyAgent install itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


TOOL_NAME = "calculator"
TOOL_DESCRIPTION = (
    "A simple arithmetic calculator that evaluates mathematical expressions. "
    "Supports basic operations like +, -, *, /, and parentheses."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "description": "The arithmetic expression to evaluate (e.g., '2 + 2' or '(10 * 5) / 2').",
        },
    },
    "required": ["input"],
}
TOOL_VERSION = "1"


def run_tool(*, input: str) -> str:
    """Evaluates a simple arithmetic expression.
    
    Return a string. PyAgent will forward it to the model as the tool
    result. Raise an exception or print to stderr + exit non-zero to
    signal an error.
    """
    try:
        # Using eval carefully here since this is a tool meant for the LLM.
        # In a production environment, a safer parser like ast.literal_eval 
        # or a custom parser would be preferred.
        # We restrict the global and local namespaces to prevent malicious code execution.
        allowed_names = {"__builtins__": {}}
        result = eval(input, allowed_names, {})
        return str(result)
    except Exception as exc:
        return f"Error evaluating expression: {exc}"


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
