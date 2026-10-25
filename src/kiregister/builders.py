"""Dataclasses to Dataverse Web API payloads and to FormXML, FetchXML, LayoutXML, chart and site-map XML."""

from __future__ import annotations

import uuid
from xml.sax.saxutils import escape

from .definitions import AppDef, Chart, Choice, Column, Definitions, Form, Relationship, Subgrid, Tab, Table, View

ODATA = "Microsoft.Dynamics.CRM."
LCID_DE, LCID_EN = 1031, 1033
ZERO_GUID = "{00000000-0000-0000-0000-000000000000}"


def _attr(text: str) -> str:
    """Escape text for use inside a double-quoted XML attribute."""
    return escape(text, {'"': "&quot;"})


def _guid(*parts: object) -> str:
    """Deterministic GUID in braces, so re-provisioning produces identical form XML."""
    return "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "kiregister:" + ":".join(str(p) for p in parts))).upper() + "}"


def _labels(de: str, en: str | None = None) -> str:
    """FormXML <labels> with a German (1031) and an English (1033) label; same text when no English is given."""
    return (f'<labels><label description="{_attr(de)}" languagecode="{LCID_DE}" />'
            f'<label description="{_attr(en or de)}" languagecode="{LCID_EN}" /></labels>')


def label(de: str, en: str | None = None) -> dict:
    return {"@odata.type": ODATA + "Label", "LocalizedLabels": [
        {"@odata.type": ODATA + "LocalizedLabel", "Label": de, "LanguageCode": LCID_DE},
        {"@odata.type": ODATA + "LocalizedLabel", "Label": en or de, "LanguageCode": LCID_EN}]}


def _required(flag: bool) -> dict:
    return {"Value": "ApplicationRequired" if flag else "None", "CanBeChanged": True, "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings"}


def _managed_bool(value: bool, name: str) -> dict:
    return {"Value": value, "CanBeChanged": True, "ManagedPropertyLogicalName": name}


def choice_payload(choice: Choice, option_prefix: int) -> dict:
    base = option_prefix * 10000
    return {"@odata.type": ODATA + "OptionSetMetadata", "Name": choice.schema, "DisplayName": label(choice.display),
            "Description": label(choice.display), "IsGlobal": True, "OptionSetType": "Picklist",
            "Options": [{"Value": base + i, "Label": label(v)} for i, v in enumerate(choice.values)]}


def table_payload(table: Table) -> dict:
    primary = {"@odata.type": ODATA + "StringAttributeMetadata", "SchemaName": table.primary.schema, "IsPrimaryName": True,
               "RequiredLevel": _required(True), "MaxLength": table.primary.length, "FormatName": {"Value": "Text"},
               "DisplayName": label(table.primary.display)}
    return {"@odata.type": ODATA + "EntityMetadata", "SchemaName": table.schema, "DisplayName": label(table.display, table.display_en),
            "DisplayCollectionName": label(table.plural, table.plural_en), "Description": label(table.display),
            "OwnershipType": "UserOwned", "HasActivities": False, "HasNotes": table.notes,
            "IsAuditEnabled": _managed_bool(table.audit, "canmodifyauditsettings"), "Attributes": [primary]}


def choice_value(defs: Definitions, choice_schema: str, value_label: str, option_prefix: int) -> int:
    values = defs.choice(choice_schema).values
    return option_prefix * 10000 + values.index(value_label)


def column_payload(table: Table, col: Column, choice_ids: dict[str, str]) -> dict:
    common = {"SchemaName": col.schema, "DisplayName": label(col.display, col.display_en), "Description": label(col.display),
              "RequiredLevel": _required(col.required)}
    if col.secured:
        common["IsSecured"] = True
    t = col.type
    if t in ("string", "autonumber", "url", "email"):
        p = {"@odata.type": ODATA + "StringAttributeMetadata", "MaxLength": col.length if t == "string" else {"autonumber": 100, "url": 500, "email": 200}[t],
             "FormatName": {"Value": {"string": "Text", "autonumber": "Text", "url": "Url", "email": "Email"}[t]}, **common}
        if t == "url":
            p["Format"] = "Url"
        if t == "email":
            p["Format"] = "Email"
        if t == "autonumber":
            p["AutoNumberFormat"] = col.format
        return p
    if t == "memo":
        return {"@odata.type": ODATA + "MemoAttributeMetadata", "MaxLength": col.length, "Format": "TextArea", **common}
    if t == "int":
        return {"@odata.type": ODATA + "IntegerAttributeMetadata", "Format": "None", "MinValue": 0, "MaxValue": 1000000, **common}
    if t in ("date", "datetime"):
        return {"@odata.type": ODATA + "DateTimeAttributeMetadata", "Format": "DateOnly" if t == "date" else "DateAndTime",
                "DateTimeBehavior": {"Value": "DateOnly" if t == "date" else "UserLocal"}, **common}
    if t == "bool" or (t == "formula" and col.result == "bool"):
        p = {"@odata.type": ODATA + "BooleanAttributeMetadata", "DefaultValue": False,
             "OptionSet": {"@odata.type": ODATA + "BooleanOptionSetMetadata",
                           "TrueOption": {"Value": 1, "Label": label("Ja", "Yes")}, "FalseOption": {"Value": 0, "Label": label("Nein", "No")}}, **common}
        if t == "formula":
            p["FormulaDefinition"] = col.formula
            p["SourceType"] = 3
        return p
    if t in ("choice", "multichoice"):
        kind = "PicklistAttributeMetadata" if t == "choice" else "MultiSelectPicklistAttributeMetadata"
        return {"@odata.type": ODATA + kind, "GlobalOptionSet@odata.bind": f"/GlobalOptionSetDefinitions({choice_ids[col.choice]})", **common}
    raise ValueError(f"Spaltentyp {t} nicht unterstuetzt")


def relationship_payload(rel: Relationship) -> dict:
    """One-to-many relationship; the associated-menu label is omitted (UseCollectionName) because a 1031 label is rejected in an English-base environment; Lookup.SchemaName is the Pascal-cased schema name (Dataverse derives the lower-case logical name)."""
    return {"@odata.type": ODATA + "OneToManyRelationshipMetadata", "SchemaName": rel.schema,
            "ReferencedEntity": rel.referenced, "ReferencingEntity": rel.referencing,
            "CascadeConfiguration": {"Assign": "NoCascade", "Delete": rel.delete, "Merge": "NoCascade", "Reparent": "NoCascade",
                                     "Share": "NoCascade", "Unshare": "NoCascade"},
            "AssociatedMenuConfiguration": {"Behavior": "UseCollectionName", "Group": "Details", "Order": 10000},
            "Lookup": {"@odata.type": ODATA + "LookupAttributeMetadata", "SchemaName": rel.lookup.schema,
                       "DisplayName": label(rel.lookup.display), "Description": label(rel.lookup.display),
                       "RequiredLevel": _required(rel.lookup.required)}}


def _choice_of_column(defs: Definitions, table: str, column: str) -> str | None:
    t = defs.table(table)
    col = next((c for c in t.columns if c.schema == column), None)
    return col.choice if col and col.type in ("choice", "multichoice") else None


def fetch_xml(view: View, defs: Definitions, option_prefix: int) -> str:
    t = defs.table(view.table)
    id_attr = f"{t.schema}id"
    attrs = "".join(f'<attribute name="{c}" />' for c in dict.fromkeys([id_attr, *view.columns]))
    conds = []
    for f in view.filter:
        choice = _choice_of_column(defs, view.table, f.column)
        vals = [str(choice_value(defs, choice, v, option_prefix)) if choice else v for v in f.values]
        if f.op == "in":
            conds.append(f'<condition attribute="{f.column}" operator="in">' + "".join(f"<value>{escape(v)}</value>" for v in vals) + "</condition>")
        else:
            conds.append(f'<condition attribute="{f.column}" operator="{f.op}" value="{_attr(vals[0])}" />')
    filt = f'<filter type="and">{"".join(conds)}</filter>' if conds else ""
    order = "".join(f'<order attribute="{o}" descending="false" />' for o in view.order)
    return f'<fetch version="1.0" output-format="xml-platform" mapping="logical" distinct="false"><entity name="{t.schema}">{attrs}{filt}{order}</entity></fetch>'


def layout_xml(view: View, defs: Definitions, object_type_code: int = 0) -> str:
    t = defs.table(view.table)
    cells = "".join(f'<cell name="{c}" width="{200 if i == 1 else 125}" />' for i, c in enumerate(view.columns))
    return (f'<grid name="resultset" object="{object_type_code}" jump="{t.primary.schema}" select="1" icon="1" preview="1">'
            f'<row name="result" id="{t.schema}id">{cells}</row></grid>')


def _control(column: str, defs: Definitions, table: str, idx: str) -> str:
    t = defs.table(table)
    lookups = {r.lookup.logical for r in defs.lookups_of(table)}
    col = next((c for c in t.columns if c.schema == column), None)
    if column in lookups:
        classid = "{270BD3DB-D9AF-4782-9025-509E298DEC0A}"
        text, text_en = next(r.lookup.display for r in defs.lookups_of(table) if r.lookup.logical == column), None
    else:
        text = col.display if col else t.primary.display if column == t.primary.schema else column
        text_en = col.display_en if col else None
        if col and col.type == "memo":
            classid = "{E0DECE4B-6FC8-4a8f-A065-082708572369}"
        elif col and col.type == "choice":
            classid = "{3EF39988-22BB-4f0b-BBBE-64B5A3748AEE}"
        elif col and col.type == "multichoice":
            classid = "{4AA28AB7-9C13-4F57-A73D-AD894D048B5F}"
        elif col and col.type in ("bool", "formula"):
            classid = "{B0C6723A-8503-4fd7-BB28-C8A06AC933C2}"
        elif col and col.type in ("date", "datetime"):
            classid = "{5B773807-9FB2-42db-97C3-7A91EFF8ADFF}"
        elif col and col.type == "int":
            classid = "{C6D124CA-7EDA-4a60-AEA9-7FB8D318B68F}"
        else:
            classid = "{4273EDBD-AC1D-40d3-9FB2-095C621B552D}"
    rows = ' rowspan="4"' if col and col.type == "memo" else ""
    disabled = "true" if col and col.type == "formula" else "false"
    return (f'<row><cell id="{_guid("cell", table, idx)}"{rows}>{_labels(text, text_en)}'
            f'<control id="{column}" classid="{classid}" datafieldname="{column}" disabled="{disabled}" /></cell></row>')


def _braced(guid: str) -> str:
    return "{" + guid.strip("{}").upper() + "}"


def _subgrid_section(g: Subgrid, ti: int, gi: int, defs: Definitions, view_ids: dict[tuple[str, str], str] | None) -> str:
    rel = defs.relationship_for(g.table, g.lookup)
    target = defs.table(g.table)
    if view_ids is not None and (g.table, g.view) not in view_ids:
        raise KeyError(f"Ansicht {g.view!r} fuer {g.table!r} (Unterliste) fehlt in view_ids")
    view_id = _braced(view_ids[(g.table, g.view)]) if view_ids is not None else None
    view_xml = f"<ViewId>{view_id or ZERO_GUID}</ViewId>" + (f"<ViewIds>{view_id}</ViewIds>" if view_id else "<ViewIds />")
    grid = (f'<row><cell id="{_guid("grid", ti, gi, g.table)}" rowspan="8" showlabel="true">{_labels(target.plural, target.plural_en)}'
            f'<control id="grid_{g.table}_{ti}_{gi}" classid="{{E7A81278-8635-4d9e-8D4D-59480B391C5B}}"><parameters>'
            f'{view_xml}<TargetEntityType>{g.table}</TargetEntityType>'
            f'<RelationshipName>{rel.schema}</RelationshipName><EnableViewPicker>false</EnableViewPicker><IsUserView>false</IsUserView>'
            f'<AutoExpand>Fixed</AutoExpand><RecordsPerPage>10</RecordsPerPage></parameters></control></cell></row>')
    return (f'<section name="grid_{ti}_{gi}" showlabel="true" showbar="false" columns="1" id="{_guid("gsec", ti, gi, g.table)}">'
            f'{_labels(target.plural, target.plural_en)}<rows>{grid}</rows></section>')


def form_xml(form: Form, defs: Definitions, view_ids: dict[tuple[str, str], str] | None = None) -> str:
    """FormXML. `view_ids` maps (sub-grid table, view name) to the saved query id; without it the zero GUID is emitted."""
    tabs = []
    for ti, tab in enumerate(form.tabs):
        sections = []
        for si, cols in enumerate(tab.sections):
            rows = "".join(_control(c, defs, form.table, f"{ti}-{si}-{ci}") for ci, c in enumerate(cols))
            sections.append(f'<section name="sec_{ti}_{si}" showlabel="false" showbar="false" columns="1" id="{_guid("sec", form.table, ti, si)}">'
                            f'{_labels(tab.name)}<rows>{rows}</rows></section>')
        for gi, g in enumerate(tab.subgrids):
            sections.append(_subgrid_section(g, ti, gi, defs, view_ids))
        tabs.append(f'<tab name="{_attr(tab.name)}" verticallayout="true" id="{_guid("tab", form.table, ti)}" expanded="true" showlabel="true">'
                    f'{_labels(tab.name)}<columns><column width="100%"><sections>{"".join(sections)}</sections></column></columns></tab>')
    return f'<form><tabs>{"".join(tabs)}</tabs></form>'


def default_form(table: Table, defs: Definitions) -> Form:
    lookups = [r.lookup.logical for r in defs.lookups_of(table.schema)]
    keys = [c.schema for c in table.columns if c.type == "autonumber"] + [table.primary.schema] + lookups
    rest = [c.schema for c in table.columns if c.schema not in keys and c.type != "autonumber"]
    return Form(table.schema, f"{table.display} Hauptformular", [Tab("Allgemein", [keys, rest])])


def default_view(table: Table, defs: Definitions) -> View:
    lookups = [r.lookup.logical for r in defs.lookups_of(table.schema)]
    auto = [c.schema for c in table.columns if c.type == "autonumber"]
    others = [c.schema for c in table.columns if c.type not in ("autonumber", "memo", "formula")]
    cols = list(dict.fromkeys([*auto, table.primary.schema, *lookups, *others]))[:6]
    return View(table.schema, f"Aktive {table.plural}", cols, [], [table.primary.schema], True)


def chart_xml(chart: Chart, defs: Definitions) -> tuple[str, str]:
    """Return (data definition XML, presentation XML) for a count-by-group chart, optionally stacked by a second group."""
    t = defs.table(chart.table)
    series_attr = f'<attribute name="{chart.series}" groupby="true" alias="groupby_series" />' if chart.series else ""
    series_cat = ""
    data = (f'<datadefinition><fetchcollection><fetch mapping="logical" aggregate="true"><entity name="{t.schema}">'
            f'<attribute name="{t.schema}id" alias="count" aggregate="count" />'
            f'<attribute name="{chart.groupby}" groupby="true" alias="groupby_col" />{series_attr}'
            f'</entity></fetch></fetchcollection><categorycollection>'
            f'<category alias="groupby_col"><measurecollection><measure alias="count" /></measurecollection></category>{series_cat}'
            f'</categorycollection></datadefinition>')
    kind = {"column": "StackedColumn" if chart.series else "Column", "pie": "Pie", "bar": "StackedBar" if chart.series else "Bar"}[chart.kind]
    legend = "True" if chart.series or chart.kind == "pie" else "False"
    pres = (f'<Chart Palette="BrightPastel"><Series><Series ChartType="{kind}" IsValueShownAsLabel="True" /></Series>'
            f'<ChartAreas><ChartArea><AxisY LabelAutoFitMinFontSize="8"><MajorGrid LineColor="246, 246, 246" /></AxisY><AxisX LabelAutoFitMinFontSize="8" /></ChartArea></ChartAreas>'
            f'<Titles><Title Text="{_attr(chart.name)}" Alignment="TopLeft" /></Titles><Legends><Legend Enabled="{legend}" /></Legends></Chart>')
    return data, pres


def sitemap_xml(app: AppDef, defs: Definitions) -> str:
    """Site map. The dashboard sub-area carries the zero GUID in DefaultDashboard; app provisioning replaces it with the real dashboard id."""
    areas = []
    for a in app.areas:
        subs = []
        if a.dashboard:
            subs.append(f'<SubArea Id="sub_{a.id}_dash" DefaultDashboard="{ZERO_GUID}" Url="/workplace/home_dashboards.aspx" Title="{_attr(a.title)}" />')
        for t in a.tables:
            subs.append(f'<SubArea Id="sub_{t}" Entity="{t}" Title="{_attr(defs.table(t).plural)}" />')
        areas.append(f'<Area Id="area_{a.id}" Title="{_attr(a.title)}" ShowGroups="true"><Group Id="grp_{a.id}" Title="{_attr(a.title)}">{"".join(subs)}</Group></Area>')
    return f'<SiteMap IntroducedVersion="7.0.0.0">{"".join(areas)}</SiteMap>'
