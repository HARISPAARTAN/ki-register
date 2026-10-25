"""Detail tests for FormXML, FetchXML, charts, site map and column payloads."""

import re
from pathlib import Path

from kiregister import builders
from kiregister.definitions import View, ViewFilter, load_definitions

DEFS = Path(__file__).resolve().parents[2] / "provision" / "definitions"
D = load_definitions(DEFS)
KI = D.table("nst_kisystem")
ZERO_VIEW = "<ViewId>{00000000-0000-0000-0000-000000000000}</ViewId>"


def ki_form():
    return next(f for f in D.app.forms if f.table == "nst_kisystem")


def col(name):
    return next(c for c in KI.columns if c.schema == name)


def test_subgrid_view_id_is_taken_from_view_ids():
    xml = builders.form_xml(ki_form(), D, {("nst_risikobewertung", "Aktive Risikobewertungen"): "0a1b2c3d-1111-2222-3333-444455556666"})
    assert "<ViewId>{0A1B2C3D-1111-2222-3333-444455556666}</ViewId>" in xml
    assert xml.count(ZERO_VIEW) == 1  # the Massnahmen grid was given no id
    assert builders.form_xml(ki_form(), D).count(ZERO_VIEW) == 2


def test_form_labels_are_bilingual():
    xml = builders.form_xml(ki_form(), D)
    blocks = re.findall(r"<labels>(.*?)</labels>", xml)
    assert blocks
    for block in blocks:
        assert block.count('languagecode="1031"') == 1 and block.count('languagecode="1033"') == 1, block
    assert '<label description="Verantwortlich" languagecode="1033" />' in xml


def test_daten_und_betroffene_tab_holds_datenarten_and_dokumentation():
    xml = builders.form_xml(ki_form(), D)
    tab = xml[xml.index('name="Daten und Betroffene"'):xml.index('name="Verlauf"')]
    assert 'datafieldname="nst_datenarten"' in tab and 'datafieldname="nst_dokumentation"' in tab
    assert xml.count('datafieldname="nst_datenarten"') == 1 and xml.count('datafieldname="nst_dokumentation"') == 1


def test_control_class_ids_for_int_and_formula():
    xml = builders.form_xml(builders.default_form(D.table("nst_schulung"), D), D)
    assert 'classid="{C6D124CA-7EDA-4a60-AEA9-7FB8D318B68F}" datafieldname="nst_dauerminuten" disabled="false"' in xml
    ki = builders.form_xml(ki_form(), D)
    assert 'datafieldname="nst_pruefungueberfaellig" disabled="true"' in ki
    assert 'datafieldname="nst_status" disabled="false"' in ki


def test_chart_type_is_stacked_only_with_a_series():
    stacked = next(c for c in D.app.charts if c.series)
    plain = next(c for c in D.app.charts if c.kind == "column" and not c.series)
    assert 'ChartType="StackedColumn"' in builders.chart_xml(stacked, D)[1]
    data, pres = builders.chart_xml(plain, D)
    assert 'ChartType="Column"' in pres and "Stacked" not in pres
    assert "groupby_series" not in data


def test_in_condition_has_value_children():
    v = next(v for v in D.app.views if v.name == "Aktive KI-Systeme")
    fetch = builders.fetch_xml(v, D, 58000)
    assert ('<condition attribute="nst_status" operator="in"><value>580000002</value><value>580000003</value>'
            '<value>580000004</value></condition>') in fetch


def test_fetch_xml_escapes_literal_values():
    view = View("nst_kisystem", "x", ["nst_name"], [ViewFilter("nst_name", "eq", ['A"&<B'])])
    assert 'value="A&quot;&amp;&lt;B"' in builders.fetch_xml(view, D, 58000)


def test_layout_xml_object_type_code():
    v = next(v for v in D.app.views if v.name == "Aktive KI-Systeme")
    assert 'object="0"' in builders.layout_xml(v, D)
    assert 'object="10042"' in builders.layout_xml(v, D, object_type_code=10042)


def test_sitemap_has_one_dashboard_placeholder_and_the_area_titles():
    xml = builders.sitemap_xml(D.app, D)
    assert xml.count("{00000000-0000-0000-0000-000000000000}") == 1
    assert re.findall(r'<Area Id="[^"]+" Title="([^"]+)"', xml) == ["Register", "Schulungen", "Stammdaten", "Übersicht"]


def test_unsecured_column_has_no_is_secured():
    ids = {"nst_status_kisystem": "11111111-1111-1111-1111-111111111111"}
    assert "IsSecured" not in builders.column_payload(KI, col("nst_fachbereich"), ids)
    assert "IsSecured" not in builders.column_payload(KI, col("nst_status"), ids)


def test_has_notes_follows_the_definition_and_url_email_lengths():
    assert builders.table_payload(KI)["HasNotes"] is True
    assert builders.table_payload(D.table("nst_organisation"))["HasNotes"] is False
    assert builders.column_payload(KI, col("nst_dokumentation"), {})["MaxLength"] == 500
    ma = D.table("nst_mitarbeiter")
    mail = next(c for c in ma.columns if c.schema == "nst_email")
    assert builders.column_payload(ma, mail, {})["MaxLength"] == 200
