import dataclasses
import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from kiregister import metadata
from kiregister.client import DataverseClient, DataverseError
from kiregister.config import Settings
from kiregister.definitions import load_definitions

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
DEFS = load_definitions(Path(__file__).resolve().parents[2] / "provision" / "definitions")
GUID_B = "bbbbbbbb-0000-0000-0000-00000000000b"
HEADER = "MSCRM.SolutionUniqueName"


class Tokens:
    def token(self):
        return "t"


def settings(tmp_path):
    return Settings(root=tmp_path, env_name="dev", url="https://org.crm4.dynamics.com", tenant_id="t", client_id="c", client_secret="s",
                    publisher_unique="nordstern", publisher_display="Nordstern Gruppe", prefix="nst", option_prefix=58000,
                    solution="NordsternKIRegister", solution_display="Nordstern KI-Register", solution_version="1.0.0.0",
                    definitions_dir=tmp_path, seed_dir=tmp_path)


def created_entity(url_tail: str, guid: str = GUID_B):
    return httpx.Response(204, headers={"OData-EntityId": API + f"{url_tail}({guid})"})


def assert_solution_header(route, expected="S"):
    assert route.call_count > 0
    assert all(call.request.headers.get(HEADER) == expected for call in route.calls)


@respx.mock
def test_ensure_publisher_and_solution_reuses_publisher_and_creates_solution_without_header(tmp_path):
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": [{"publisherid": "pub-1"}]}))
    respx.get(url__startswith=API + "solutions").mock(return_value=httpx.Response(200, json={"value": []}))
    pub_post = respx.post(API + "publishers").mock(return_value=created_entity("publishers"))
    sol_post = respx.post(API + "solutions").mock(return_value=created_entity("solutions"))
    metadata.ensure_publisher_and_solution(DataverseClient(API, Tokens(), solution="S"), settings(tmp_path))
    assert not pub_post.called and sol_post.call_count == 1
    request = sol_post.calls.last.request
    body = json.loads(request.content)
    assert body["publisherid@odata.bind"] == "/publishers(pub-1)" and body["uniquename"] == "NordsternKIRegister"
    assert body["version"] == "1.0.0.0" and HEADER not in request.headers


@respx.mock
def test_ensure_publisher_and_solution_creates_publisher_when_missing(tmp_path):
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": []}))
    respx.get(url__startswith=API + "solutions").mock(return_value=httpx.Response(200, json={"value": []}))
    pub_post = respx.post(API + "publishers").mock(return_value=created_entity("publishers", "11111111-0000-0000-0000-000000000001"))
    sol_post = respx.post(API + "solutions").mock(return_value=created_entity("solutions"))
    metadata.ensure_publisher_and_solution(DataverseClient(API, Tokens(), solution="S"), settings(tmp_path))
    body = json.loads(pub_post.calls.last.request.content)
    assert body["uniquename"] == "nordstern" and body["customizationprefix"] == "nst" and body["customizationoptionvalueprefix"] == 58000
    assert HEADER not in pub_post.calls.last.request.headers
    assert json.loads(sol_post.calls.last.request.content)["publisherid@odata.bind"] == "/publishers(11111111-0000-0000-0000-000000000001)"


@pytest.mark.parametrize("version", ["1.0.0.0", "1.1.0.0"])
@respx.mock
def test_ensure_publisher_and_solution_does_nothing_when_both_exist_with_the_configured_version(tmp_path, version):
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": [{"publisherid": "p"}]}))
    respx.get(url__startswith=API + "solutions").mock(return_value=httpx.Response(200, json={"value": [{"solutionid": "s", "version": version}]}))
    pub_post = respx.post(API + "publishers").mock(return_value=created_entity("publishers"))
    sol_post = respx.post(API + "solutions").mock(return_value=created_entity("solutions"))
    sol_patch = respx.patch(API + "solutions(s)").mock(return_value=httpx.Response(204))
    configured = dataclasses.replace(settings(tmp_path), solution_version=version)
    metadata.ensure_publisher_and_solution(DataverseClient(API, Tokens(), solution="S"), configured)
    assert not pub_post.called and not sol_post.called and not sol_patch.called


@respx.mock
def test_ensure_publisher_and_solution_raises_the_version_of_an_existing_solution_once(tmp_path):
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": [{"publisherid": "p"}]}))
    solutions = respx.get(url__startswith=API + "solutions").mock(side_effect=[
        httpx.Response(200, json={"value": [{"solutionid": "sol-1", "version": "1.0.0.0"}]}),
        httpx.Response(200, json={"value": [{"solutionid": "sol-1", "version": "1.1.0.0"}]})])  # the second run sees the raised version
    sol_post = respx.post(API + "solutions").mock(return_value=created_entity("solutions"))
    sol_patch = respx.patch(API + "solutions(sol-1)").mock(return_value=httpx.Response(204))
    configured = dataclasses.replace(settings(tmp_path), solution_version="1.1.0.0")
    client = DataverseClient(API, Tokens(), solution="S")
    metadata.ensure_publisher_and_solution(client, configured)
    metadata.ensure_publisher_and_solution(client, configured)
    assert solutions.call_count == 2 and sol_patch.call_count == 1 and not sol_post.called
    request = sol_patch.calls.last.request
    assert json.loads(request.content) == {"version": "1.1.0.0"} and HEADER not in request.headers


@respx.mock
def test_a_failing_version_patch_names_the_solution(tmp_path):
    respx.get(url__startswith=API + "publishers").mock(return_value=httpx.Response(200, json={"value": [{"publisherid": "p"}]}))
    respx.get(url__startswith=API + "solutions").mock(return_value=httpx.Response(200, json={"value": [{"solutionid": "sol-1", "version": "1.0.0.0"}]}))
    respx.patch(API + "solutions(sol-1)").mock(return_value=httpx.Response(400, json={"error": {"code": "c", "message": "verwaltet"}}))
    configured = dataclasses.replace(settings(tmp_path), solution_version="1.1.0.0")
    with pytest.raises(DataverseError) as exc:
        metadata.ensure_publisher_and_solution(DataverseClient(API, Tokens(), solution="S"), configured)
    assert "NordsternKIRegister" in str(exc.value) and "verwaltet" in str(exc.value)


@respx.mock
def test_ensure_choices_creates_missing_and_keeps_existing():
    existing = {"value": [{"Name": "nst_risikoklasse", "MetadataId": "aaaa"}]}
    respx.get(url__startswith=API + "GlobalOptionSetDefinitions").mock(return_value=httpx.Response(200, json=existing))
    created = respx.post(API + "GlobalOptionSetDefinitions").mock(return_value=created_entity("GlobalOptionSetDefinitions"))
    ids = metadata.ensure_choices(DataverseClient(API, Tokens(), solution="S"), DEFS, 58000)
    assert ids["nst_risikoklasse"] == "aaaa" and ids["nst_rolle_kivo"] == GUID_B
    assert created.call_count == len(DEFS.choices) - 1
    assert_solution_header(created)


@respx.mock
def test_ensure_tables_skips_existing_entity():
    respx.get(url__startswith=API + "EntityDefinitions").mock(
        return_value=httpx.Response(200, json={"value": [{"LogicalName": t.schema, "MetadataId": "m-" + t.schema} for t in DEFS.tables]}))
    created = respx.post(API + "EntityDefinitions").mock(return_value=created_entity("EntityDefinitions"))
    metadata.ensure_tables(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert created.call_count == 0


@respx.mock
def test_ensure_tables_creates_missing_with_solution_header():
    present = [t for t in DEFS.tables if t.schema != "nst_kisystem"]
    respx.get(url__startswith=API + "EntityDefinitions").mock(
        return_value=httpx.Response(200, json={"value": [{"LogicalName": t.schema} for t in present]}))
    created = respx.post(API + "EntityDefinitions").mock(return_value=created_entity("EntityDefinitions"))
    metadata.ensure_tables(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert created.call_count == 1 and json.loads(created.calls.last.request.content)["SchemaName"] == "nst_kisystem"
    assert_solution_header(created)


@respx.mock
def test_failing_table_create_names_the_table():
    respx.get(url__startswith=API + "EntityDefinitions").mock(return_value=httpx.Response(200, json={"value": []}))
    respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(400, json={"error": {"code": "0x1", "message": "kaputt"}}))
    first = DEFS.tables[0].schema
    with pytest.raises(DataverseError) as exc:
        metadata.ensure_tables(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert exc.value.component == first and first in str(exc.value) and "kaputt" in str(exc.value)


@respx.mock
def test_failing_kisystem_create_names_nst_kisystem():
    present = [t for t in DEFS.tables if t.schema != "nst_kisystem"]
    respx.get(url__startswith=API + "EntityDefinitions").mock(
        return_value=httpx.Response(200, json={"value": [{"LogicalName": t.schema} for t in present]}))
    respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(400, json={"error": {"code": "0x1", "message": "kaputt"}}))
    with pytest.raises(DataverseError) as exc:
        metadata.ensure_tables(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert "nst_kisystem" in str(exc.value)


@respx.mock
def test_ensure_columns_posts_only_missing_attributes():
    def attrs(request, route):
        return httpx.Response(200, json={"value": [{"LogicalName": "nst_name"}, {"LogicalName": "nst_kennung"}]})
    respx.get(url__regex=r".*/EntityDefinitions\(LogicalName='nst_kisystem'\)/Attributes.*").mock(side_effect=attrs)
    respx.get(url__regex=r".*/EntityDefinitions\(LogicalName='(?!nst_kisystem).*'\)/Attributes.*").mock(
        return_value=httpx.Response(200, json={"value": [{"LogicalName": "everything"}]}))
    created = respx.post(url__regex=r".*/EntityDefinitions\(LogicalName='nst_kisystem'\)/Attributes").mock(
        return_value=created_entity("x"))
    other = respx.post(url__regex=r".*/EntityDefinitions\(LogicalName='(?!nst_kisystem).*'\)/Attributes").mock(
        return_value=created_entity("x"))
    choice_ids = {c.schema: "id-" + c.schema for c in DEFS.choices}
    metadata.ensure_columns(DataverseClient(API, Tokens(), solution="S"), DEFS, choice_ids)
    ki = DEFS.table("nst_kisystem")
    assert created.call_count == len(ki.columns) - 1  # nst_kennung already exists
    assert_solution_header(created)
    assert_solution_header(other)


def _columns_mock(missing_column: str, post_response: httpx.Response):
    """All columns exist everywhere except `missing_column` on nst_kisystem; the create answers with `post_response`."""
    def attrs(request, route):
        table = re.search(r"LogicalName='([^']+)'", str(request.url)).group(1)
        names = [c.schema for c in DEFS.table(table).columns if not (table == "nst_kisystem" and c.schema == missing_column)]
        return httpx.Response(200, json={"value": [{"LogicalName": n} for n in names]})
    respx.get(url__regex=r".*/EntityDefinitions\(LogicalName='[^']+'\)/Attributes.*").mock(side_effect=attrs)
    return respx.post(url__regex=r".*/EntityDefinitions\(LogicalName='nst_kisystem'\)/Attributes").mock(return_value=post_response)


@respx.mock
def test_formula_column_rejected_with_400_is_skipped_with_a_warning(caplog):
    route = _columns_mock("nst_pruefungueberfaellig", httpx.Response(400, json={"error": {"code": "c", "message": "keine Formeln"}}))
    metadata.ensure_columns(DataverseClient(API, Tokens(), solution="S"), DEFS, {c.schema: "id" for c in DEFS.choices})
    assert route.call_count == 1
    assert "nst_pruefungueberfaellig" in caplog.text


@respx.mock
def test_formula_column_with_403_re_raises():
    _columns_mock("nst_pruefungueberfaellig", httpx.Response(403, json={"error": {"code": "c", "message": "verboten"}}))
    with pytest.raises(DataverseError) as exc:
        metadata.ensure_columns(DataverseClient(API, Tokens(), solution="S"), DEFS, {c.schema: "id" for c in DEFS.choices})
    assert exc.value.status == 403 and exc.value.component == "nst_kisystem.nst_pruefungueberfaellig"


@respx.mock
def test_non_formula_column_with_400_re_raises():
    _columns_mock("nst_kennung", httpx.Response(400, json={"error": {"code": "c", "message": "ungueltig"}}))
    with pytest.raises(DataverseError) as exc:
        metadata.ensure_columns(DataverseClient(API, Tokens(), solution="S"), DEFS, {c.schema: "id" for c in DEFS.choices})
    assert exc.value.status == 400 and exc.value.component == "nst_kisystem.nst_kennung"


@respx.mock
def test_ensure_relationships_creates_missing():
    respx.get(url__startswith=API + "RelationshipDefinitions").mock(
        return_value=httpx.Response(200, json={"value": [{"SchemaName": "nst_organisation_mitarbeiter"}]}))
    created = respx.post(API + "RelationshipDefinitions").mock(return_value=created_entity("R"))
    metadata.ensure_relationships(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert created.call_count == len(DEFS.relationships) - 1
    assert_solution_header(created)


@respx.mock
def test_failing_relationship_create_names_the_relationship():
    respx.get(url__startswith=API + "RelationshipDefinitions").mock(return_value=httpx.Response(200, json={"value": []}))
    respx.post(API + "RelationshipDefinitions").mock(return_value=httpx.Response(400, json={"error": {"code": "c", "message": "m"}}))
    with pytest.raises(DataverseError) as exc:
        metadata.ensure_relationships(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert exc.value.component == DEFS.relationships[0].schema


@respx.mock
def test_publish_all_calls_the_action():
    route = respx.post(API + "PublishAllXml").mock(return_value=httpx.Response(204))
    metadata.publish_all(DataverseClient(API, Tokens()))
    assert route.called
    assert HEADER not in route.calls.last.request.headers


@respx.mock
def test_apply_metadata_runs_in_dependency_order(tmp_path):
    log: list[tuple[str, str]] = []
    base = "/api/data/v9.2/"

    def handler(request):
        path = request.url.path[len(base):]
        log.append((request.method, path))
        if request.method == "POST":
            return created_entity("X")
        if path.startswith("EntityDefinitions("):
            return httpx.Response(200, json={"value": []})
        rows = {"publishers": [{"publisherid": "p"}], "solutions": [{"solutionid": "s"}]}.get(path, [])
        return httpx.Response(200, json={"value": rows})

    respx.route().mock(side_effect=handler)
    cfg = settings(tmp_path)
    result = metadata.apply_metadata(DataverseClient(API, Tokens(), solution=cfg.solution), cfg, DEFS)

    posts = [path for method, path in log if method == "POST"]

    def first(pred):
        return next(i for i, p in enumerate(posts) if pred(p))

    choices, tables = first(lambda p: p == "GlobalOptionSetDefinitions"), first(lambda p: p == "EntityDefinitions")
    columns, relationships = first(lambda p: p.endswith("/Attributes")), first(lambda p: p == "RelationshipDefinitions")
    assert choices < tables < columns < relationships
    assert posts[-1] == "PublishAllXml" and posts.count("PublishAllXml") == 1
    last_create = max(i for i, p in enumerate(posts) if p != "PublishAllXml")
    assert last_create < len(posts) - 1
    assert result == {"choices": len(DEFS.choices), "tables": len(DEFS.tables), "relationships": len(DEFS.relationships)}


@respx.mock
def test_apply_metadata_rejects_a_client_with_the_wrong_solution(tmp_path):
    route = respx.route().mock(return_value=httpx.Response(200, json={"value": []}))
    for client_solution in (None, "Andere"):
        with pytest.raises(ValueError):
            metadata.apply_metadata(DataverseClient(API, Tokens(), solution=client_solution), settings(tmp_path), DEFS)
    assert not route.called
