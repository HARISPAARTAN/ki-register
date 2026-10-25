import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from kiregister import app
from kiregister.client import DataverseClient
from kiregister.config import load_settings
from kiregister.definitions import load_definitions

API = "https://org.crm4.dynamics.com/api/data/v9.2/"
ROOT = Path(__file__).resolve().parents[2]
DEFS = load_definitions(ROOT / "provision" / "definitions")
SETTINGS = load_settings("dev", ROOT)
NEW = "00000000-0000-0000-0000-0000000000b2"
APP_ID = "00000000-0000-0000-0000-0000000000c1"
SM_ID = "00000000-0000-0000-0000-0000000000d1"


class Tokens:
    def token(self):
        return "t"


def new_client():
    return DataverseClient(API, Tokens(), solution="NordsternKIRegister")


def created(entity_set: str, new_id: str = NEW):
    return httpx.Response(204, headers={"OData-EntityId": API + f"{entity_set}({new_id})"})


def all_view_ids():
    views = list(DEFS.app.views) + [v for v in (app.builders.default_view(t, DEFS) for t in DEFS.tables)
                                    if not any(x.table == v.table and x.default for x in DEFS.app.views)]
    return {(v.table, v.name): f"00000000-0000-0000-0001-{i:012d}" for i, v in enumerate(views)}


def chart_ids():
    return {(c.table, c.name): f"00000000-0000-0000-0002-{i:012d}" for i, c in enumerate(DEFS.app.charts)}


@respx.mock
def test_object_type_code_reads_the_entity_definition():
    route = respx.get(url__startswith=API + "EntityDefinitions(LogicalName='nst_kisystem')").respond(200, json={"ObjectTypeCode": 10625})
    assert app.object_type_code(new_client(), "nst_kisystem") == 10625
    assert "ObjectTypeCode" in str(route.calls[0].request.url)


def test_dashboard_formxml_has_one_control_per_component_in_two_columns():
    views, charts = all_view_ids(), chart_ids()
    xml = app.dashboard_formxml(DEFS.app.dashboard, views, charts, DEFS)
    comps = DEFS.app.dashboard.components
    assert xml.count("<control ") == len(comps) == 4
    assert xml.count("<row>") == 2 and all(r.count("<cell ") == 2 for r in re.findall(r"<row>.*?</row>", xml))
    for comp in comps:
        if comp.chart:
            assert f"<VisualizationId>{{{charts[(comp.table, comp.chart)]}}}</VisualizationId>" in xml
        assert f"<ViewId>{{{views[(comp.table, comp.view or comp.list)]}}}</ViewId>" in xml
    assert xml.count("<VisualizationId>") == 3
    # every id in the markup is a real GUID (the form schema rejects anything else)
    for value in re.findall(r' id="(\{[^}]*\})"', xml):
        assert re.fullmatch(r"\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}", value), value


def test_dashboard_formxml_fails_on_an_unknown_view():
    with pytest.raises(KeyError):
        app.dashboard_formxml(DEFS.app.dashboard, {}, chart_ids(), DEFS)


def test_app_components_cover_tables_forms_views_charts_and_dashboard():
    forms = {t.schema: f"form-{t.schema}" for t in DEFS.tables}
    views, charts = all_view_ids(), chart_ids()
    entity_ids = {t.schema: f"meta-{t.schema}" for t in DEFS.tables}
    comps = app.app_components(DEFS, forms, views, charts, "dash-1", entity_ids)
    by_type = {}
    for c in comps:
        by_type.setdefault(c["@odata.type"].rsplit(".", 1)[1], []).append(c)
    area_tables = [t for a in DEFS.app.areas for t in a.tables]
    assert sorted(c["entityid"] for c in by_type["entity"]) == sorted(f"meta-{t}" for t in area_tables)
    assert {c["formid"] for c in by_type["systemform"]} == set(forms.values()) | {"dash-1"}
    assert {c["savedqueryid"] for c in by_type["savedquery"]} == set(views.values())
    assert {c["savedqueryvisualizationid"] for c in by_type["savedqueryvisualization"]} == set(charts.values())


@respx.mock
def test_ensure_views_creates_missing_views_with_the_object_type_code():
    respx.get(url__startswith=API + "EntityDefinitions").respond(200, json={"ObjectTypeCode": 10625})
    respx.get(API + "savedqueries").respond(200, json={"value": []})
    create = respx.post(API + "savedqueries").mock(return_value=created("savedqueries"))
    ids = app.ensure_views(new_client(), DEFS, 58000)
    assert create.call_count == len(ids) == 13
    pruefung = next(json.loads(c.request.content) for c in create.calls if json.loads(c.request.content)["name"] == "Prüfung überfällig")
    assert pruefung["returnedtypecode"] == "nst_kisystem" and "olderthan-x-days" in pruefung["fetchxml"]
    assert 'object="10625"' in pruefung["layoutxml"]
    assert ("nst_kisystem", "Prüfung überfällig") in ids


@respx.mock
def test_ensure_views_updates_an_existing_view():
    respx.get(url__startswith=API + "EntityDefinitions").respond(200, json={"ObjectTypeCode": 10625})
    respx.get(API + "savedqueries").respond(200, json={"value": [{"savedqueryid": "sq-1"}]})
    create = respx.post(API + "savedqueries").mock(return_value=created("savedqueries"))
    patch = respx.patch(API + "savedqueries(sq-1)").mock(return_value=httpx.Response(204))
    app.ensure_views(new_client(), DEFS, 58000)
    assert create.call_count == 0 and patch.call_count == 13


@respx.mock
def test_ensure_forms_embeds_the_view_ids_and_raises_on_a_missing_one():
    respx.get(API + "systemforms").respond(200, json={"value": []})
    create = respx.post(API + "systemforms").mock(return_value=created("systemforms"))
    ids = app.ensure_forms(new_client(), DEFS, all_view_ids())
    assert len(ids) == len(DEFS.tables) == create.call_count
    ki = next(json.loads(c.request.content) for c in create.calls if json.loads(c.request.content)["objecttypecode"] == "nst_kisystem")
    assert ki["type"] == app.FORM_MAIN and "00000000-0000-0000-0000-000000000000" not in ki["formxml"]
    with pytest.raises(KeyError):
        app.ensure_forms(new_client(), DEFS, {})


@respx.mock
def test_ensure_charts_posts_data_and_presentation_descriptions():
    respx.get(API + "savedqueryvisualizations").respond(200, json={"value": []})
    create = respx.post(API + "savedqueryvisualizations").mock(return_value=created("savedqueryvisualizations"))
    ids = app.ensure_charts(new_client(), DEFS)
    assert len(ids) == create.call_count == 3
    body = json.loads(create.calls[0].request.content)
    assert body["primaryentitytypecode"] == "nst_kisystem" and "<datadefinition>" in body["datadescription"] and "<Chart " in body["presentationdescription"]


@respx.mock
def test_ensure_dashboard_creates_a_type_0_form_then_updates_it():
    respx.get(API + "systemforms").mock(side_effect=[httpx.Response(200, json={"value": []}), httpx.Response(200, json={"value": [{"formid": "d1"}]})])
    create = respx.post(API + "systemforms").mock(return_value=created("systemforms"))
    patch = respx.patch(API + "systemforms(d1)").mock(return_value=httpx.Response(204))
    assert app.ensure_dashboard(new_client(), DEFS, all_view_ids(), chart_ids()) == NEW
    assert json.loads(create.calls[0].request.content)["type"] == app.FORM_DASHBOARD
    assert app.ensure_dashboard(new_client(), DEFS, all_view_ids(), chart_ids()) == "d1"
    assert patch.call_count == 1 and create.call_count == 1


@respx.mock
def test_find_app_module_falls_back_to_unpublished_apps():
    respx.get(API + "appmodules").respond(200, json={"value": []})
    respx.get(url__startswith=API + "appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple").respond(200, json={"value": [{"appmoduleid": APP_ID}]})
    assert app.find_app_module(new_client(), "nst_kiregister") == APP_ID


@respx.mock
def test_validate_app_returns_only_errors():
    respx.get(API + f"ValidateApp(AppModuleId={APP_ID})").respond(200, json={"AppValidationResponse": {"ValidationSuccess": True, "ValidationIssueList": [
        {"ErrorType": "Warning", "DisplayName": "w"}, {"ErrorType": "Error", "DisplayName": "e"}]}})
    assert app.validate_app(new_client(), APP_ID) == [{"ErrorType": "Error", "DisplayName": "e"}]


@respx.mock
def test_ensure_app_module_creates_the_app_and_sitemap_and_publishes():
    respx.get(API + "appmodules").respond(200, json={"value": []})
    respx.get(url__startswith=API + "appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple").respond(200, json={"value": []})
    respx.get(API + "sitemaps").respond(200, json={"value": []})
    respx.get(url__startswith=API + "EntityDefinitions").respond(200, json={"MetadataId": "meta"})
    create_app = respx.post(API + "appmodules").mock(return_value=created("appmodules", APP_ID))
    create_sm = respx.post(API + "sitemaps").mock(return_value=created("sitemaps", SM_ID))
    add = respx.post(API + "AddAppComponents").mock(return_value=httpx.Response(204))
    publish = respx.post(API + "PublishXml").mock(return_value=httpx.Response(204))
    respx.get(API + f"ValidateApp(AppModuleId={APP_ID})").respond(200, json={"AppValidationResponse": {"ValidationSuccess": True, "ValidationIssueList": []}})
    forms = {t.schema: f"form-{t.schema}" for t in DEFS.tables}
    assert app.ensure_app_module(new_client(), SETTINGS, DEFS, "dash-1", forms, all_view_ids(), chart_ids()) == APP_ID
    body = json.loads(create_app.calls[0].request.content)
    assert body["uniquename"] == "nst_kiregister" and body["webresourceid"] == app.DEFAULT_APP_ICON
    assert "{dash-1}" in json.loads(create_sm.calls[0].request.content)["sitemapxml"]
    comps = json.loads(add.calls[0].request.content)["Components"]
    assert comps[0] == {"@odata.type": "Microsoft.Dynamics.CRM.sitemap", "sitemapid": SM_ID}
    assert not [c for c in comps if c["@odata.type"].endswith(".entity")]
    assert APP_ID in json.loads(publish.calls[0].request.content)["ParameterXml"]
    assert "MSCRM.SolutionUniqueName" not in publish.calls[0].request.headers
