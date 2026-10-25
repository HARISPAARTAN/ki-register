import json
import re

import httpx
import pytest
import respx
from typer.testing import CliRunner

from kiregister import bootstrap
from kiregister.cli import app
from kiregister.client import DataverseClient

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
CLIENT_ID = "11111111-2222-3333-4444-555555555555"
BU = "bbbbbbbb-0000-0000-0000-00000000000b"
USER = "abcdef01-0000-0000-0000-00000000000a"
ROLE = "0123abcd-0000-0000-0000-00000000000c"
runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


class Tokens:
    def token(self):
        return "t"


def plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_four_commands_registered():
    names = {c.name or c.callback.__name__ for c in app.registered_commands}
    assert names == {"bootstrap", "apply", "seed", "verify"}


def test_apply_help_shows_only_and_env():
    result = runner.invoke(app, ["apply", "--help"])
    assert result.exit_code == 0
    out = plain(result.output)
    assert "--only" in out and "--env" in out


def test_apply_rejects_unknown_only():
    result = runner.invoke(app, ["apply", "--only", "nonsense"])
    assert result.exit_code != 0


def test_bootstrap_requires_client_id(monkeypatch):
    for var in ("CLIENT_ID", "DATAVERSE_URL_DEV"):
        monkeypatch.delenv(var, raising=False)
    result = runner.invoke(app, ["bootstrap", "--env", "dev"])
    assert result.exit_code != 0


def new_client():
    return DataverseClient(API, Tokens())


def mock_lookups(router, user_rows, assigned):
    router.get(API + "businessunits").respond(200, json={"value": [{"businessunitid": BU}]})
    router.get(API + "systemusers").respond(200, json={"value": user_rows})
    router.get(API + "roles").respond(200, json={"value": [{"roleid": ROLE}]})
    router.get(API + f"systemusers({USER})/systemuserroles_association").respond(200, json={"value": assigned})


@respx.mock
def test_ensure_application_user_creates_user_and_assigns_role():
    mock_lookups(respx.mock, [], [])
    create = respx.post(API + "systemusers").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + f"systemusers({USER})"}))
    assign = respx.post(API + f"systemusers({USER})/systemuserroles_association/$ref").mock(return_value=httpx.Response(204))
    assert bootstrap.ensure_application_user(new_client(), CLIENT_ID) == USER
    body = json.loads(create.calls[0].request.content)
    assert body == {"applicationid": CLIENT_ID, "businessunitid@odata.bind": f"/businessunits({BU})"}
    assert json.loads(assign.calls[0].request.content) == {"@odata.id": f"{API}roles({ROLE})"}
    assert "MSCRM.SolutionUniqueName" not in create.calls[0].request.headers


@respx.mock
def test_ensure_application_user_is_idempotent():
    mock_lookups(respx.mock, [{"systemuserid": USER}], [{"roleid": ROLE}])
    create = respx.post(API + "systemusers").mock(return_value=httpx.Response(204))
    assign = respx.post(API + f"systemusers({USER})/systemuserroles_association/$ref").mock(return_value=httpx.Response(204))
    assert bootstrap.ensure_application_user(new_client(), CLIENT_ID) == USER
    assert create.call_count == 0 and assign.call_count == 0


@respx.mock
def test_ensure_application_user_assigns_missing_role_only():
    mock_lookups(respx.mock, [{"systemuserid": USER}], [])
    create = respx.post(API + "systemusers").mock(return_value=httpx.Response(204))
    assign = respx.post(API + f"systemusers({USER})/systemuserroles_association/$ref").mock(return_value=httpx.Response(204))
    bootstrap.ensure_application_user(new_client(), CLIENT_ID)
    assert create.call_count == 0 and assign.call_count == 1


@respx.mock
def test_missing_role_raises():
    respx.get(API + "businessunits").respond(200, json={"value": [{"businessunitid": BU}]})
    respx.get(API + "systemusers").respond(200, json={"value": [{"systemuserid": USER}]})
    respx.get(API + "roles").respond(200, json={"value": []})
    with pytest.raises(RuntimeError, match="System Administrator"):
        bootstrap.ensure_application_user(new_client(), CLIENT_ID)


@respx.mock
def test_ensure_application_user_accepts_entity_body_response():
    mock_lookups(respx.mock, [], [])
    respx.post(API + "systemusers").mock(return_value=httpx.Response(201, json={"systemuserid": USER, "applicationid": CLIENT_ID}))
    assign = respx.post(API + f"systemusers({USER})/systemuserroles_association/$ref").mock(return_value=httpx.Response(204))
    assert bootstrap.ensure_application_user(new_client(), CLIENT_ID) == USER
    assert assign.call_count == 1
