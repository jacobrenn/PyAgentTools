#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click",
#     "google-api-python-client",
#     "google-auth-oauthlib",
#     "google-auth-httplib2",
# ]
# ///
"""PyAgent external tool: google_calendar.

This script allows PyAgent to read and create events in the user's Google Calendar.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import click
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

TOOL_NAME = "google_calendar"
TOOL_DESCRIPTION = (
    "Interacts with the user's Google Calendar. "
    "The 'input' parameter should be a JSON string with an 'action' ('list' or 'create'). "
    "For 'list', it returns the next 10 events. "
    "For 'create', provide 'summary', 'start_time' (ISO format), 'end_time' (ISO format), "
    "and optionally 'description' and 'attendees' (a list of email addresses). "
    "If no timezone is specified in the timestamps, the system's local time will be used. "
    "It will automatically add a Google Meet link."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "description": "JSON string containing action and parameters. e.g. {'action': 'list'} or {'action': 'create', 'summary': 'Meeting', 'start_time': '2023-10-01T10:00:00Z', 'end_time': '2023-10-01T11:00:00Z'}",
        },
    },
    "required": ["input"],
}
TOOL_VERSION = "1"

# Updated scope to allow writing/creating events
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = Path.home() / ".pyagent" / "token_calendar.json"
CREDENTIALS_PATH = Path.home() / "Downloads" / "credentials.json"

def get_calendar_service():
    creds = None
    token_path = TOKEN_PATH
    creds_path = CREDENTIALS_PATH

    token_path.parent.mkdir(parents=True, exist_ok=True)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(f"credentials.json not found at {creds_path}")

            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

def run_tool(*, input: str) -> str:
    """Processes the calendar action."""
    try:
        service = get_calendar_service()
        params = json.loads(input)
        action = params.get("action")

        if action == "list":
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            if not events:
                return "No upcoming events found."
            
            summaries = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                summaries.append(f"{start}: {event.get('summary', 'No Title')}")
            return "\n".join(summaries)

        elif action == "create":
            summary = params.get("summary")
            start_time = params.get("start_time")
            end_time = params.get("end_time")

            # Handle naive datetimes by assuming local system timezone
            for time_val in [start_time, end_time]:
                if time_val:
                    try:
                        dt = datetime.datetime.fromisoformat(time_val)
                        if dt.tzinfo is None:
                            # Attach local timezone if none provided
                            dt = dt.astimezone()
                            # Update value back to ISO format with timezone
                            if time_val == start_time:
                                start_time = dt.isoformat()
                            else:
                                end_time = dt.isoformat()
                    except ValueError:
                        pass # Leave as is if not ISO format
            description = params.get("description", "")
            attendees = params.get("attendees", [])

            if not all([summary, start_time, end_time]):
                return "Missing required parameters: summary, start_time, and end_time are all required for creation."

            event_body = {
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
                "attendees": [{"email": email} for email in attendees],
                "conferenceData": {
                    "createRequest": {
                        "requestId": f"pyagent-{datetime.datetime.now().timestamp()}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"}
                    }
                },
            }

            event = service.events().insert(
                calendarId="primary", 
                body=event_body, 
                conferenceDataVersion=1
            ).execute()
            
            meet_link = event.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", "No meet link generated.")
            return f"Event created: {event.get('htmlLink')}\nGoogle Meet: {meet_link}"

        else:
            return f"Unsupported action: {action}. Please use 'list' or 'create'."

    except json.JSONDecodeError:
        return "Invalid JSON provided in input."
    except HttpError as error:
        return f"An API error occurred: {error}"
    except Exception as exc:
        return f"An unexpected error occurred: {exc}"


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
