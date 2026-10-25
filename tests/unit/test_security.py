import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import respx

from kiregister import security
from kiregister.client import DataverseClient
from kiregister.definitions import load_definitions

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
ROOT = "00000000-0000-0000-0000-0000000000a0"
ENERGIE = "00000000-0000-0000-0000-0000000000a1"
NEW = "00000000-0000-0000-0000-0000000000a2"
DEFS = load_definitions(Path(__file__).resolve().parents[2] / "provision" / "definitions")


class Tokens:
    def token(self):
        return "t"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(security.time, "sleep", lambda s: None)


def new_client():
    return DataverseClient(API, Tokens(), solution="NordsternKIRegister")


def test_privilege_names_for_role_tables():
    names = security.privilege_names({"nst_kisystem": {"read": "Local", "appendto": "Local"}})
    assert names == {"prvReadnst_kisystem": "Local", "prvAppendTonst_kisystem": "Local"}


def test_expand_star_uses_every_table():
    expanded = security.expand_tables({"*": {"read": "Global"}}, ["nst_a", "nst_b"])
    assert expanded == {"nst_a": {"read": "Global"}, "nst_b": {"read": "Global"}}


def test_expand_star_lets_a_named_table_override():
    expanded = security.expand_tables({"*": {"read": "Global"}, "nst_b": {"read": "Local"}}, ["nst_a", "nst_b"])
    assert expanded == {"nst_a": {"read": "Global"}, "nst_b": {"read": "Local"}}


def test_governance_wants_eight_privileges_per_table_plus_the_extras():
    role = next(r for r in DEFS.security.roles if r.name == "nst KI-Governance")
    wanted = security.wanted_privileges(role, [t.schema for t in DEFS.tables])
    assert len(wanted) == 8 * len(DEFS.tables) + 3
    assert wanted["prvReadUser"] == "Global" and wanted["prvDeletenst_risikobewertung"] == "Global"


def test_fachbereich_has_no_risikobewertung_privilege():
    role = next(r for r in DEFS.security.roles if r.name == "nst Fachbereich")
    wanted = security.wanted_privileges(role, [t.schema for t in DEFS.tables])
    assert not [n for n in wanted if n.endswith("nst_risikobewertung")]
    assert wanted["prvCreatenst_anwendungsfall"] == "Basic" and wanted["prvReadnst_kisystem"] == "Local"


@respx.mock
def test_ensure_business_units_creates_missing_children():
    respx.get(url__startswith=API + "businessunits").mock(side_effect=[
        httpx.Response(200, json={"value": [{"businessunitid": ROOT, "name": "org"}]}),
        httpx.Response(200, json={"value": [{"businessunitid": ROOT, "name": "org"}, {"businessunitid": ENERGIE, "name": "Nordstern Energie"}]}),
    ])
    created = respx.post(API + "businessunits").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + f"businessunits({NEW})"}))
    ids = security.ensure_business_units(new_client(), ["Nordstern Energie", "Nordstern Klinikum"])
    assert created.call_count == 1 and ids["Nordstern Energie"] == ENERGIE and ids["Nordstern Klinikum"] == NEW
    request = created.calls[0].request
    assert json.loads(request.content) == {"name": "Nordstern Klinikum", "parentbusinessunitid@odata.bind": f"/businessunits({ROOT})"}
    assert "MSCRM.SolutionUniqueName" not in request.headers


@respx.mock
def test_default_team_is_found_by_flag():
    route = respx.get(API + "teams").respond(200, json={"value": [{"teamid": "team-1"}]})
    assert security.default_team_ids(new_client(), {"Nordstern Energie": ENERGIE}) == {"Nordstern Energie": "team-1"}
    assert "isdefault" in str(route.calls[0].request.url)


@respx.mock
def test_missing_default_team_raises_after_waiting():
    respx.get(API + "teams").respond(200, json={"value": []})
    with pytest.raises(RuntimeError, match="Standardteam"):
        security.default_team_ids(new_client(), {"Nordstern Energie": ENERGIE})


def leser_only(defs):
    return replace(defs, security=replace(defs.security, roles=[r for r in defs.security.roles if r.name == "nst Leser"]))


def mock_privileges(defs, held: dict[str, int] | None = None):
    wanted = security.wanted_privileges(defs.security.roles[0], [t.schema for t in defs.tables])
    ids = {n: f"p-{n}" for n in wanted}
    respx.get(API + "privileges").respond(200, json={"value": [{"privilegeid": i, "name": n} for n, i in ids.items()]})
    rows = [{"privilegeid": ids[n], "privilegedepthmask": m} for n, m in (held or {}).items()]
    respx.get(API + "roleprivilegescollection").respond(200, json={"value": rows})
    return wanted, ids


@respx.mock
def test_ensure_roles_creates_the_role_and_adds_its_privileges():
    defs = leser_only(DEFS)
    wanted, ids = mock_privileges(defs)
    respx.get(API + "roles").respond(200, json={"value": []})
    create = respx.post(API + "roles").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + f"roles({NEW})"}))
    action = respx.post(API + f"roles({NEW})/Microsoft.Dynamics.CRM.AddPrivilegesRole").mock(return_value=httpx.Response(204))
    assert security.ensure_roles(new_client(), defs, ROOT) == {"nst Leser": NEW}
    assert json.loads(create.calls[0].request.content) == {"name": "nst Leser", "businessunitid@odata.bind": f"/businessunits({ROOT})"}
    sent = json.loads(action.calls[0].request.content)["Privileges"]
    assert {p["PrivilegeId"] for p in sent} == set(ids.values()) and {p["Depth"] for p in sent} == {"Local"}
    assert all(p["BusinessUnitId"] == security.NO_BUSINESS_UNIT for p in sent)


@respx.mock
def test_ensure_roles_is_idempotent():
    defs = leser_only(DEFS)
    mock_privileges(defs, {n: security.DEPTH_MASK["Local"] for n in security.privilege_names(defs.security.roles[0].tables)})
    respx.get(API + "roles").respond(200, json={"value": [{"roleid": "r1"}]})
    create = respx.post(API + "roles").mock(return_value=httpx.Response(204))
    action = respx.post(API + "roles(r1)/Microsoft.Dynamics.CRM.AddPrivilegesRole").mock(return_value=httpx.Response(204))
    security.ensure_roles(new_client(), defs, ROOT)
    assert create.call_count == 0 and action.call_count == 0


@respx.mock
def test_ensure_roles_updates_a_privilege_held_at_the_wrong_depth():
    defs = leser_only(DEFS)
    held = {n: security.DEPTH_MASK["Local"] for n in security.privilege_names(defs.security.roles[0].tables)}
    held["prvReadnst_kisystem"] = security.DEPTH_MASK["Global"]
    mock_privileges(defs, held)
    respx.get(API + "roles").respond(200, json={"value": [{"roleid": "r1"}]})
    action = respx.post(API + "roles(r1)/Microsoft.Dynamics.CRM.AddPrivilegesRole").mock(return_value=httpx.Response(204))
    security.ensure_roles(new_client(), defs, ROOT)
    sent = json.loads(action.calls[0].request.content)["Privileges"]
    assert len(sent) == 1 and sent[0]["PrivilegeId"] == "p-prvReadnst_kisystem" and sent[0]["Depth"] == "Local"


@respx.mock
def test_missing_privilege_names_are_reported():
    respx.get(API + "privileges").respond(200, json={"value": []})
    respx.get(API + "roles").respond(200, json={"value": [{"roleid": "r1"}]})
    with pytest.raises(RuntimeError, match="Privilegien fehlen"):
        security.ensure_roles(new_client(), leser_only(DEFS), ROOT)


@respx.mock
def test_column_security_creates_profile_and_permission():
    respx.get(API + "fieldsecurityprofiles").respond(200, json={"value": []})
    respx.get(API + "fieldpermissions").respond(200, json={"value": []})
    profile = respx.post(API + "fieldsecurityprofiles").mock(
        return_value=httpx.Response(204, headers={"OData-EntityId": API + f"fieldsecurityprofiles({NEW})"}))
    perm = respx.post(API + "fieldpermissions").mock(return_value=httpx.Response(204))
    assert security.ensure_column_security(new_client(), DEFS) == NEW
    assert json.loads(profile.calls[0].request.content)["name"] == "nst KI-Governance Felder"
    body = json.loads(perm.calls[0].request.content)
    assert body == {"entityname": "nst_kisystem", "attributelogicalname": "nst_internebewertung", "canread": 4, "canupdate": 4, "cancreate": 4,
                    "fieldsecurityprofileid@odata.bind": f"/fieldsecurityprofiles({NEW})"}


@respx.mock
def test_column_security_is_idempotent():
    respx.get(API + "fieldsecurityprofiles").respond(200, json={"value": [{"fieldsecurityprofileid": "fp"}]})
    respx.get(API + "fieldpermissions").respond(200, json={"value": [{"fieldpermissionid": "fperm", "entityname": "nst_kisystem", "attributelogicalname": "nst_internebewertung",
                                                                      "canread": 4, "canupdate": 4, "cancreate": 4}]})
    profile = respx.post(API + "fieldsecurityprofiles").mock(return_value=httpx.Response(204))
    perm = respx.post(API + "fieldpermissions").mock(return_value=httpx.Response(204))
    assert security.ensure_column_security(new_client(), DEFS) == "fp"
    assert profile.call_count == 0 and perm.call_count == 0


@respx.mock
def test_column_security_repairs_a_permission_with_other_values():
    respx.get(API + "fieldsecurityprofiles").respond(200, json={"value": [{"fieldsecurityprofileid": "fp"}]})
    respx.get(API + "fieldpermissions").respond(200, json={"value": [{"fieldpermissionid": "fperm", "entityname": "nst_kisystem", "attributelogicalname": "nst_internebewertung",
                                                                      "canread": 4, "canupdate": 0, "cancreate": 0}]})
    create = respx.post(API + "fieldpermissions").mock(return_value=httpx.Response(204))
    patch = respx.patch(API + "fieldpermissions(fperm)").mock(return_value=httpx.Response(204))
    security.ensure_column_security(new_client(), DEFS)
    assert create.call_count == 0 and patch.call_count == 1
    assert json.loads(patch.calls[0].request.content) == {"canread": 4, "canupdate": 4, "cancreate": 4}


@respx.mock
def test_ensure_business_units_with_a_known_root_reads_the_list_once():
    route = respx.get(url__startswith=API + "businessunits").mock(
        return_value=httpx.Response(200, json={"value": [{"businessunitid": ROOT, "name": "org"}, {"businessunitid": ENERGIE, "name": "Nordstern Energie"}]}))
    assert security.ensure_business_units(new_client(), ["Nordstern Energie"], ROOT) == {"Nordstern Energie": ENERGIE}
    assert route.call_count == 1


def test_owner_role_is_defined_read_only_for_every_table():
    role = next(r for r in DEFS.security.roles if r.name == security.OWNER_ROLE)
    wanted = security.wanted_privileges(role, [t.schema for t in DEFS.tables])
    assert set(wanted) == {f"prvRead{t.schema}" for t in DEFS.tables} and set(wanted.values()) == {"Basic"}


@respx.mock
def test_owner_teams_are_created_with_the_role_of_their_unit():
    respx.get(API + "WhoAmI").respond(200, json={"UserId": "app-user"})
    respx.get(API + "teams").respond(200, json={"value": []})
    respx.get(API + "roles").respond(200, json={"value": [{"roleid": "role-copy"}]})
    respx.get(API + f"teams({NEW})/teamroles_association").respond(200, json={"value": []})
    create = respx.post(API + "teams").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + f"teams({NEW})"}))
    assign = respx.post(API + f"teams({NEW})/teamroles_association/$ref").mock(return_value=httpx.Response(204))
    assert security.ensure_owner_teams(new_client(), {"Nordstern Energie": ENERGIE}) == {"Nordstern Energie": NEW}
    body = json.loads(create.calls[0].request.content)
    assert body["name"] == "Nordstern Energie Datenbesitz" and body["teamtype"] == 0
    assert body["businessunitid@odata.bind"] == f"/businessunits({ENERGIE})" and body["administratorid@odata.bind"] == "/systemusers(app-user)"
    assert "MSCRM.SolutionUniqueName" not in create.calls[0].request.headers
    assert json.loads(assign.calls[0].request.content) == {"@odata.id": API + "roles(role-copy)"}


@respx.mock
def test_owner_teams_are_idempotent():
    respx.get(API + "WhoAmI").respond(200, json={"UserId": "app-user"})
    respx.get(API + "teams").respond(200, json={"value": [{"teamid": "t1"}]})
    respx.get(API + "roles").respond(200, json={"value": [{"roleid": "role-copy"}]})
    respx.get(API + "teams(t1)/teamroles_association").respond(200, json={"value": [{"roleid": "role-copy"}]})
    create = respx.post(API + "teams").mock(return_value=httpx.Response(204))
    assign = respx.post(API + "teams(t1)/teamroles_association/$ref").mock(return_value=httpx.Response(204))
    assert security.ensure_owner_teams(new_client(), {"Nordstern Energie": ENERGIE}) == {"Nordstern Energie": "t1"}
    assert create.call_count == 0 and assign.call_count == 0


@respx.mock
def test_missing_owner_role_in_the_unit_raises_after_waiting():
    respx.get(API + "WhoAmI").respond(200, json={"UserId": "app-user"})
    respx.get(API + "teams").respond(200, json={"value": [{"teamid": "t1"}]})
    respx.get(API + "roles").respond(200, json={"value": []})
    with pytest.raises(RuntimeError, match="nst Datenbesitz"):
        security.ensure_owner_teams(new_client(), {"Nordstern Energie": ENERGIE})
