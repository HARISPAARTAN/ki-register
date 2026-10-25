from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from kiregister.client import DataverseClient, DataverseError

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
GUID = "5d3a9e2a-0000-0000-0000-000000000001"


class Tokens:
    def token(self):
        return "t0ken"


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr("kiregister.client.time.sleep", lambda s: recorded.append(s))
    return recorded


@respx.mock
def test_get_sends_odata_headers_and_bearer():
    route = respx.get(API + "WhoAmI").mock(return_value=httpx.Response(200, json={"UserId": "u"}))
    c = DataverseClient(API, Tokens())
    assert c.get("WhoAmI") == {"UserId": "u"}
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer t0ken" and req.headers["OData-Version"] == "4.0" and req.headers["Accept"] == "application/json"
    assert "Prefer" not in req.headers and "MSCRM.SolutionUniqueName" not in req.headers


@respx.mock
def test_get_never_sends_the_solution_header_even_when_configured():
    route = respx.get(API + "WhoAmI").mock(return_value=httpx.Response(200, json={}))
    DataverseClient(API, Tokens(), solution="S").get("WhoAmI")
    assert "MSCRM.SolutionUniqueName" not in route.calls.last.request.headers


@respx.mock
def test_post_adds_solution_header_and_returns_entity_id():
    route = respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(
        204, headers={"OData-EntityId": API + f"EntityDefinitions({GUID})"}))
    c = DataverseClient(API, Tokens(), solution="NordsternKIRegister")
    assert c.post("EntityDefinitions", {"SchemaName": "x"}) == GUID
    assert route.calls.last.request.headers["MSCRM.SolutionUniqueName"] == "NordsternKIRegister"


@respx.mock
def test_post_without_solution_flag_omits_the_header():
    route = respx.post(API + "publishers").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + f"publishers({GUID})"}))
    DataverseClient(API, Tokens(), solution="S").post("publishers", {}, solution=False)
    assert "MSCRM.SolutionUniqueName" not in route.calls.last.request.headers


@respx.mock
def test_create_without_configured_solution_raises_and_sends_nothing():
    route = respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(204))
    with pytest.raises(ValueError, match="Lösung nicht gesetzt"):
        DataverseClient(API, Tokens()).post("EntityDefinitions", {"SchemaName": "x"})
    assert not route.called


@respx.mock
def test_action_defaults_to_solution_header_and_can_opt_out():
    route = respx.post(API + "PublishXml").mock(return_value=httpx.Response(204))
    c = DataverseClient(API, Tokens(), solution="S")
    c.action("PublishXml", {"ParameterXml": "<x/>"})
    assert route.calls.last.request.headers["MSCRM.SolutionUniqueName"] == "S"
    c.action("PublishXml", {"ParameterXml": "<x/>"}, solution=False)
    assert "MSCRM.SolutionUniqueName" not in route.calls.last.request.headers
    with pytest.raises(ValueError):
        DataverseClient(API, Tokens()).action("PublishXml")


@respx.mock
def test_action_uses_the_long_timeout():
    route = respx.post(API + "PublishAllXml").mock(return_value=httpx.Response(204))
    DataverseClient(API, Tokens()).action("PublishAllXml", solution=False)
    assert route.calls.last.request.extensions["timeout"]["read"] == 300.0


@respx.mock
def test_retries_on_429_with_retry_after_then_succeeds(sleeps):
    respx.get(API + "roles").mock(side_effect=[httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json={"value": []})])
    c = DataverseClient(API, Tokens())
    assert c.get("roles") == {"value": []}
    assert sleeps == [2.0]


@respx.mock
def test_retry_exhaustion_makes_six_requests_with_exponential_backoff(sleeps):
    route = respx.get(API + "roles").mock(return_value=httpx.Response(503, json={"error": {"code": "x", "message": "down"}}))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).get("roles")
    assert exc.value.status == 503
    assert route.call_count == 6
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0]


@respx.mock
def test_post_retries_429_and_503(sleeps):
    route = respx.post(API + "roles").mock(side_effect=[httpx.Response(429), httpx.Response(503), httpx.Response(204)])
    DataverseClient(API, Tokens()).post("roles", {}, solution=False)
    assert route.call_count == 3 and sleeps == [1.0, 2.0]


@pytest.mark.parametrize("status", [502, 504])
@respx.mock
def test_get_retries_gateway_errors_but_post_does_not(sleeps, status):
    get_route = respx.get(API + "roles").mock(side_effect=[httpx.Response(status), httpx.Response(200, json={"value": []})])
    assert DataverseClient(API, Tokens()).get("roles") == {"value": []}
    assert get_route.call_count == 2
    post_route = respx.post(API + "roles").mock(return_value=httpx.Response(status))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).post("roles", {}, solution=False)
    assert exc.value.status == status and post_route.call_count == 1


@respx.mock
def test_patch_does_not_retry_gateway_errors(sleeps):
    route = respx.patch(API + "roles(1)").mock(return_value=httpx.Response(502))
    with pytest.raises(DataverseError):
        DataverseClient(API, Tokens()).patch("roles(1)", {}, solution=False)
    assert route.call_count == 1 and sleeps == []


@respx.mock
def test_retry_after_http_date(sleeps):
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    respx.get(API + "roles").mock(side_effect=[httpx.Response(429, headers={"Retry-After": when}), httpx.Response(200, json={})])
    DataverseClient(API, Tokens()).get("roles")
    assert 20 < sleeps[0] <= 30


@respx.mock
def test_retry_after_date_in_the_past_waits_zero(sleeps):
    when = format_datetime(datetime.now(UTC) - timedelta(seconds=30), usegmt=True)
    respx.get(API + "roles").mock(side_effect=[httpx.Response(429, headers={"Retry-After": when}), httpx.Response(200, json={})])
    DataverseClient(API, Tokens()).get("roles")
    assert sleeps == [0.0]


@respx.mock
def test_retry_after_nonsense_falls_back_to_backoff(sleeps):
    respx.get(API + "roles").mock(side_effect=[httpx.Response(429, headers={"Retry-After": "bald"}),
                                               httpx.Response(429, headers={"Retry-After": "bald"}), httpx.Response(200, json={})])
    DataverseClient(API, Tokens()).get("roles")
    assert sleeps == [1.0, 2.0]


@respx.mock
def test_retry_after_is_capped(sleeps):
    respx.get(API + "roles").mock(side_effect=[httpx.Response(429, headers={"Retry-After": "99999"}), httpx.Response(200, json={})])
    DataverseClient(API, Tokens()).get("roles")
    assert sleeps == [120.0]


@respx.mock
def test_get_retries_transport_errors_then_succeeds(sleeps):
    route = respx.get(API + "roles").mock(side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"value": []})])
    assert DataverseClient(API, Tokens()).get("roles") == {"value": []}
    assert route.call_count == 2 and sleeps == [1.0]


@respx.mock
def test_get_transport_error_exhaustion_raises_dataverse_error(sleeps):
    route = respx.get(API + "roles").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).get("roles")
    assert exc.value.status == 0 and exc.value.code == "transport" and route.call_count == 6


@respx.mock
def test_post_transport_error_is_not_retried(sleeps):
    route = respx.post(API + "roles").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).post("roles", {}, solution=False, component="nst_x")
    assert exc.value.status == 0 and exc.value.code == "transport" and "nst_x" in str(exc.value)
    assert route.call_count == 1 and sleeps == []


@respx.mock
def test_error_carries_dataverse_message(sleeps):
    respx.post(API + "roles").mock(return_value=httpx.Response(400, json={"error": {"code": "0x80040203", "message": "Attribute nst_x missing"}}))
    c = DataverseClient(API, Tokens())
    with pytest.raises(DataverseError) as exc:
        c.post("roles", {"name": "x"}, solution=False)
    assert exc.value.status == 400 and exc.value.code == "0x80040203" and "nst_x" in str(exc.value) and "roles" in str(exc.value)
    assert exc.value.path == "roles" and exc.value.message == "Attribute nst_x missing"


@respx.mock
def test_error_names_the_component():
    respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(400, json={"error": {"code": "c", "message": "m"}}))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens(), solution="S").post("EntityDefinitions", {}, component="nst_kisystem")
    assert str(exc.value) == "400 c bei nst_kisystem (EntityDefinitions): m"
    assert exc.value.component == "nst_kisystem"


@pytest.mark.parametrize("body", [["oops"], "text", {"error": "plain string"}, {"error": None}])
@respx.mock
def test_non_dict_error_body_does_not_crash(body):
    respx.get(API + "roles").mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).get("roles")
    assert exc.value.status == 400


@respx.mock
def test_non_json_error_body_uses_the_text():
    respx.get(API + "roles").mock(return_value=httpx.Response(400, text="<html>bad</html>"))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).get("roles")
    assert "bad" in exc.value.message


@respx.mock
def test_get_all_follows_next_link():
    # the more specific route is registered first: respx matches a query-less pattern against any query string
    respx.get(API + "systemusers?$skiptoken=2").mock(return_value=httpx.Response(200, json={"value": [{"a": 2}]}))
    respx.get(API + "systemusers").mock(return_value=httpx.Response(200, json={"value": [{"a": 1}], "@odata.nextLink": API + "systemusers?$skiptoken=2"}))
    assert DataverseClient(API, Tokens()).get_all("systemusers") == [{"a": 1}, {"a": 2}]


@respx.mock
def test_get_all_refuses_a_foreign_next_link_host():
    evil = respx.get("https://evil.example/steal").mock(return_value=httpx.Response(200, json={"value": []}))
    respx.get(API + "systemusers").mock(return_value=httpx.Response(200, json={"value": [], "@odata.nextLink": "https://evil.example/steal"}))
    with pytest.raises(DataverseError) as exc:
        DataverseClient(API, Tokens()).get_all("systemusers")
    assert exc.value.code == "nextlink" and not evil.called


@respx.mock
def test_find_one_returns_none_when_empty():
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": []}))
    assert DataverseClient(API, Tokens()).find_one("publishers", "uniquename eq 'nordstern'") is None


@respx.mock
def test_find_one_returns_the_first_row_and_sends_filter_top_select():
    route = respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": [{"publisherid": "p"}]}))
    assert DataverseClient(API, Tokens()).find_one("publishers", "uniquename eq 'n'", "publisherid") == {"publisherid": "p"}
    query = route.calls.last.request.url.params
    assert query["$filter"] == "uniquename eq 'n'" and query["$top"] == "1" and query["$select"] == "publisherid"


def test_context_manager_closes_the_http_client():
    with DataverseClient(API, Tokens()) as c:
        assert not c._http.is_closed
    assert c._http.is_closed


@respx.mock
def test_post_id_returns_the_id_and_rejects_a_missing_one():
    api = "https://org.crm4.dynamics.com/api/data/v9.2/"
    c = DataverseClient(api, type("T", (), {"token": lambda self: "t"})(), solution="S")
    respx.post(api + "things").mock(return_value=httpx.Response(204, headers={"OData-EntityId": api + "things(11111111-2222-3333-4444-555555555555)"}))
    assert c.post_id("things", {}) == "11111111-2222-3333-4444-555555555555"
    respx.post(api + "bare").mock(return_value=httpx.Response(204))
    with pytest.raises(DataverseError, match="ID"):
        c.post_id("bare", {})


@respx.mock
def test_get_text_returns_the_bare_answer_of_a_count_request():
    route = respx.get(API + "nst_kisystems/$count").mock(return_value=httpx.Response(200, content=(chr(0xFEFF) + "20\n").encode()))  # the service prefixes a byte order mark
    assert DataverseClient(API, Tokens()).get_text("nst_kisystems/$count") == "20"
    assert "MSCRM.SolutionUniqueName" not in route.calls.last.request.headers


@respx.mock
def test_get_text_raises_with_the_error_text():
    respx.get(API + "nst_kisystems/$count").mock(return_value=httpx.Response(404, json={"error": {"code": "0x0", "message": "nope"}}))
    with pytest.raises(DataverseError, match="nope"):
        DataverseClient(API, Tokens()).get_text("nst_kisystems/$count")
