from pathlib import Path

from kiregister import builders
from kiregister.definitions import load_definitions

DEFS = Path(__file__).resolve().parents[2] / "provision" / "definitions"
D = load_definitions(DEFS)
KI = next(t for t in D.tables if t.schema == "nst_kisystem")


def col(name):
    return next(c for c in KI.columns if c.schema == name)


def test_label_has_german_and_english():
    lab = builders.label("Risikoklasse")
    codes = {x["LanguageCode"]: x["Label"] for x in lab["LocalizedLabels"]}
    assert codes == {1031: "Risikoklasse", 1033: "Risikoklasse"}
    assert lab["@odata.type"] == "Microsoft.Dynamics.CRM.Label"


def test_choice_payload_values_start_at_prefix():
    c = next(c for c in D.choices if c.schema == "nst_risikoklasse")
    p = builders.choice_payload(c, option_prefix=58000)
    assert p["@odata.type"] == "Microsoft.Dynamics.CRM.OptionSetMetadata"
    assert p["Name"] == "nst_risikoklasse" and p["IsGlobal"] is True and p["OptionSetType"] == "Picklist"
    assert [o["Value"] for o in p["Options"]] == [580000000, 580000001, 580000002, 580000003, 580000004]
    assert p["Options"][2]["Label"]["LocalizedLabels"][0]["Label"] == "Hoch"


def test_table_payload_has_primary_name_and_german_names():
    p = builders.table_payload(KI)
    assert p["SchemaName"] == "nst_kisystem" and p["OwnershipType"] == "UserOwned"
    assert p["DisplayCollectionName"]["LocalizedLabels"][0]["Label"] == "KI-Systeme"
    prim = p["Attributes"][0]
    assert prim["IsPrimaryName"] is True and prim["SchemaName"] == "nst_name" and prim["MaxLength"] == 200
    assert p["IsAuditEnabled"]["Value"] is True


def test_column_payloads_by_type():
    ids = {"nst_status_kisystem": "11111111-1111-1111-1111-111111111111", "nst_datenart": "22222222-2222-2222-2222-222222222222"}
    auto = builders.column_payload(KI, col("nst_kennung"), ids)
    assert auto["AutoNumberFormat"] == "KIS-{SEQNUM:4}" and auto["@odata.type"].endswith("StringAttributeMetadata")
    memo = builders.column_payload(KI, col("nst_internebewertung"), ids)
    assert memo["@odata.type"].endswith("MemoAttributeMetadata") and memo["MaxLength"] == 4000 and memo["IsSecured"] is True
    date = builders.column_payload(KI, col("nst_naechstepruefung"), ids)
    assert date["Format"] == "DateOnly" and date["DateTimeBehavior"]["Value"] == "DateOnly"
    pick = builders.column_payload(KI, col("nst_status"), ids)
    assert pick["@odata.type"].endswith("PicklistAttributeMetadata")
    assert pick["GlobalOptionSet@odata.bind"] == "/GlobalOptionSetDefinitions(11111111-1111-1111-1111-111111111111)"
    assert pick["RequiredLevel"]["Value"] == "ApplicationRequired"
    multi = builders.column_payload(KI, col("nst_datenarten"), ids)
    assert multi["@odata.type"].endswith("MultiSelectPicklistAttributeMetadata")
    boo = builders.column_payload(KI, col("nst_transparenzpflicht"), ids)
    assert boo["OptionSet"]["TrueOption"]["Value"] == 1 and boo["OptionSet"]["FalseOption"]["Label"]["LocalizedLabels"][0]["Label"] == "Nein"
    formula = builders.column_payload(KI, col("nst_pruefungueberfaellig"), ids)
    assert formula["@odata.type"].endswith("BooleanAttributeMetadata") and "Today()" in formula["FormulaDefinition"]
    assert formula["SourceType"] == 3
    url = builders.column_payload(KI, col("nst_dokumentation"), ids)
    assert url["Format"] == "Url"


def test_relationship_payload_cascade():
    r = next(r for r in D.relationships if r.schema == "nst_kisystem_risikobewertung")
    p = builders.relationship_payload(r)
    assert p["@odata.type"] == "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata"
    assert p["ReferencedEntity"] == "nst_kisystem" and p["ReferencingEntity"] == "nst_risikobewertung"
    assert p["CascadeConfiguration"]["Delete"] == "Restrict" and p["CascadeConfiguration"]["Assign"] == "NoCascade"
    assert p["Lookup"]["SchemaName"] == "nst_KISystem" and p["Lookup"]["RequiredLevel"]["Value"] == "ApplicationRequired"


def test_fetch_and_layout_xml_for_a_view():
    v = next(v for v in D.app.views if v.name == "Prüfung überfällig")
    fetch = builders.fetch_xml(v, D)
    assert '<entity name="nst_kisystem">' in fetch
    assert '<attribute name="nst_naechstepruefung"' in fetch
    assert '<condition attribute="nst_status" operator="eq" value="580000003"' in fetch  # In Betrieb = index 3
    assert '<condition attribute="nst_naechstepruefung" operator="olderthan-x-days" value="1"' in fetch
    assert '<order attribute="nst_naechstepruefung"' in fetch
    layout = builders.layout_xml(v, D)
    assert layout.startswith('<grid name="resultset"') and 'name="nst_kennung"' in layout and 'width="' in layout


def test_form_xml_has_tabs_sections_and_subgrids():
    f = next(f for f in D.app.forms if f.table == "nst_kisystem")
    xml = builders.form_xml(f, D)
    assert xml.count("<tab ") == 4 and 'name="Verlauf"' in xml
    assert 'datafieldname="nst_internebewertung"' in xml
    assert "<TargetEntityType>nst_risikobewertung</TargetEntityType>" in xml
    assert "<RelationshipName>nst_kisystem_risikobewertung</RelationshipName>" in xml


def test_sitemap_xml_lists_areas_and_tables():
    xml = builders.sitemap_xml(D.app, D)
    assert xml.count("<Area ") == 4 and 'Entity="nst_kisystem"' in xml and "KI-Register" not in xml  # app name lives on the app module
    assert 'Url="/workplace/home_dashboards.aspx' in xml or 'DefaultDashboard' in xml


def test_chart_xml_column_and_pie():
    c = next(c for c in D.app.charts if c.kind == "column")
    data, pres = builders.chart_xml(c, D)
    assert 'attribute name="nst_risikoklasse" groupby="true" alias="groupby_col"' in data and 'alias="count"' in data
    assert 'attribute name="nst_organisation" groupby="true" alias="groupby_series"' in data
    assert "<Series>" in pres and "Column" in pres
    pie = next(c for c in D.app.charts if c.kind == "pie")
    _, pres2 = builders.chart_xml(pie, D)
    assert "Pie" in pres2


def test_default_view_and_form_for_tables_without_explicit_ones():
    rb = D.table("nst_risikobewertung")
    view = builders.default_view(rb, D)
    assert view.name == "Aktive Risikobewertungen" and len(view.columns) == 6
    assert "nst_kisystem" in view.columns
    form = builders.default_form(rb, D)
    assert form.tabs[0].sections[0][0] == "nst_kennung"
    assert "nst_kisystem" in form.tabs[0].sections[0]
