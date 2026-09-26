from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""AnimaWorks Google Sheets tool -- Sheets API access.

Provides spreadsheet value reading/writing and sheet (tab) listing via
Google Sheets API. Uses the same OAuth2 credential pattern as the Gmail
and Google Calendar tools.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from core.i18n import t

logger = logging.getLogger(__name__)

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "read": {"expected_seconds": 10, "background_eligible": False},
    "tabs": {"expected_seconds": 10, "background_eligible": False},
    "write_values": {"expected_seconds": 10, "background_eligible": False},
    "append_values": {"expected_seconds": 10, "background_eligible": False},
}

TOOL_DESCRIPTION = "Google Sheets access (read/write values and sheet tabs)"

# The stored token carries the full spreadsheets scope; requesting the
# same scope here keeps refresh compatible with the existing token.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_DEFAULT_CREDENTIALS_DIR = Path.home() / ".animaworks" / "credentials" / "google_sheets"

_SPREADSHEET_URL_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


def _credentials_dir() -> Path:
    """Prefer credentials isolated to the running Anima's company."""
    anima_dir_value = os.environ.get("ANIMAWORKS_ANIMA_DIR")
    if anima_dir_value:
        from core.company import get_company

        anima_dir = Path(anima_dir_value).resolve()
        company = get_company(anima_dir.name, animas_dir=anima_dir.parent)
        if company:
            companies_dir = (anima_dir.parent.parent / "companies").resolve()
            company_dir = (companies_dir / company / "credentials" / company / "google_sheets").resolve()
            if company_dir.is_relative_to(companies_dir) and company_dir.is_dir():
                return company_dir
    return _DEFAULT_CREDENTIALS_DIR


def _extract_spreadsheet_id(id_or_url: str) -> str:
    """Accept either a bare spreadsheet ID or a full docs.google.com URL."""
    m = _SPREADSHEET_URL_RE.search(id_or_url)
    return m.group(1) if m else id_or_url


# ── Client ────────────────────────────────────────────────


class GoogleSheetsClient:
    """Google Sheets API client with OAuth2 authentication."""

    def __init__(
        self,
        credentials_path: Path | None = None,
        token_path: Path | None = None,
    ) -> None:
        credentials_dir = _credentials_dir()
        self.credentials_path = credentials_path or (credentials_dir / "credentials.json")
        self.token_path = token_path or (credentials_dir / "token.json")
        self._service = None

    def _get_credentials(self) -> Any:
        """Obtain valid credentials via OAuth2."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise ImportError(
                "google_sheets tool requires google-api packages. "
                "Install with: pip install google-api-python-client "
                "google-auth-httplib2 google-auth-oauthlib"
            ) from None

        creds = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Sandboxes mount credentials read-only; a refreshed token
                # still works in-memory even when persisting fails.
                try:
                    self.token_path.write_text(creds.to_json())
                except OSError:
                    logger.debug("could not persist refreshed token (read-only mount?)")
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"No credentials found. Place credentials.json and token.json at "
                        f"{self.credentials_path.parent}."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path),
                    SCOPES,
                )
                creds = flow.run_local_server(port=0)
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                self.token_path.write_text(creds.to_json())

        return creds

    def _build_service(self) -> Any:
        """Build the Sheets API service."""
        if self._service is None:
            from googleapiclient.discovery import build as build_api

            creds = self._get_credentials()
            self._service = build_api("sheets", "v4", credentials=creds)
        return self._service

    def list_tabs(self, spreadsheet_id: str) -> dict[str, Any]:
        """List sheet tabs and basic metadata of a spreadsheet."""
        service = self._build_service()
        result = service.spreadsheets().get(spreadsheetId=_extract_spreadsheet_id(spreadsheet_id)).execute()
        return {
            "title": result.get("properties", {}).get("title", ""),
            "spreadsheet_id": result.get("spreadsheetId", ""),
            "sheets": [
                {
                    "title": s.get("properties", {}).get("title", ""),
                    "sheet_id": s.get("properties", {}).get("sheetId", 0),
                    "rows": s.get("properties", {}).get("gridProperties", {}).get("rowCount", 0),
                    "cols": s.get("properties", {}).get("gridProperties", {}).get("columnCount", 0),
                }
                for s in result.get("sheets", [])
            ],
        }

    def read_values(
        self,
        spreadsheet_id: str,
        *,
        range_: str = "A1:Z1000",
    ) -> dict[str, Any]:
        """Read cell values from a spreadsheet range.

        Args:
            spreadsheet_id: Spreadsheet ID or full URL.
            range_: A1 notation, optionally with sheet name (e.g. "Sheet1!A1:C10").
        """
        service = self._build_service()
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=_extract_spreadsheet_id(spreadsheet_id),
                range=range_,
            )
            .execute()
        )
        return {
            "range": result.get("range", ""),
            "values": result.get("values", []),
        }

    def write_values(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[list],
        value_input_option: str = "USER_ENTERED",
    ) -> dict[str, Any]:
        """Overwrite cell values in a spreadsheet range.

        Args:
            spreadsheet_id: Spreadsheet ID or full URL.
            range_a1: A1 notation, optionally with sheet name (e.g. "Sheet1!A1:C10").
            values: 2D list of cell values (rows of columns).
            value_input_option: How input data is interpreted (USER_ENTERED or RAW).
        """
        service = self._build_service()
        result = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=_extract_spreadsheet_id(spreadsheet_id),
                range=range_a1,
                valueInputOption=value_input_option,
                body={"values": values},
            )
            .execute()
        )
        return {
            "updated_range": result.get("updatedRange", ""),
            "updated_cells": result.get("updatedCells", 0),
        }

    def append_values(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[list],
        value_input_option: str = "USER_ENTERED",
    ) -> dict[str, Any]:
        """Append rows after the last data in a spreadsheet range/table.

        Args:
            spreadsheet_id: Spreadsheet ID or full URL.
            range_a1: A1 notation identifying the table (e.g. "Sheet1!A:C").
            values: 2D list of cell values to append (rows of columns).
            value_input_option: How input data is interpreted (USER_ENTERED or RAW).
        """
        service = self._build_service()
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=_extract_spreadsheet_id(spreadsheet_id),
                range=range_a1,
                valueInputOption=value_input_option,
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            )
            .execute()
        )
        updates = result.get("updates") or {}
        return {
            "updated_range": updates.get("updatedRange", result.get("updatedRange", "")),
            "updated_cells": updates.get("updatedCells", result.get("updatedCells", 0)),
        }


# ── Tool schemas ──────────────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas for Google Sheets tools."""
    spreadsheet_id_prop = {
        "type": "string",
        "description": "Spreadsheet ID or full docs.google.com URL",
    }
    range_prop = {
        "type": "string",
        "description": "A1 range, optionally with sheet name (e.g. 'Sheet1!A1:C10')",
    }
    values_prop = {
        "type": "array",
        "description": "2D array of cell values (list of rows)",
        "items": {"type": "array", "items": {}},
    }
    value_input_option_prop = {
        "type": "string",
        "description": "How input is interpreted: USER_ENTERED (default) or RAW",
        "enum": ["USER_ENTERED", "RAW"],
    }
    write_caution = t("tooling_schema.sheets_write_caution")
    return [
        {
            "name": "google_sheets_tabs",
            "description": "List sheet tabs and basic metadata of a spreadsheet (list_tabs).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": spreadsheet_id_prop,
                },
                "required": ["spreadsheet_id"],
            },
        },
        {
            "name": "google_sheets_read",
            "description": "Read cell values from a spreadsheet range (read_values).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": spreadsheet_id_prop,
                    "range": {
                        **range_prop,
                        "description": range_prop["description"] + " Default: A1:Z1000",
                    },
                },
                "required": ["spreadsheet_id"],
            },
        },
        {
            "name": "google_sheets_write_values",
            "description": ("Overwrite cell values in a spreadsheet range (write_values). " + write_caution),
            "input_schema": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": spreadsheet_id_prop,
                    "range": range_prop,
                    "values": values_prop,
                    "value_input_option": value_input_option_prop,
                },
                "required": ["spreadsheet_id", "range", "values"],
            },
        },
        {
            "name": "google_sheets_append_values",
            "description": (
                "Append rows after the last data in a spreadsheet range/table (append_values). " + write_caution
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": spreadsheet_id_prop,
                    "range": range_prop,
                    "values": values_prop,
                    "value_input_option": value_input_option_prop,
                },
                "required": ["spreadsheet_id", "range", "values"],
            },
        },
    ]


# ── Dispatch ──────────────────────────────────────────────


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    _args = {k: v for k, v in args.items() if k != "anima_dir"}
    client = GoogleSheetsClient()

    if name == "google_sheets_read":
        spreadsheet_id = _args.get("spreadsheet_id", "")
        if not spreadsheet_id:
            return {"error": "spreadsheet_id is required"}
        return client.read_values(
            spreadsheet_id,
            range_=_args.get("range", "A1:Z1000"),
        )

    if name == "google_sheets_tabs":
        spreadsheet_id = _args.get("spreadsheet_id", "")
        if not spreadsheet_id:
            return {"error": "spreadsheet_id is required"}
        return client.list_tabs(spreadsheet_id)

    if name == "google_sheets_write_values":
        spreadsheet_id = _args.get("spreadsheet_id", "")
        range_a1 = _args.get("range", "")
        values = _args.get("values")
        if not spreadsheet_id:
            return {"error": "spreadsheet_id is required"}
        if not range_a1:
            return {"error": "range is required"}
        if not isinstance(values, list):
            return {"error": "values is required (2D list)"}
        return client.write_values(
            spreadsheet_id,
            range_a1,
            values,
            value_input_option=_args.get("value_input_option", "USER_ENTERED"),
        )

    if name == "google_sheets_append_values":
        spreadsheet_id = _args.get("spreadsheet_id", "")
        range_a1 = _args.get("range", "")
        values = _args.get("values")
        if not spreadsheet_id:
            return {"error": "spreadsheet_id is required"}
        if not range_a1:
            return {"error": "range is required"}
        if not isinstance(values, list):
            return {"error": "values is required (2D list)"}
        return client.append_values(
            spreadsheet_id,
            range_a1,
            values,
            value_input_option=_args.get("value_input_option", "USER_ENTERED"),
        )

    return {"error": f"Unknown action: {name}"}


# ── CLI ───────────────────────────────────────────────────


def cli_main(argv: list[str] | None = None) -> None:
    """CLI entry point for the Google Sheets tool."""
    parser = argparse.ArgumentParser(
        prog="animaworks-tool google_sheets",
        description="Google Sheets operations (read/write values and sheet tabs)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # read
    p_read = subparsers.add_parser("read", help="Read cell values")
    p_read.add_argument("spreadsheet_id", help="Spreadsheet ID or URL")
    p_read.add_argument("-r", "--range", default="A1:Z1000", help="A1 range, e.g. 'Sheet1!A1:C10'")
    p_read.add_argument("-j", "--json", action="store_true", help="JSON output")

    # tabs
    p_tabs = subparsers.add_parser("tabs", help="List sheet tabs")
    p_tabs.add_argument("spreadsheet_id", help="Spreadsheet ID or URL")
    p_tabs.add_argument("-j", "--json", action="store_true", help="JSON output")

    # write / append (shared arguments)
    values_help = "Cell values as JSON 2D array (e.g. '[[\"a\",1],[\"b\",2]]'), or '-' to read from stdin"
    p_write = subparsers.add_parser("write", help="Overwrite cell values in a range")
    p_append = subparsers.add_parser("append", help="Append rows after the last data in a range")
    for p in (p_write, p_append):
        p.add_argument("spreadsheet_id", help="Spreadsheet ID or URL")
        p.add_argument("range", help="A1 range, e.g. 'Sheet1!A1:C10'")
        p.add_argument("values", help=values_help)
        p.add_argument(
            "--raw",
            action="store_true",
            help="Interpret values as RAW instead of USER_ENTERED",
        )
        p.add_argument("-j", "--json", action="store_true", help="JSON output")

    args = parser.parse_args(argv)
    client = GoogleSheetsClient()

    try:
        if args.command == "read":
            result = client.read_values(args.spreadsheet_id, range_=args.range)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                for row in result.get("values", []):
                    print("\t".join(str(c) for c in row))

        elif args.command == "tabs":
            result = client.list_tabs(args.spreadsheet_id)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"{result.get('title', '')} ({result.get('spreadsheet_id', '')})")
                for s in result.get("sheets", []):
                    print(f"  {s['title']}  ({s['rows']}x{s['cols']})")

        elif args.command in ("write", "append"):
            raw_values = sys.stdin.read() if args.values == "-" else args.values
            values = json.loads(raw_values)
            if not isinstance(values, list) or not all(isinstance(r, list) for r in values):
                print("Error: values must be a JSON 2D array (rows of columns)", file=sys.stderr)
                sys.exit(1)
            option = "RAW" if args.raw else "USER_ENTERED"
            fn = client.write_values if args.command == "write" else client.append_values
            result = fn(args.spreadsheet_id, args.range, values, value_input_option=option)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"{result.get('updated_range', '')}: {result.get('updated_cells', 0)} cells")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
