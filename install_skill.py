#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["click", "requests"]
# ///
"""PyAgent external tool: install_skill.

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
import shutil
import requests
from pathlib import Path

import click


TOOL_NAME = "install_skill"
TOOL_DESCRIPTION = (
    "Installs a new skill into the PyAgent skills directory (~/.pyagent/skills). "
    "Can install from a local file path or a URL (GitHub raw, Gists, etc.)."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "The path to a local file or a URL to a remote skill file.",
        },
    },
    "required": ["source"],
}
TOOL_VERSION = "1"


def run_tool(*, source: str) -> str:
    """Installs a skill from a local path or remote URL into ~/.pyagent/skills."""
    skills_dir = Path("~/.pyagent/skills").expanduser()
    skills_dir.mkdir(parents=True, exist_ok=True)

    if source.startswith(("http://", "https://")):
        # Remote installation
        try:
            response = requests.get(source, timeout=10)
            response.raise_for_status()

            # Determine filename from URL
            filename = source.split("/")[-1]
            if not filename or "." not in filename:
                filename = "installed_skill.py"
            if not filename.endswith(".py"):
                filename += ".py"

            dest_path = skills_dir / filename
            dest_path.write_text(response.text, encoding="utf-8")
            return f"Successfully downloaded and installed skill from {source} to {dest_path}"
        except Exception as e:
            raise RuntimeError(f"Failed to download skill from {source}: {e}")
    else:
        # Local installation
        src_path = Path(source).expanduser().resolve()
        if not src_path.is_file():
            raise FileNotFoundError(f"Source file not found: {src_path}")

        dest_path = skills_dir / src_path.name
        shutil.copy2(src_path, dest_path)
        return f"Successfully copied local skill from {src_path} to {dest_path}"


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
