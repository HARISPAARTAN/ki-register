"""Thin Dataverse Web API client: OData headers, solution header, retries, errors with context."""

from __future__ import annotations

import logging
import re
import time

import httpx

log = logging.getLogger(__name__)
RETRY_STATUS = {429, 502, 503, 504}
ENTITY_ID = re.compile(r"\(([^()]+)\)\s*$")


class DataverseError(Exception):
    def __init__(self, status: int, code: str, message: str, path: str):
        super().__init__(f"{status} {code} bei {path}: {message}")
        self.status, self.code, self.message, self.path = status, code, message, path


class DataverseClient:
    def __init__(self, api_url: str, tokens, solution: str | None = None, timeout: float = 120.0):
        self.api_url = api_url if api_url.endswith("/") else api_url + "/"
        self._tokens = tokens
        self.solution = solution
        self._http = httpx.Client(timeout=timeout)

    def _headers(self, solution: bool) -> dict:
        h = {"Authorization": f"Bearer {self._tokens.token()}", "OData-MaxVersion": "4.0", "OData-Version": "4.0",
             "Accept": "application/json", "Content-Type": "application/json; charset=utf-8", "Prefer": "return=representation"}
        if solution and self.solution:
            h["MSCRM.SolutionUniqueName"] = self.solution
        return h

    def _request(self, method: str, path: str, *, params=None, json=None, solution: bool = False) -> httpx.Response:
        url = path if path.startswith("http") else self.api_url + path
        for attempt in range(6):
            resp = self._http.request(method, url, params=params, json=json, headers=self._headers(solution))
            if resp.status_code in RETRY_STATUS and attempt < 5:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("%s %s -> %s, warte %.0fs", method, path, resp.status_code, wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                try:
                    err = resp.json().get("error", {})
                except ValueError:
                    err = {}
                raise DataverseError(resp.status_code, str(err.get("code", "")), str(err.get("message", resp.text[:500])), path)
            return resp
        raise DataverseError(599, "retries", "zu viele Wiederholungen", path)

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params).json()

    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        data = self.get(path, params)
        rows = list(data.get("value", []))
        while data.get("@odata.nextLink"):
            data = self.get(data["@odata.nextLink"])
            rows.extend(data.get("value", []))
        return rows

    def find_one(self, path: str, filter_: str, select: str | None = None) -> dict | None:
        params = {"$filter": filter_, "$top": 1}
        if select:
            params["$select"] = select
        rows = self.get(path, params).get("value", [])
        return rows[0] if rows else None

    def post(self, path: str, json: dict, solution: bool = True) -> str | dict | None:
        resp = self._request("POST", path, json=json, solution=solution)
        entity = resp.headers.get("OData-EntityId")
        if entity:
            m = ENTITY_ID.search(entity)
            return m.group(1) if m else entity
        return resp.json() if resp.content else None

    def patch(self, path: str, json: dict, solution: bool = True) -> None:
        self._request("PATCH", path, json=json, solution=solution)

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    def action(self, name: str, body: dict | None = None) -> dict:
        resp = self._request("POST", name, json=body or {}, solution=True)
        return resp.json() if resp.content else {}
