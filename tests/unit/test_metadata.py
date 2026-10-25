from pathlib import Path

import httpx
import respx

from kiregister import metadata
from kiregister.client import DataverseClient
from kiregister.config import Settings
from kiregister.definitions import load_definitions

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
DEFS = load_definitions(Path(__file__).resolve().parents[2] / "provision" / "definitions")


class Tokens:
    def token(self):
        return "t"


def settings(tmp_path):
    return Settings(root=tmp_path, env_name="dev", url="https://org.crm4.dynamics.com", tenant_id="t", client_id="c", client_secret="s",
                    publisher_unique="nordstern", publisher_display="Nordstern Gruppe", prefix="nst", option_prefix=58000,
                    solution="NordsternKIRegister", solution_display="Nordstern KI-Register", solution_version="1.0.0.0",
                    definitions_dir=tmp_path, seed_dir=tmp_path)


@respx.mock
def test_ensure_choices_creates_missing_and_keeps_existing():
    existing = {"value": [{"Name": "nst_risikoklasse", "MetadataId": "aaaa"}]}
    respx.get(url__startswith=API + "GlobalOptionSetDefinitions").mock(return_value=httpx.Response(200, json=existing))
    created = respx.post(API + "GlobalOptionSetDefinitions").mock(
        return_value=httpx.Response(204, headers={"OData-EntityId": API + "GlobalOptionSetDefinitions(bbbb)"}))
    ids = metadata.ensure_choices(DataverseClient(API, Tokens(), solution="S"), DEFS, 58000)
    assert ids["nst_risikoklasse"] == "aaaa" and ids["nst_rolle_kivo"] == "bbbb"
    assert created.call_count == len(DEFS.choices) - 1


@respx.mock
def test_ensure_tables_skips_existing_entity():
    respx.get(url__startswith=API + "EntityDefinitions").mock(
        return_value=httpx.Response(200, json={"value": [{"LogicalName": t.schema, "MetadataId": "m-" + t.schema} for t in DEFS.tables]}))
    created = respx.post(API + "EntityDefinitions").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + "EntityDefinitions(x)"}))
    metadata.ensure_tables(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert created.call_count == 0


@respx.mock
def test_ensure_columns_posts_only_missing_attributes():
    def attrs(request, route):
        return httpx.Response(200, json={"value": [{"LogicalName": "nst_name"}, {"LogicalName": "nst_kennung"}]})
    respx.get(url__regex=r".*/EntityDefinitions\(LogicalName='nst_kisystem'\)/Attributes.*").mock(side_effect=attrs)
    respx.get(url__regex=r".*/EntityDefinitions\(LogicalName='(?!nst_kisystem).*'\)/Attributes.*").mock(
        return_value=httpx.Response(200, json={"value": [{"LogicalName": "everything"}]}))
    created = respx.post(url__regex=r".*/EntityDefinitions\(LogicalName='nst_kisystem'\)/Attributes").mock(
        return_value=httpx.Response(204, headers={"OData-EntityId": API + "x(y)"}))
    respx.post(url__regex=r".*/EntityDefinitions\(LogicalName='(?!nst_kisystem).*'\)/Attributes").mock(
        return_value=httpx.Response(204, headers={"OData-EntityId": API + "x(y)"}))
    choice_ids = {c.schema: "id-" + c.schema for c in DEFS.choices}
    metadata.ensure_columns(DataverseClient(API, Tokens(), solution="S"), DEFS, choice_ids)
    ki = DEFS.table("nst_kisystem")
    assert created.call_count == len(ki.columns) - 1  # nst_kennung already exists


@respx.mock
def test_ensure_relationships_creates_missing():
    respx.get(url__startswith=API + "RelationshipDefinitions").mock(
        return_value=httpx.Response(200, json={"value": [{"SchemaName": "nst_organisation_mitarbeiter"}]}))
    created = respx.post(API + "RelationshipDefinitions").mock(return_value=httpx.Response(204, headers={"OData-EntityId": API + "R(1)"}))
    metadata.ensure_relationships(DataverseClient(API, Tokens(), solution="S"), DEFS)
    assert created.call_count == len(DEFS.relationships) - 1


@respx.mock
def test_publish_all_calls_the_action():
    route = respx.post(API + "PublishAllXml").mock(return_value=httpx.Response(204))
    metadata.publish_all(DataverseClient(API, Tokens()))
    assert route.called
