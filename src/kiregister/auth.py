"""Tokens: client credentials (MSAL) for automation, Azure CLI for the owner's one-time bootstrap."""

from __future__ import annotations

import json
import subprocess
import time

import msal

from .config import Settings


class ClientCredentialTokens:
    def __init__(self, settings: Settings):
        if not (settings.tenant_id and settings.client_id and settings.client_secret and settings.url):
            raise ValueError("TENANT_ID, CLIENT_ID, CLIENT_SECRET und die Umgebungs-URL muessen gesetzt sein (.env)")
        self._scope = [settings.url.rstrip("/") + "/.default"]
        self._app = msal.ConfidentialClientApplication(
            settings.client_id, authority=f"https://login.microsoftonline.com/{settings.tenant_id}", client_credential=settings.client_secret)

    def token(self) -> str:
        result = self._app.acquire_token_silent(self._scope, account=None) or self._app.acquire_token_for_client(self._scope)
        if "access_token" not in result:
            raise RuntimeError(f"Token fehlgeschlagen: {result.get('error')}: {result.get('error_description')}")
        return result["access_token"]


class AzCliTokens:
    """Uses the owner's `az login` session; only for `kiregister bootstrap`."""

    def __init__(self, url: str):
        self._resource = url.rstrip("/")
        self._cached: tuple[float, str] | None = None

    def token(self) -> str:
        if self._cached and self._cached[0] > time.time() + 60:
            return self._cached[1]
        out = subprocess.run(["az", "account", "get-access-token", "--resource", self._resource, "-o", "json"],
                             capture_output=True, text=True, check=True, shell=True).stdout
        data = json.loads(out)
        self._cached = (time.time() + 3000, data["accessToken"])
        return data["accessToken"]
