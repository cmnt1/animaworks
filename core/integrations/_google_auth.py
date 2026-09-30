"""Shared OAuth2 credential handling for Google integrations."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.integrations._base import ToolConfigError, get_credential

logger = logging.getLogger(__name__)


class GoogleOAuth:
    """Load, refresh, and persist Google OAuth credentials for an API client.

    Differences between integrations (scopes, storage paths, client env vars,
    errors, and the Gmail MCP token source) are configured at construction.
    """

    def __init__(
        self,
        *,
        scopes: list[str],
        token_path: Path,
        credentials_path: Path,
        env_prefix: str | None = None,
        credential_name: str | None = None,
        tool_name: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        mcp_token_path: Path | None = None,
        missing_credentials_error: str = "No credentials found.",
        missing_credentials_exception: type[Exception] = FileNotFoundError,
        allow_client_config: bool = True,
        open_browser: bool = False,
        import_error_message: str = "Google integrations require google-api packages.",
        create_parent_on_refresh: bool = True,
        create_parent_on_initial_auth: bool = True,
        best_effort_refresh_persist: bool = True,
        best_effort_initial_persist: bool = True,
        persist_error_log_level: int = logging.WARNING,
        persist_error_message: str = "Token persist skipped (%s): %s",
    ) -> None:
        self.scopes = scopes
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.env_prefix = env_prefix
        self.tool_name = tool_name or (env_prefix or "google").lower()
        self.mcp_token_path = mcp_token_path
        self.missing_credentials_error = missing_credentials_error
        self.missing_credentials_exception = missing_credentials_exception
        self.allow_client_config = allow_client_config
        self.open_browser = open_browser
        self.import_error_message = import_error_message
        self.create_parent_on_refresh = create_parent_on_refresh
        self.create_parent_on_initial_auth = create_parent_on_initial_auth
        self.best_effort_refresh_persist = best_effort_refresh_persist
        self.best_effort_initial_persist = best_effort_initial_persist
        self.persist_error_log_level = persist_error_log_level
        self.persist_error_message = persist_error_message

        credential_name = credential_name or (env_prefix.lower() if env_prefix else "")
        self.client_id = client_id or self._resolve_client_credential(
            credential_name, "client_id", f"{env_prefix}_CLIENT_ID" if env_prefix else None
        )
        self.client_secret = client_secret or self._resolve_client_credential(
            credential_name, "client_secret", f"{env_prefix}_CLIENT_SECRET" if env_prefix else None
        )

    def _resolve_client_credential(self, credential_name: str, key_name: str, env_var: str | None) -> str | None:
        if not env_var:
            return None
        try:
            return get_credential(
                credential_name,
                self.tool_name,
                key_name=key_name,
                env_var=env_var,
            )
        except ToolConfigError:
            # Preserve each integration's existing missing-credential error.
            return None

    def _load_auth_dependencies(self) -> tuple[Any, Any, Any]:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise ImportError(self.import_error_message) from None
        return Request, Credentials, InstalledAppFlow

    def _load_mcp_token(self, credentials_cls: Any) -> Any | None:
        if not self.mcp_token_path or not self.mcp_token_path.exists():
            return None
        try:
            with self.mcp_token_path.open() as token_file:
                token_data = json.load(token_file)
            creds = credentials_cls(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id") or self.client_id,
                client_secret=token_data.get("client_secret") or self.client_secret,
            )
            logger.info("Loaded MCP-GSuite token")
            return creds
        except Exception as exc:
            logger.warning("MCP token load error: %s", exc)
            return None

    def _persist_token(self, creds: Any, *, initial_auth: bool = False) -> None:
        create_parent = self.create_parent_on_initial_auth if initial_auth else self.create_parent_on_refresh
        best_effort = self.best_effort_initial_persist if initial_auth else self.best_effort_refresh_persist
        try:
            if create_parent:
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())
        except OSError as exc:
            if not best_effort:
                raise
            if "%s" in self.persist_error_message:
                logger.log(self.persist_error_log_level, self.persist_error_message, self.token_path, exc)
            else:
                logger.log(self.persist_error_log_level, self.persist_error_message)

    def _missing_credentials(self) -> Exception:
        message = self.missing_credentials_error.format(
            credentials_path=self.credentials_path,
            credentials_dir=self.credentials_path.parent,
            env_prefix=self.env_prefix or "",
        )
        return self.missing_credentials_exception(message)

    def get_credentials(self) -> Any:
        """Return valid saved credentials, refreshing or initiating OAuth as needed."""
        Request, Credentials, InstalledAppFlow = self._load_auth_dependencies()
        creds = self._load_mcp_token(Credentials) if self.mcp_token_path else None

        if not creds and self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._persist_token(creds)
            return creds

        if self.credentials_path.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), self.scopes)
        elif self.allow_client_config and self.client_id and self.client_secret:
            client_config = {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, self.scopes)
        else:
            raise self._missing_credentials()

        flow_args = {"port": 0}
        if self.open_browser:
            flow_args["open_browser"] = True
        creds = flow.run_local_server(**flow_args)
        self._persist_token(creds, initial_auth=True)
        return creds
