import json

import httpx
import pytest
import respx

from kiregister import auditing
from kiregister.client import DataverseClient, DataverseError

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
ORG = "cccccccc-0000-0000-0000-00000000000c"
HEADER = "MSCRM.SolutionUniqueName"


class Tokens:
    def token(self):
        return "t"


def new_client():
    return DataverseClient(API, Tokens(), solution="NordsternKIRegister")


def organization(enabled):
    return httpx.Response(200, json={"value": [{"organizationid": ORG, "isauditenabled": enabled}]})


@respx.mock
@pytest.mark.parametrize("enabled", [True, False])
def test_audit_enabled_reads_the_organization_row_and_reports_the_switch(enabled):
    route = respx.get(API + "organizations").mock(return_value=organization(enabled))
    assert auditing.audit_enabled(new_client()) is enabled
    assert route.call_count == 1
    assert route.calls[0].request.url.params["$select"] == "organizationid,isauditenabled"
    assert [c.request.method for c in respx.calls] == ["GET"]


@respx.mock
def test_ensure_auditing_reads_first_and_sends_no_patch_when_the_switch_is_already_on():
    respx.get(API + "organizations").mock(return_value=organization(True))
    patch = respx.patch(url__startswith=API + "organizations").mock(return_value=httpx.Response(204))
    assert auditing.ensure_auditing(new_client()) is False
    assert [c.request.method for c in respx.calls] == ["GET"]
    assert patch.call_count == 0


@respx.mock
def test_ensure_auditing_sends_exactly_one_patch_after_the_read_when_the_switch_is_off():
    respx.get(API + "organizations").mock(return_value=organization(False))
    patch = respx.patch(API + f"organizations({ORG})").mock(return_value=httpx.Response(204))
    assert auditing.ensure_auditing(new_client()) is True
    assert [c.request.method for c in respx.calls] == ["GET", "PATCH"]
    request = patch.calls[0].request
    assert json.loads(request.content) == {"isauditenabled": True}
    assert HEADER not in request.headers  # organization settings are not solution components


@respx.mock
def test_a_second_run_after_the_switch_is_on_changes_nothing():
    state = {"on": False}

    def read(request):
        return organization(state["on"])

    def write(request):
        state["on"] = json.loads(request.content)["isauditenabled"]
        return httpx.Response(204)

    respx.get(API + "organizations").mock(side_effect=read)
    patch = respx.patch(API + f"organizations({ORG})").mock(side_effect=write)
    client = new_client()
    assert auditing.ensure_auditing(client) is True
    assert auditing.ensure_auditing(client) is False
    assert patch.call_count == 1


@respx.mock
def test_a_refused_patch_stops_with_the_error_text_and_the_component_name():
    respx.get(API + "organizations").mock(return_value=organization(False))
    respx.patch(API + f"organizations({ORG})").mock(
        return_value=httpx.Response(403, json={"error": {"code": "0x80040220", "message": "SecLib::CheckPrivilege failed"}}))
    with pytest.raises(DataverseError, match=r"403 0x80040220 bei Umgebungs-Auditing .*SecLib::CheckPrivilege failed"):
        auditing.ensure_auditing(new_client())


@respx.mock
@pytest.mark.parametrize("rows", [[], [{"organizationid": ORG, "isauditenabled": True}, {"organizationid": "other", "isauditenabled": True}]])
def test_anything_but_exactly_one_organization_row_is_an_error(rows):
    respx.get(API + "organizations").mock(return_value=httpx.Response(200, json={"value": rows}))
    patch = respx.patch(url__startswith=API + "organizations").mock(return_value=httpx.Response(204))
    with pytest.raises(RuntimeError, match="Organisation"):
        auditing.ensure_auditing(new_client())
    assert patch.call_count == 0
