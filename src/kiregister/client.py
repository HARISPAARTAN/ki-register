"""Thin Dataverse Web API client: OData headers, solution header, retries, errors with context."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)
READ_RETRY_STATUS = {429, 502, 503, 504}  # idempotent calls (GET)
WRITE_RETRY_STATUS = {429, 503}  # a retried create may already have succeeded after 502/504
MAX_RETRIES = 5
MAX_WAIT = 120.0
ACTION_TIMEOUT = 300.0
ENTITY_ID = re.compile(r"\(([0-9a-fA-F-]{36})\)\s*$")


class DataverseError(Exception):
    def __init__(self, status: int, code: str, message: str, path: str, component: str | None = None):
        where = f"{component} ({path})" if component else path
        super().__init__(f"{status} {code} bei {where}: {message}")
        self.status, self.code, self.message, self.path, self.component = status, code, message, path, component


def _retry_wait(value: str | None, attempt: int) -> float:
    """Seconds to wait: Retry-After as integer seconds or HTTP date, else exponential backoff; capped."""
    wait = float(2 ** attempt)
    if value:
        value = value.strip()
        try:
            wait = float(int(value))
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                wait = max(0.0, (when - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError):
                pass
    return min(wait, MAX_WAIT)


def _error_parts(resp: httpx.Response) -> tuple[str, str]:
    try:
        body = resp.json()
    except ValueError:
        body = None
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("code", "")), str(err.get("message", resp.text[:500]))
    if isinstance(err, str):
        return "", err
    return "", resp.text[:500]


class DataverseClient:
    def __init__(self, api_url: str, tokens, solution: str | None = None, timeout: float = 120.0):
        self.api_url = api_url if api_url.endswith("/") else api_url + "/"
        self._tokens = tokens
        self.solution = solution
        self._timeout = timeout
        self._http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> DataverseClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _headers(self, solution: bool) -> dict:
        h = {"Authorization": f"Bearer {self._tokens.token()}", "OData-MaxVersion": "4.0", "OData-Version": "4.0",
             "Accept": "application/json", "Content-Type": "application/json; charset=utf-8"}
        if solution:
            if not self.solution:
                raise ValueError("Lösung nicht gesetzt: DataverseClient(..., solution=...)")
            h["MSCRM.SolutionUniqueName"] = self.solution
        return h

    def _request(self, method: str, path: str, *, params=None, json=None, solution: bool = False,
                 component: str | None = None, timeout: float | None = None) -> httpx.Response:
        url = path if path.startswith("http") else self.api_url + path
        idempotent = method == "GET"
        retry_status = READ_RETRY_STATUS if idempotent else WRITE_RETRY_STATUS
        attempt = 0
        while True:
            try:
                resp = self._http.request(method, url, params=params, json=json, headers=self._headers(solution),
                                          timeout=timeout if timeout is not None else self._timeout)
            except httpx.TransportError as exc:
                if idempotent and attempt < MAX_RETRIES:
                    wait = _retry_wait(None, attempt)
                    log.warning("%s %s -> %s, warte %.0fs", method, path, type(exc).__name__, wait)
                    time.sleep(wait)
                    attempt += 1
                    continue
                raise DataverseError(0, "transport", f"{type(exc).__name__}: {exc}", path, component) from exc
            if resp.status_code in retry_status and attempt < MAX_RETRIES:
                wait = _retry_wait(resp.headers.get("Retry-After"), attempt)
                log.warning("%s %s -> %s, warte %.0fs", method, path, resp.status_code, wait)
                time.sleep(wait)
                attempt += 1
                continue
            if resp.status_code >= 400:
                code, message = _error_parts(resp)
                raise DataverseError(resp.status_code, code, message, path, component)
            return resp

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params).json()

    def get_text(self, path: str, params: dict | None = None) -> str:
        """GET with a plain-text answer such as `<entity set>/$count` (a bare integer)."""
        return self._request("GET", path, params=params).text.removeprefix(chr(0xFEFF)).strip()  # Dataverse answers /$count with a UTF-8 byte order mark

    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        data = self.get(path, params)
        rows = list(data.get("value", []))
        api_host = urlparse(self.api_url).netloc
        while data.get("@odata.nextLink"):
            link = data["@odata.nextLink"]
            if urlparse(link).netloc != api_host:
                raise DataverseError(0, "nextlink", f"nextLink zeigt auf einen fremden Host: {link}", path)
            data = self.get(link)
            rows.extend(data.get("value", []))
        return rows

    def find_one(self, path: str, filter_: str, select: str | None = None) -> dict | None:
        params = {"$filter": filter_, "$top": 1}
        if select:
            params["$select"] = select
        rows = self.get(path, params).get("value", [])
        return rows[0] if rows else None

    def post(self, path: str, json: dict, solution: bool = True, component: str | None = None) -> str | dict | None:
        resp = self._request("POST", path, json=json, solution=solution, component=component)
        entity = resp.headers.get("OData-EntityId")
        if entity:
            m = ENTITY_ID.search(entity)
            return m.group(1) if m else entity
        return resp.json() if resp.content else None

    def post_id(self, path: str, json: dict, solution: bool = True, component: str | None = None) -> str:
        """POST a create and return the new record id; fails if the answer carries no id."""
        created = self.post(path, json, solution=solution, component=component)
        if not isinstance(created, str):
            raise DataverseError(0, "no-id", "Die Antwort enthaelt keine Datensatz-ID (OData-EntityId fehlt)", path, component)
        return created

    def patch(self, path: str, json: dict, solution: bool = True, component: str | None = None) -> None:
        self._request("PATCH", path, json=json, solution=solution, component=component)

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    def action(self, name: str, body: dict | None = None, solution: bool = True) -> dict:
        resp = self._request("POST", name, json=body or {}, solution=solution, component=name, timeout=ACTION_TIMEOUT)
        return resp.json() if resp.content else {}
