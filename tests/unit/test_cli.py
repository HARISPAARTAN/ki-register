import json
import re

import httpx
import pytest
import respx
from typer.testing import CliRunner

from kiregister import auditing, bootstrap
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


def test_apply_help_lists_auditing_and_names_it_as_the_one_variant_that_runs_against_test():
    result = runner.invoke(app, ["apply", "--help"])
    assert result.exit_code == 0
    out = plain(result.output)
    assert "metadata | security | app | auditing" in out
    assert "Gegen Test laeuft nur" in out and "apply --only auditing" in out


def stub_apply(monkeypatch):
    """apply without Dataverse: each step records its name when it runs; the client, settings and definitions are stand-ins."""
    from kiregister import app as app_module
    from kiregister import cli, metadata, security
    steps = []
    monkeypatch.setattr(cli, "_client", lambda env: (object(), object(), object()))
    monkeypatch.setattr(metadata, "apply_metadata", lambda client, settings, defs: steps.append("metadata") or {"tables": 8})
    monkeypatch.setattr(security, "apply_security", lambda client, settings, defs: steps.append("security") or {"roles": 4})
    monkeypatch.setattr(app_module, "apply_app", lambda client, settings, defs: steps.append("app") or {"app": "id"})
    monkeypatch.setattr(auditing, "ensure_auditing", lambda client: steps.append("auditing") or True)
    return steps


@pytest.mark.parametrize("only, expected", [("metadata", ["metadata"]), ("security", ["security"]), ("app", ["app"]), ("auditing", ["auditing"]),
                                            (None, ["metadata", "security", "app", "auditing"])])
def test_apply_runs_the_chosen_step_only_and_the_full_apply_ends_with_auditing(monkeypatch, only, expected):
    steps = stub_apply(monkeypatch)
    result = runner.invoke(app, ["apply", "--env", "dev", *(["--only", only] if only else [])])
    assert result.exit_code == 0, result.output
    assert steps == expected


@pytest.mark.parametrize("changed, text", [(True, "auditing: eingeschaltet"), (False, "auditing: war bereits eingeschaltet")])
def test_apply_only_auditing_says_whether_it_changed_something(monkeypatch, changed, text):
    stub_apply(monkeypatch)
    monkeypatch.setattr(auditing, "ensure_auditing", lambda client: changed)
    result = runner.invoke(app, ["apply", "--only", "auditing"])
    assert result.exit_code == 0 and text in result.output


@respx.mock
@pytest.mark.parametrize("env, variable", [("dev", "DATAVERSE_URL_DEV"), ("test", "DATAVERSE_URL_TEST")])
def test_apply_only_auditing_reads_and_patches_the_organization_row_and_nothing_else(monkeypatch, env, variable):
    """The variant that runs against Test: any other request would be unmocked and fail the run."""
    from kiregister import cli
    monkeypatch.setenv(variable, "https://org.crm4.dynamics.com")
    monkeypatch.setattr(cli, "ClientCredentialTokens", lambda settings: Tokens())
    org = "cccccccc-0000-0000-0000-00000000000c"
    get = respx.get(API + "organizations").respond(200, json={"value": [{"organizationid": org, "isauditenabled": False}]})
    patch = respx.patch(API + f"organizations({org})").respond(204)
    result = runner.invoke(app, ["apply", "--env", env, "--only", "auditing"])
    assert result.exit_code == 0, result.output
    assert "auditing: eingeschaltet" in result.output
    assert get.call_count == 1 and patch.call_count == 1 and len(respx.calls) == 2


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


@respx.mock
def test_role_is_looked_up_by_template_id_first():
    respx.get(API + "businessunits").respond(200, json={"value": [{"businessunitid": BU}]})
    respx.get(API + "systemusers").respond(200, json={"value": [{"systemuserid": USER}]})
    roles = respx.get(API + "roles").respond(200, json={"value": [{"roleid": ROLE}]})
    respx.get(API + f"systemusers({USER})/systemuserroles_association").respond(200, json={"value": [{"roleid": ROLE}]})
    bootstrap.ensure_application_user(new_client(), CLIENT_ID)
    assert roles.call_count == 1
    # The Web API rejects `roletemplateid eq <guid>` (400, 0x80060888, checked against Dev); the lookup spelling is `_roletemplateid_value`.
    assert roles.calls[0].request.url.params["$filter"] == f"_roletemplateid_value eq 627090ff-40a3-4053-8790-584edc5be201 and _businessunitid_value eq {BU}"


@respx.mock
def test_role_lookup_falls_back_to_the_name():
    respx.get(API + "businessunits").respond(200, json={"value": [{"businessunitid": BU}]})
    respx.get(API + "systemusers").respond(200, json={"value": [{"systemuserid": USER}]})
    roles = respx.get(API + "roles").mock(side_effect=[httpx.Response(200, json={"value": []}),
                                                       httpx.Response(200, json={"value": [{"roleid": ROLE}]})])
    respx.get(API + f"systemusers({USER})/systemuserroles_association").respond(200, json={"value": [{"roleid": ROLE}]})
    bootstrap.ensure_application_user(new_client(), CLIENT_ID)
    assert roles.call_count == 2
    assert "System%20Administrator" in str(roles.calls[1].request.url) or "System+Administrator" in str(roles.calls[1].request.url)


def stub_verify(monkeypatch, failures=()):
    """verify without Dataverse: records the arguments of run_verify and returns the given failures."""
    from kiregister import cli
    from kiregister import verify as verify_module
    seen = {}

    def fake_run_verify(client, settings, defs, expect_seed=True):
        seen["expect_seed"] = expect_seed
        return list(failures)

    monkeypatch.setattr(cli, "_client", lambda env: (object(), object(), object()))
    monkeypatch.setattr(verify_module, "run_verify", fake_run_verify)
    return seen


@pytest.mark.parametrize("value, expect_seed", [(None, True), ("", True), ("0", True), ("1", False), (" TRUE ", False), ("yes", False)])
def test_verify_checks_solution_components_only_when_no_seed_is_set(monkeypatch, value, expect_seed):
    seen = stub_verify(monkeypatch)
    if value is None:
        monkeypatch.delenv("KIREGISTER_VERIFY_NO_SEED", raising=False)
    else:
        monkeypatch.setenv("KIREGISTER_VERIFY_NO_SEED", value)
    result = runner.invoke(app, ["verify", "--env", "test"])
    assert result.exit_code == 0 and "verify: ok" in result.output
    assert seen["expect_seed"] is expect_seed
    assert ("nur Loesungskomponenten und Auditing-Schalter" in result.output) is (not expect_seed)


@pytest.mark.parametrize("no_seed", [False, True])
def test_verify_failures_give_exit_code_1_in_both_modes(monkeypatch, no_seed):
    stub_verify(monkeypatch, failures=["Tabelle nst_schulung", "Rolle nst Leser"])
    monkeypatch.setenv("KIREGISTER_VERIFY_NO_SEED", "1" if no_seed else "0")
    result = runner.invoke(app, ["verify", "--env", "test"])
    assert result.exit_code == 1
    assert "FEHLT: Tabelle nst_schulung" in result.output and "FEHLT: Rolle nst Leser" in result.output and "verify: 2 Abweichungen" in result.output


def test_verbose_scopes_debug_to_the_kiregister_logger():
    import logging
    runner.invoke(app, ["apply", "--help"])
    assert logging.getLogger("kiregister").level == logging.INFO
    runner.invoke(app, ["-v", "apply", "--help"])
    assert logging.getLogger("kiregister").level == logging.DEBUG
    assert logging.getLogger("msal").getEffectiveLevel() >= logging.WARNING
    logging.getLogger("kiregister").setLevel(logging.NOTSET)
