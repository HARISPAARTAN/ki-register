"""Views (savedqueries), forms (systemforms type 2), charts, dashboard (systemforms type 0), site map and app module."""

from __future__ import annotations

import logging

from . import builders
from .client import DataverseClient
from .config import Settings
from .definitions import Definitions
from .security import root_business_unit

log = logging.getLogger(__name__)
FORM_MAIN, FORM_DASHBOARD = 2, 0
APP_CLIENT_TYPE_UCI = 4
# AddAppComponents accepts {"@odata.type": ".entity", "entityid": <MetadataId>} but ignores the id (any GUID, also the zero GUID, gives a
# component that points at the table "entity" itself; ADR-002). The tables therefore become app components through the solution import
# (AppModuleComponent type 1 in solution/src/AppModules/nst_kiregister/AppModule.xml, imported by import-dev.yml or deploy-test.yml);
# `apply` leaves them alone, and until that import the site map is the only way they reach the app.
ADD_ENTITY_COMPONENTS = False
DEFAULT_APP_ICON = "953b9fac-1e5e-e611-80d6-00155ded156f"  # webresource of the stock app icon (required on create)


def _quote(value: str) -> str:
    """OData string literal content: single quotes are doubled."""
    return value.replace("'", "''")


def object_type_code(client: DataverseClient, table: str) -> int:
    return int(client.get(f"EntityDefinitions(LogicalName='{table}')", {"$select": "ObjectTypeCode"})["ObjectTypeCode"])


def entity_metadata_ids(client: DataverseClient, defs: Definitions, tables: list[str] | None = None) -> dict[str, str]:
    """MetadataId per table; AddAppComponents addresses a table by this id."""
    wanted = tables if tables is not None else [t.schema for t in defs.tables]
    return {t: client.get(f"EntityDefinitions(LogicalName='{t}')", {"$select": "MetadataId"})["MetadataId"] for t in wanted}


def find_app_module(client: DataverseClient, unique: str) -> str | None:
    """App module id by unique name. An app that is created but not yet published is only returned by RetrieveUnpublishedMultiple."""
    for path in ("appmodules", "appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple()"):
        rows = client.get(path, {"$select": "appmoduleid", "$filter": f"uniquename eq '{unique}'"}).get("value", [])
        if rows:
            return rows[0]["appmoduleid"]
    return None


def ensure_views(client: DataverseClient, defs: Definitions, option_prefix: int) -> dict[tuple[str, str], str]:
    ids = {}
    codes: dict[str, int] = {}
    views = list(defs.app.views)
    for t in defs.tables:
        if not any(v.table == t.schema and v.default for v in views):
            views.append(builders.default_view(t, defs))
    for v in views:
        if v.table not in codes:
            codes[v.table] = object_type_code(client, v.table)
        existing = client.find_one("savedqueries", f"name eq '{_quote(v.name)}' and returnedtypecode eq '{v.table}'", "savedqueryid")
        body = {"name": v.name, "returnedtypecode": v.table, "fetchxml": builders.fetch_xml(v, defs, option_prefix),
                "layoutxml": builders.layout_xml(v, defs, codes[v.table]), "querytype": 0, "description": v.name,
                "isdefault": v.default}
        component = f"Ansicht {v.table} / {v.name}"
        if existing:
            client.patch(f"savedqueries({existing['savedqueryid']})", body, component=component)
            ids[(v.table, v.name)] = existing["savedqueryid"]
        else:
            ids[(v.table, v.name)] = client.post_id("savedqueries", body, component=component)
            log.info("Ansicht %s / %s angelegt", v.table, v.name)
    demote_stock_default_views(client, views, ids)
    return ids


def demote_stock_default_views(client: DataverseClient, views: list, ids: dict[tuple[str, str], str]) -> None:
    """Our default view must be the only default of its table: the stock "Active ..." view is switched to non-default."""
    for v in views:
        if not v.default:
            continue
        mine = ids[(v.table, v.name)]
        rows = client.get_all("savedqueries", {"$select": "savedqueryid,name", "$filter": f"returnedtypecode eq '{v.table}' and querytype eq 0 and isdefault eq true"})
        for r in rows:
            if r["savedqueryid"] != mine:
                client.patch(f"savedqueries({r['savedqueryid']})", {"isdefault": False}, component=f"Ansicht {v.table} / {r['name']}")
                log.info("Standardansicht %s / %s abgewaehlt", v.table, r["name"])


def ensure_forms(client: DataverseClient, defs: Definitions, view_ids: dict[tuple[str, str], str]) -> dict[str, str]:
    ids = {}
    forms = list(defs.app.forms)
    for t in defs.tables:
        if not any(f.table == t.schema for f in forms):
            forms.append(builders.default_form(t, defs))
    for f in forms:
        existing = client.find_one("systemforms", f"name eq '{_quote(f.name)}' and objecttypecode eq '{f.table}' and type eq {FORM_MAIN}", "formid")
        xml = builders.form_xml(f, defs, view_ids)
        component = f"Formular {f.name}"
        if existing:
            client.patch(f"systemforms({existing['formid']})", {"formxml": xml, "isdefault": True}, component=component)
            ids[f.table] = existing["formid"]
        else:
            body = {"name": f.name, "objecttypecode": f.table, "type": FORM_MAIN, "formxml": xml, "description": f.name, "isdefault": True}
            ids[f.table] = client.post_id("systemforms", body, component=component)
            log.info("Formular %s angelegt", f.name)
    return ids


def ensure_charts(client: DataverseClient, defs: Definitions) -> dict[tuple[str, str], str]:
    ids = {}
    for c in defs.app.charts:
        existing = client.find_one("savedqueryvisualizations", f"name eq '{_quote(c.name)}' and primaryentitytypecode eq '{c.table}'",
                                   "savedqueryvisualizationid")
        data, pres = builders.chart_xml(c, defs)
        body = {"name": c.name, "primaryentitytypecode": c.table, "datadescription": data, "presentationdescription": pres, "description": c.name}
        component = f"Diagramm {c.name}"
        if existing:
            client.patch(f"savedqueryvisualizations({existing['savedqueryvisualizationid']})", body, component=component)
            ids[(c.table, c.name)] = existing["savedqueryvisualizationid"]
        else:
            ids[(c.table, c.name)] = client.post_id("savedqueryvisualizations", body, component=component)
            log.info("Diagramm %s angelegt", c.name)
    return ids


def dashboard_formxml(dashboard, view_ids: dict, chart_ids: dict, defs: Definitions) -> str:
    """Dashboard FormXML: one sub-grid control per component (chart or list), laid out in two columns."""
    cells = []
    for i, comp in enumerate(dashboard.components):
        view = view_ids[(comp.table, comp.view or comp.list)]
        base = (f"<ViewId>{{{view}}}</ViewId><IsUserView>false</IsUserView><RelationshipName /><TargetEntityType>{comp.table}</TargetEntityType>"
                f"<AutoExpand>Fixed</AutoExpand><EnableQuickFind>false</EnableQuickFind><EnableViewPicker>false</EnableViewPicker>")
        if comp.chart:
            chart = chart_ids[(comp.table, comp.chart)]
            params = (f"{base}<VisualizationId>{{{chart}}}</VisualizationId><IsUserChart>false</IsUserChart><EnableChartPicker>false</EnableChartPicker>"
                      f"<ChartGridMode>Chart</ChartGridMode>")
            title = comp.chart
        else:
            params = f"{base}<RecordsPerPage>10</RecordsPerPage>"
            title = comp.list
        cells.append(f'<cell id="{builders._guid("dashcell", dashboard.name, i)}" showlabel="true" rowspan="12" colspan="1"><labels><label description="{builders._attr(title)}" languagecode="1031" />'
                     f'<label description="{builders._attr(title)}" languagecode="1033" /></labels>'
                     f'<control id="comp_{i}" classid="{{E7A81278-8635-4d9e-8D4D-59480B391C5B}}"><parameters>{params}</parameters></control></cell>')
    rows = "".join(f"<row>{cells[i]}{cells[i + 1] if i + 1 < len(cells) else ''}</row>" for i in range(0, len(cells), 2))
    name = builders._attr(dashboard.name)
    return (f'<form><tabs><tab name="dash" verticallayout="true" id="{builders._guid("dashtab", dashboard.name)}"><labels><label description="{name}" languagecode="1031" />'
            f'<label description="{name}" languagecode="1033" /></labels>'
            f'<columns><column width="100%"><sections><section name="s1" showlabel="false" columns="11" id="{builders._guid("dashsec", dashboard.name)}"><labels><label description="" languagecode="1031" />'
            f'<label description="" languagecode="1033" /></labels>'
            f'<rows>{rows}</rows></section></sections></column></columns></tab></tabs></form>')


def ensure_dashboard(client: DataverseClient, defs: Definitions, view_ids: dict, chart_ids: dict) -> str:
    d = defs.app.dashboard
    existing = client.find_one("systemforms", f"name eq '{_quote(d.name)}' and type eq {FORM_DASHBOARD}", "formid")
    xml = dashboard_formxml(d, view_ids, chart_ids, defs)
    component = f"Dashboard {d.name}"
    if existing:
        client.patch(f"systemforms({existing['formid']})", {"formxml": xml}, component=component)
        return existing["formid"]
    dash_id = client.post_id("systemforms", {"name": d.name, "type": FORM_DASHBOARD, "formxml": xml, "description": d.name, "isdefault": False},
                             component=component)
    log.info("Dashboard %s angelegt", d.name)
    return dash_id


def app_components(defs: Definitions, form_ids: dict, view_ids: dict, chart_ids: dict, dashboard_id: str,
                   entity_ids: dict[str, str] | None = None) -> list[dict]:
    """AddAppComponents list: forms, views, charts and the dashboard, plus every table of every area when `entity_ids` is given."""
    comps = []
    if entity_ids is not None:
        for area in defs.app.areas:
            for t in area.tables:
                comps.append({"@odata.type": "Microsoft.Dynamics.CRM.entity", "entityid": entity_ids[t]})
    comps += [{"@odata.type": "Microsoft.Dynamics.CRM.systemform", "formid": fid} for fid in form_ids.values()]
    comps += [{"@odata.type": "Microsoft.Dynamics.CRM.savedquery", "savedqueryid": vid} for vid in view_ids.values()]
    comps += [{"@odata.type": "Microsoft.Dynamics.CRM.savedqueryvisualization", "savedqueryvisualizationid": cid} for cid in chart_ids.values()]
    comps.append({"@odata.type": "Microsoft.Dynamics.CRM.systemform", "formid": dashboard_id})
    return comps


def app_unique_name(settings: Settings, defs: Definitions) -> str:
    """Unique name of the app module: the prefix is added once."""
    return f"{settings.prefix}_{defs.app.unique_name.removeprefix(settings.prefix + '_')}"


def ensure_app_roles(client: DataverseClient, app_id: str, role_names: list[str]) -> list[str]:
    """Let the named security roles open the app (N:N relationship appmoduleroles_association); returns the names that were added.

    Without it only System Administrator and System Customizer can open the app, so a user who holds just an nst role cannot (the
    exported AppModule.xml lists no other role). The role of the root business unit is associated, as for the two stock roles; the copies
    in the child units follow their root role. Reads first and adds what is missing; it never removes an association."""
    root, _ = root_business_unit(client)
    held = {r["roleid"] for r in client.get_all(f"appmodules({app_id})/appmoduleroles_association", {"$select": "roleid"})}
    added = []
    for name in role_names:
        role = client.find_one("roles", f"name eq '{_quote(name)}' and _businessunitid_value eq {root}", "roleid")
        if not role:
            raise RuntimeError(f"Rolle {name} fehlt in der Wurzel-Unternehmenseinheit (zuerst `kiregister apply --only security` ausfuehren)")
        if role["roleid"] in held:
            continue
        client.post(f"appmodules({app_id})/appmoduleroles_association/$ref", {"@odata.id": f"{client.api_url}roles({role['roleid']})"}, solution=False,
                    component=f"Rolle {name} fuer die App")
        log.info("Rolle %s darf die App oeffnen", name)
        added.append(name)
    return added


def ensure_app_module(client: DataverseClient, settings: Settings, defs: Definitions, dashboard_id: str, form_ids: dict, view_ids: dict,
                      chart_ids: dict) -> str:
    a = defs.app
    unique = app_unique_name(settings, defs)
    app_id = find_app_module(client, unique)
    if not app_id:
        app_id = client.post_id("appmodules", {"name": a.display, "uniquename": unique, "description": a.description, "clienttype": APP_CLIENT_TYPE_UCI,
                                                 "webresourceid": DEFAULT_APP_ICON},
                                component=f"App {a.display}")
        log.info("App %s angelegt", a.display)
    sitemap_xml = builders.sitemap_xml(a, defs).replace(builders.ZERO_GUID, "{" + dashboard_id + "}")
    sm = client.find_one("sitemaps", f"sitemapnameunique eq '{unique}_sitemap'", "sitemapid")
    if sm:
        client.patch(f"sitemaps({sm['sitemapid']})", {"sitemapxml": sitemap_xml}, component="Sitemap")
        sm_id = sm["sitemapid"]
    else:
        sm_id = client.post_id("sitemaps", {"sitemapname": f"{a.display} Sitemap", "sitemapnameunique": f"{unique}_sitemap", "sitemapxml": sitemap_xml},
                               component="Sitemap")
    entity_ids = entity_metadata_ids(client, defs, [t for area in a.areas for t in area.tables]) if ADD_ENTITY_COMPONENTS else None
    comps = app_components(defs, form_ids, view_ids, chart_ids, dashboard_id, entity_ids)
    client.action("AddAppComponents", {"AppId": app_id, "Components": [{"@odata.type": "Microsoft.Dynamics.CRM.sitemap", "sitemapid": sm_id}, *comps]})
    client.action("PublishXml", {"ParameterXml": f"<importexportxml><appmodules><appmodule>{app_id}</appmodule></appmodules></importexportxml>"}, solution=False)
    ensure_app_roles(client, app_id, a.roles)  # after the publish: a new app is only readable once published
    problems = validate_app(client, app_id)
    if problems:
        log.warning("ValidateApp meldet %d Fehler: %s", len(problems), problems[:3])
    return app_id


def validation_issues(client: DataverseClient, app_id: str) -> list[dict]:
    """Every issue reported by the ValidateApp function, warnings included."""
    result = client.get(f"ValidateApp(AppModuleId={app_id})")
    return result.get("AppValidationResponse", {}).get("ValidationIssueList", [])


def validate_app(client: DataverseClient, app_id: str) -> list[dict]:
    """Issues of type Error reported by the ValidateApp function (warnings are ignored)."""
    return [v for v in validation_issues(client, app_id) if v.get("ErrorType") == "Error"]


def apply_app(client: DataverseClient, settings: Settings, defs: Definitions) -> dict:
    view_ids = ensure_views(client, defs, settings.option_prefix)
    form_ids = ensure_forms(client, defs, view_ids)
    chart_ids = ensure_charts(client, defs)
    client.action("PublishAllXml", solution=False)
    dash_id = ensure_dashboard(client, defs, view_ids, chart_ids)
    app_id = ensure_app_module(client, settings, defs, dash_id, form_ids, view_ids, chart_ids)
    client.action("PublishAllXml", solution=False)
    return {"views": len(view_ids), "forms": len(form_ids), "charts": len(chart_ids), "dashboard": dash_id, "app": app_id}
