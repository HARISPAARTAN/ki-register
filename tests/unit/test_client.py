import httpx
import pytest
import respx

from kiregister.client import DataverseClient, DataverseError

API = "https://org.crm4.dynamics.com/api/data/v9.2/"


class Tokens:
    def token(self):
        return "t0ken"


@respx.mock
def test_get_sends_odata_headers_and_bearer():
    route = respx.get(API + "WhoAmI").mock(return_value=httpx.Response(200, json={"UserId": "u"}))
    c = DataverseClient(API, Tokens())
    assert c.get("WhoAmI") == {"UserId": "u"}
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer t0ken" and req.headers["OData-Version"] == "4.0" and req.headers["Accept"] == "application/json"


@respx.mock
def test_post_adds_solution_header_and_returns_entity_id():
    route = respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(
        204, headers={"OData-EntityId": API + "EntityDefinitions(5d3a9e2a-0000-0000-0000-000000000001)"}))
    c = DataverseClient(API, Tokens(), solution="NordsternKIRegister")
    assert c.post("EntityDefinitions", {"SchemaName": "x"}) == "5d3a9e2a-0000-0000-0000-000000000001"
    assert route.calls.last.request.headers["MSCRM.SolutionUniqueName"] == "NordsternKIRegister"


@respx.mock
def test_retries_on_429_with_retry_after_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("kiregister.client.time.sleep", lambda s: sleeps.append(s))
    respx.get(API + "roles").mock(side_effect=[httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json={"value": []})])
    c = DataverseClient(API, Tokens())
    assert c.get("roles") == {"value": []}
    assert sleeps == [2.0]


@respx.mock
def test_error_carries_dataverse_message(monkeypatch):
    monkeypatch.setattr("kiregister.client.time.sleep", lambda s: None)
    respx.post(API + "roles").mock(return_value=httpx.Response(400, json={"error": {"code": "0x80040203", "message": "Attribute nst_x missing"}}))
    c = DataverseClient(API, Tokens())
    with pytest.raises(DataverseError) as exc:
        c.post("roles", {"name": "x"})
    assert exc.value.status == 400 and "nst_x" in str(exc.value) and "roles" in str(exc.value)


@respx.mock
def test_get_all_follows_next_link():
    # the more specific route is registered first: respx matches a query-less pattern against any query string
    respx.get(API + "systemusers?$skiptoken=2").mock(return_value=httpx.Response(200, json={"value": [{"a": 2}]}))
    respx.get(API + "systemusers").mock(return_value=httpx.Response(200, json={"value": [{"a": 1}], "@odata.nextLink": API + "systemusers?$skiptoken=2"}))
    assert DataverseClient(API, Tokens()).get_all("systemusers") == [{"a": 1}, {"a": 2}]


@respx.mock
def test_find_one_returns_none_when_empty():
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": []}))
    assert DataverseClient(API, Tokens()).find_one("publishers", "uniquename eq 'nordstern'") is None
