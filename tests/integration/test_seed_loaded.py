import pytest

from kiregister import seed
from kiregister.verify import run_verify

pytestmark = pytest.mark.dataverse


def _view_rows(client, table, view_name):
    """Rows returned by the FetchXML of a saved view, executed against the entity set."""
    view = client.find_one("savedqueries", f"name eq '{view_name}' and returnedtypecode eq '{table}'", "fetchxml")
    assert view is not None, view_name
    return client.get_all(seed.entity_set(client, table), {"fetchXml": view["fetchxml"]})


def test_record_counts_are_at_least_the_csv_counts(client, settings):
    data = seed.read_seed(settings.seed_dir)
    for table, rows in data.items():
        count = int(client.get_text(f"{seed.entity_set(client, table)}/$count"))
        assert count >= len(rows), table


def test_ids_are_the_deterministic_ones(client, settings):
    data = seed.read_seed(settings.seed_dir)
    for table, rows in data.items():
        sets = seed.entity_set(client, table)
        for row in (rows[0], rows[-1]):
            found = client.get(f"{sets}({seed.record_id(table, row['key'])})", {"$select": "nst_name"})
            assert found["nst_name"] == row["nst_name"], (table, row["key"])


def test_hochrisiko_view_returns_five_high_risk_and_the_prohibited_system(client, settings):
    rows = _view_rows(client, "nst_kisystem", "Hochrisiko-Systeme")
    assert len(rows) == 6
    high = {s["nst_name"] for s in seed.read_seed(settings.seed_dir)["nst_kisystem"] if s["nst_risikoklasse"] in ("Hoch", "Unannehmbar (Art. 5)")}
    assert {r["nst_name"] for r in rows} == high and len(high) == 6


def test_pruefung_ueberfaellig_view_returns_four(client):
    rows = _view_rows(client, "nst_kisystem", "Prüfung überfällig")
    assert len(rows) == 4
    assert {r["nst_name"] for r in rows} == {"TalentFilter Bewerbungs-Screening", "Kunden-Chatbot Website", "Zählerstand-Bilderkennung", "Diktat-LLM für Arztbriefe"}


def test_overdue_formula_column_agrees_with_the_view(client):
    rows = client.get_all(seed.entity_set(client, "nst_kisystem"), {"$select": "nst_name", "$filter": "nst_pruefungueberfaellig eq true"})
    assert len(rows) == 4


def test_every_record_is_owned_by_the_team_of_its_organisation(client, defs):
    org_unit = {r["nst_organisationid"]: r["nst_businessunitname"] for r in client.get_all("nst_organisations", {"$select": "nst_businessunitname"})}
    teams = {t["teamid"]: t["_businessunitid_value"] for t in client.get_all("teams", {"$select": "teamid,_businessunitid_value"})}
    units = {u["businessunitid"]: u["name"] for u in client.get("businessunits", {"$select": "businessunitid,name"})["value"]}
    systems = client.get_all(seed.entity_set(client, "nst_kisystem"), {"$select": "nst_name,_ownerid_value,_nst_organisation_value"})
    assert len(systems) >= 20
    for s in systems:
        owner_unit = units[teams[s["_ownerid_value"]]]
        assert owner_unit == org_unit[s["_nst_organisation_value"]], s["nst_name"]


def test_every_seeded_table_is_owned_by_the_organisation_team(client, settings):
    data = seed.read_seed(settings.seed_dir)
    teams = {t["teamid"]: t["_businessunitid_value"] for t in client.get_all("teams", {"$select": "teamid,_businessunitid_value"})}
    units = {u["businessunitid"]: u["name"] for u in client.get("businessunits", {"$select": "businessunitid,name"})["value"]}
    for table, rows in data.items():
        for row in rows:
            found = client.get(f"{seed.entity_set(client, table)}({seed.record_id(table, row['key'])})", {"$select": "_ownerid_value"})
            assert units[teams[found["_ownerid_value"]]] == seed.ORG_TO_BU[row["org"]], (table, row["key"])


def test_verify_reports_nothing(client, settings, defs):
    assert run_verify(client, settings, defs) == []
