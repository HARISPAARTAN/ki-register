import pytest

from kiregister import app

pytestmark = pytest.mark.dataverse


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
    result = app.apply_app(client, settings, defs)
    assert result["views"] == 13 and result["forms"] == 8 and result["charts"] == 3
    assert snapshot() == before
