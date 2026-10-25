import pytest

from kiregister import app, security

pytestmark = pytest.mark.dataverse

# Stock roles are found by their template id: their names are translated in an environment with another base language (as in bootstrap.py).
SYSTEM_ADMINISTRATOR_TEMPLATE = "627090ff-40a3-4053-8790-584edc5be201"
SYSTEM_CUSTOMIZER_TEMPLATE = "119f245c-3cc8-4b62-b31c-d1a046ced15d"


def _app_id(client, settings):
    app_id = app.find_app_module(client, "nst_kiregister")
    assert app_id is not None
    return app_id


def test_app_module_exists_and_validates_without_errors(client, settings):
    app_id = _app_id(client, settings)
    assert app.validate_app(client, app_id) == []


def test_pruefung_ueberfaellig_view_filters_on_the_review_date(client):
    view = client.find_one("savedqueries", "name eq 'Prüfung überfällig' and returnedtypecode eq 'nst_kisystem'", "savedqueryid,fetchxml,layoutxml")
    assert view is not None
    assert "olderthan-x-days" in view["fetchxml"]
    assert 'object="0"' not in view["layoutxml"]


def test_dashboard_form_and_charts_exist(client, defs):
    dash = client.find_one("systemforms", f"name eq '{defs.app.dashboard.name}' and type eq {app.FORM_DASHBOARD}", "formid,formxml")
    assert dash is not None and dash["formxml"].count("<control ") == len(defs.app.dashboard.components)
    for chart in defs.app.charts:
        assert client.find_one("savedqueryvisualizations", f"name eq '{chart.name}' and primaryentitytypecode eq '{chart.table}'",
                               "savedqueryvisualizationid") is not None


def test_ki_system_form_has_the_five_tabs_and_real_view_ids(client, defs):
    form = client.find_one("systemforms", "name eq 'KI-System Hauptformular' and objecttypecode eq 'nst_kisystem' and type eq 2", "formxml")
    assert form is not None
    for tab in ("Allgemein", "Einstufung", "Daten und Betroffene", "Verlauf", "Intern"):
        assert f'name="{tab}"' in form["formxml"], tab
    assert "{00000000-0000-0000-0000-000000000000}" not in form["formxml"]


def test_every_defined_view_exists(client, defs):
    for v in defs.app.views:
        assert client.find_one("savedqueries", f"name eq '{v.name}' and returnedtypecode eq '{v.table}'", "savedqueryid") is not None, v.name


def _components(client, app_id):
    return sorted((x["componenttype"], x["objectid"]) for x in client.get(f"RetrieveAppComponents(AppModuleId={app_id})")["value"])


def test_the_tables_are_app_components_and_validate_app_reports_no_issue(client, settings, defs):
    """ADR-002: AddAppComponents cannot add tables on this org; the solution import (AppModuleComponent type 1) does. Without it
    ValidateApp warns about every component ("App does not reference at least one entity")."""
    app_id = _app_id(client, settings)
    assert [c[1] for c in _components(client, app_id) if c[0] == 1] == sorted(app.entity_metadata_ids(client, defs).values())
    assert app.validation_issues(client, app_id) == []


def _app_role_ids(client, app_id):
    return {r["roleid"] for r in client.get_all(f"appmodules({app_id})/appmoduleroles_association", {"$select": "roleid"})}


def _root_role_id(client, name):
    root, _ = security.root_business_unit(client)
    role = client.find_one("roles", f"name eq '{name}' and _businessunitid_value eq {root}", "roleid")
    assert role is not None, name
    return role["roleid"]


def _stock_role_id(client, template):
    """The stock role of the root unit with this `roletemplateid`. The filter needs the lookup spelling `_roletemplateid_value`;
    `roletemplateid eq <guid>` is rejected by the Web API (400, 0x80060888)."""
    root, _ = security.root_business_unit(client)
    role = client.find_one("roles", f"_roletemplateid_value eq {template} and _businessunitid_value eq {root}", "roleid")
    assert role is not None, template
    return role["roleid"]


def test_the_user_roles_may_open_the_app_and_the_owner_role_may_not(client, settings, defs):
    """T8-D2: the export mapped only System Administrator and System Customizer, so a user holding just an nst role could not open the app."""
    held = _app_role_ids(client, _app_id(client, settings))
    for name in defs.app.roles:
        assert _root_role_id(client, name) in held, name
    assert _root_role_id(client, security.OWNER_ROLE) not in held  # no user holds it
    assert {_stock_role_id(client, SYSTEM_ADMINISTRATOR_TEMPLATE), _stock_role_id(client, SYSTEM_CUSTOMIZER_TEMPLATE)} <= held  # apply removes nothing


def test_our_forms_and_views_are_the_only_defaults_of_each_table(client, defs):
    for t in defs.tables:
        forms = client.get_all("systemforms", {"$select": "name,isdefault", "$filter": f"objecttypecode eq '{t.schema}' and type eq 2"})
        assert [f["name"] for f in forms if f["isdefault"]] == [f"{t.display} Hauptformular"], t.schema
        views = client.get_all("savedqueries", {"$select": "name,isdefault", "$filter": f"returnedtypecode eq '{t.schema}' and querytype eq 0 and isdefault eq true"})
        assert len(views) == 1, t.schema


def test_apply_app_is_idempotent(client, settings, defs):
    def snapshot():
        tables = [t.schema for t in defs.tables]
        return ({t: len(client.get_all("savedqueries", {"$select": "name", "$filter": f"returnedtypecode eq '{t}'"})) for t in tables},
                {t: len(client.get_all("systemforms", {"$select": "name", "$filter": f"objecttypecode eq '{t}'"})) for t in tables},
                len(client.get_all("systemforms", {"$select": "name", "$filter": f"type eq {app.FORM_DASHBOARD}"})),
                {t: len(client.get_all("savedqueryvisualizations", {"$select": "name", "$filter": f"primaryentitytypecode eq '{t}'"})) for t in tables},
                len(client.get_all("sitemaps", {"$select": "sitemapnameunique"})),
                app.find_app_module(client, "nst_kiregister"))

    before = snapshot()
    components_before = _components(client, _app_id(client, settings))
    roles_before = _app_role_ids(client, _app_id(client, settings))
    result = app.apply_app(client, settings, defs)
    assert result["views"] == 13 and result["forms"] == 8 and result["charts"] == 3
    assert snapshot() == before
    assert _components(client, _app_id(client, settings)) == components_before
    assert _app_role_ids(client, _app_id(client, settings)) == roles_before
