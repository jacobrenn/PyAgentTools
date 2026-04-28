# /// script
# dependencies = [
#     "ollama",
#     "click",
# ]
# ///

import click
import json
import sys
import ollama

@click.group()
def cli():
    """Web Search Tool for PyAgent."""
    pass

@cli.command()
@click.option("--args-file", type=click.Path(exists=True), required=True, help="Path to JSON arguments file.")
def invoke(args_file):
    """Invoke the web search tool using Ollama."""
    try:
        with open(args_file, "r", encoding="utf-8") as f:
            args = json.load(f)
        
        query = args.get("query")
        if not query:
            print("Error: Missing 'query' argument.")
            sys.exit(1)

        # Use ollama.web_search to get results
        # Note: This assumes the local Ollama instance is configured with a search tool/plugin
        # that exposes 'web_search'.
        response = ollama.web_search(query=query)
        
        # Present the results cleanly
        print(json.dumps(response.dict(), indent=2))

    except Exception as e:
        print(f"Error during web search: {e}", file=sys.stderr)
        sys.exit(1)

@cli.command()
def describe():
    """Describe the tool manifest."""
    manifest = {
        "name": "web_search",
        "description": "Perform a web search to find current information on the internet.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web."
                }
            },
            "required": ["query"]
        },
        "version": "1.0.0"
    }
    print(json.dumps(manifest))

if __name__ == "__main__":
    cli()
