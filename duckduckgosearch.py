#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["click", "ddgs"]
# ///
"""PyAgent external tool: duckduckgosearch.

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
from ddgs import DDGS

TOOL_NAME = "duckduckgosearch"
TOOL_DESCRIPTION = (
    "Performs a web search using DuckDuckGo to retrieve current information "
    "from the internet. Returns a list of results including titles, URLs, and snippets."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "description": "The search query to look up on the web.",
        },
    },
    "required": ["input"],
}
TOOL_VERSION = "1"


def run_tool(*, input: str) -> str:
    """Uses the DuckDuckGo Search SDK to fetch results."""
    query = input.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
    except Exception as e:
        raise RuntimeError(f"DuckDuckGo search failed: {e}") from e

    if not results:
        return "No results found for the given query."

    formatted_results = []
    for i, res in enumerate(results, 1):
        title = res.get("title", "Untitled")
        url = res.get("href") or res.get("url") or "No URL provided"
        snippet = res.get("body") or res.get("snippet") or "No snippet available."
        formatted_results.append(f"{i}. {title}\nURL: {url}\nSnippet: {snippet}")

    return "\n\n".join(formatted_results)


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
    required=True,
    help="JSON object containing the tool arguments.",
)
def invoke(args_json: str | None = None) -> None:
    """Run the tool with arguments supplied via ``--args``."""
    if not args_json:
        click.echo("Missing tool arguments. Provide --args as a JSON string.", err=True)
        sys.exit(2)

    try:
        arguments = json.loads(args_json)
    except json.JSONDecodeError as exc:
        click.echo(f"Failed to parse {args_json} as JSON: {exc}", err=True)
        sys.exit(2)

    if not isinstance(arguments, dict):
        click.echo("--args must contain a JSON object.", err=True)
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
