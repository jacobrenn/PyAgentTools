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
"""PyAgent external tool: gmail.

This script allows PyAgent to read, send, reply to, and modify emails in the user's Gmail account.
"""

from __future__ import annotations

import os
import json
import sys
import base64
from pathlib import Path
from email.mime.text import MIMEText
from email.utils import parseaddr

import click
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

TOOL_NAME = "gmail"
TOOL_DESCRIPTION = (
    "Manages Gmail messages. Actions include 'search' (find emails), "
    "'read' (fetch the full content of a specific email), 'send' (send a new email), "
    "'reply' (reply to a specific message), and 'mark_read' (mark a message as read)."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "The action to perform: 'search', 'read', 'send', 'reply', or 'mark_read'.",
            "enum": ["search", "read", "send", "reply", "mark_read"],
        },
        "query": {
            "type": "string",
            "description": "Gmail search query for 'search' action. Leave empty for recent mail.",
        },
        "recipient": {
            "type": "string",
            "description": "Email address of the recipient for 'send' or 'reply'.",
        },
        "subject": {
            "type": "string",
            "description": "Subject line for 'send'.",
        },
        "body": {
            "type": "string",
            "description": "The content of the email for 'send' or 'reply'.",
        },
        "message_id": {
            "type": "string",
            "description": "The ID of the message for 'read', 'reply', or 'mark_read'.",
        },
        "include_body": {
            "type": "boolean",
            "description": "For 'search', include the full email body for each result.",
        },
    },
    "required": ["action"],
}
TOOL_VERSION = "3"

# Changed to modify scope to allow sending and marking read
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = Path.home() / ".pyagent" / "token_gmail.json"
CREDENTIALS_PATH = Path.home() / "Downloads" / "credentials.json"

def get_gmail_service():
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

    return build("gmail", "v1", credentials=creds)

def create_message(sender, to, subject, body, thread_id=None, in_reply_to=None, references=None):
    message = MIMEText(body)
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw, "threadId": thread_id}


def _decode_base64url(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    decoded = base64.urlsafe_b64decode(data + padding)
    return decoded.decode("utf-8", errors="replace")


def _extract_message_bodies(payload: dict) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict) -> None:
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")

        if mime_type == "text/plain" and data:
            text_parts.append(_decode_base64url(data))
        elif mime_type == "text/html" and data:
            html_parts.append(_decode_base64url(data))

        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload or {})
    return ("\n\n".join(p for p in text_parts if p).strip(), "\n\n".join(p for p in html_parts if p).strip())


def run_tool(**kwargs) -> str:
    action = kwargs.get("action")
    try:
        service = get_gmail_service()

        if action == "search":
            query = kwargs.get("query", "") if kwargs.get("query") else ""
            include_body = bool(kwargs.get("include_body", False))
            results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
            messages = results.get("messages", [])

            if not messages:
                return "No messages found matching your criteria."

            email_summaries = []
            for msg in messages:
                msg_data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
                payload = msg_data.get("payload", {})
                headers = payload.get("headers", [])

                subject = "No Subject"
                sender = "Unknown Sender"
                for header in headers:
                    if header["name"] == "Subject":
                        subject = header["value"]
                    if header["name"] == "From":
                        sender = header["value"]

                snippet = msg_data.get("snippet", "")
                entry_parts = [
                    f"ID: {msg['id']}",
                    f"From: {sender}",
                    f"Subject: {subject}",
                    f"Snippet: {snippet}",
                ]

                if include_body:
                    text_body, html_body = _extract_message_bodies(payload)
                    if not text_body and not html_body:
                        text_body = snippet
                    if text_body:
                        entry_parts.extend(["", "Plain Text Body:", text_body])
                    if html_body:
                        entry_parts.extend(["", "HTML Body:", html_body])

                entry_parts.append("-" * 20)
                email_summaries.append("\n".join(entry_parts))
            return "\n".join(email_summaries)

        elif action == "read":
            message_id = kwargs.get("message_id")
            if not message_id:
                return "Error: Message ID is required to read an email."

            msg_data = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            payload = msg_data.get("payload", {})
            headers = payload.get("headers", [])

            header_map = {header.get("name", ""): header.get("value", "") for header in headers}
            subject = header_map.get("Subject", "No Subject")
            sender = header_map.get("From", "Unknown Sender")
            to = header_map.get("To", "Unknown Recipient")
            date = header_map.get("Date", "Unknown Date")

            text_body, html_body = _extract_message_bodies(payload)
            if not text_body and not html_body:
                text_body = msg_data.get("snippet", "")

            parts = [
                f"ID: {message_id}",
                f"From: {sender}",
                f"To: {to}",
                f"Date: {date}",
                f"Subject: {subject}",
                "",
            ]

            if text_body:
                parts.extend(["Plain Text Body:", text_body, ""])
            if html_body:
                parts.extend(["HTML Body:", html_body, ""])

            return "\n".join(parts).strip()

        elif action == "send":
            recipient = kwargs.get("recipient")
            subject = kwargs.get("subject", "(No Subject)")
            body = kwargs.get("body", "")
            if not recipient or not body:
                return "Error: Recipient and body are required for sending emails."

            # Get my own email address
            me = service.users().getProfile(userId="me").execute()["emailAddress"]
            msg_obj = create_message(me, recipient, subject, body)
            service.users().messages().send(userId="me", body=msg_obj).execute()
            return f"Email successfully sent to {recipient}."

        elif action == "reply":
            message_id = kwargs.get("message_id")
            body = kwargs.get("body")
            if not message_id or not body:
                return "Error: Message ID and body are required for replying."

            # Fetch the original message to get headers and thread ID
            original = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            headers = original.get("payload", {}).get("headers", [])
            thread_id = original.get("threadId")

            original_subject = ""
            recipient = ""
            msg_id_header = ""
            references_header = ""

            for h in headers:
                name = h["name"]
                value = h["value"]
                if name == "Subject":
                    original_subject = value
                elif name == "From":
                    recipient = parseaddr(value)[1]
                elif name == "Message-ID":
                    msg_id_header = value
                elif name == "References":
                    references_header = value

            if not recipient:
                return "Error: Could not determine reply recipient from original message."
            if not msg_id_header:
                return "Error: Original message is missing Message-ID header."

            subject = original_subject or "(No Subject)"
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

            references = f"{references_header} {msg_id_header}".strip() if references_header else msg_id_header

            me = service.users().getProfile(userId="me").execute()["emailAddress"]
            msg_obj = create_message(
                me,
                recipient,
                subject,
                body,
                thread_id=thread_id,
                in_reply_to=msg_id_header,
                references=references,
            )
            service.users().messages().send(userId="me", body=msg_obj).execute()
            return f"Reply sent to {recipient} in thread {thread_id}."

        elif action == "mark_read":
            message_id = kwargs.get("message_id")
            if not message_id:
                return "Error: Message ID is required to mark as read."

            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return f"Message {message_id} marked as read."

        else:
            return f"Unsupported action: {action}"

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
