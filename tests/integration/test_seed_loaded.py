from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from kiregister import seed
from kiregister.security import OWNER_ROLE, owner_team_name
from kiregister.verify import run_verify

pytestmark = pytest.mark.dataverse


def _view_rows(client, table, view_name):
    """Rows returned by the FetchXML of a saved view, executed against the entity set."""
    view = client.find_one("savedqueries", f"name eq '{view_name}' and returnedtypecode eq '{table}'", "fetchxml")
    assert view is not None, view_name
    return client.get_all(seed.entity_set(client, table), {"fetchXml": view["fetchxml"]})


def _owner_units(client):
    teams = {t["teamid"]: t for t in client.get_all("teams", {"$select": "teamid,name,_businessunitid_value"})}
    units = {u["businessunitid"]: u["name"] for u in client.get("businessunits", {"$select": "businessunitid,name"})["value"]}
    return teams, units


def test_record_counts_are_at_least_the_csv_counts(client, settings):
    data = seed.read_seed(settings.seed_dir)
    for table, rows in data.items():
        count = int(client.get_text(f"{seed.entity_set(client, table)}/$count"))
        assert count >= len(rows), table


def test_record_counts_per_subsidiary(client, settings):
    data = seed.read_seed(settings.seed_dir)
    org_by_id = {seed.record_id("nst_organisation", o["key"]): o["key"] for o in data["nst_organisation"]}
    for table, id_col in (("nst_kisystem", "nst_kisystemid"), ("nst_mitarbeiter", "nst_mitarbeiterid")):
        seeded = {seed.record_id(table, r["key"]) for r in data[table]}
        rows = client.get_all(seed.entity_set(client, table), {"$select": f"{id_col},_nst_organisation_value"})
        per_unit = Counter(org_by_id[r["_nst_organisation_value"]] for r in rows if r[id_col] in seeded)
        assert per_unit == Counter(r["org"] for r in data[table]), table


def test_hochrisiko_view_returns_the_five_systems_of_tier_hoch(client, settings):
    rows = _view_rows(client, "nst_kisystem", "Hochrisiko-Systeme")
    high = {s["nst_name"] for s in seed.read_seed(settings.seed_dir)["nst_kisystem"] if s["nst_risikoklasse"] == "Hoch"}
    assert len(rows) == 5 and {r["nst_name"] for r in rows} == high


def test_overdue_view_and_formula_column_agree_with_the_overdue_set_computed_from_the_data(client, settings, defs):
    in_operation = settings.option_prefix * 10000 + defs.choice("nst_status_kisystem").values.index("In Betrieb")
    today = datetime.now(UTC).date()
    systems = client.get_all(seed.entity_set(client, "nst_kisystem"), {"$select": "nst_name,nst_status,nst_naechstepruefung"})
    reviewed = [(s["nst_name"], s["nst_naechstepruefung"]) for s in systems if s["nst_status"] == in_operation and s["nst_naechstepruefung"]]
    # "olderthan-x-days 1" (view) and "< UTCToday()" (formula) differ only for a review dated yesterday
    strict = {n for n, d in reviewed if d < (today - timedelta(days=1)).isoformat()}
    loose = {n for n, d in reviewed if d < today.isoformat()}
    view = {r["nst_name"] for r in _view_rows(client, "nst_kisystem", "Prüfung überfällig")}
    formula = {s["nst_name"] for s in client.get_all(seed.entity_set(client, "nst_kisystem"), {"$select": "nst_name", "$filter": "nst_pruefungueberfaellig eq true"})}
    assert formula == loose and strict <= view <= loose
    assert view  # spec 11: Prüfung überfällig > 0


def test_every_seeded_row_exists_under_its_deterministic_id_and_belongs_to_the_owner_team_of_its_subsidiary(client, settings):
    data = seed.read_seed(settings.seed_dir)
    teams, units = _owner_units(client)
    unit_of = {r["key"]: r["nst_businessunitname"] for r in data["nst_organisation"]}
    for table, rows in data.items():
        id_col = f"{table}id"
        owners = {r[id_col]: r["_ownerid_value"] for r in client.get_all(seed.entity_set(client, table), {"$select": f"{id_col},_ownerid_value"})}
        for row in rows:
            owner = teams[owners[seed.record_id(table, row["key"])]]
            assert owner["name"] == owner_team_name(unit_of[row["org"]]), (table, row["key"])
            assert units[owner["_businessunitid_value"]] == unit_of[row["org"]], (table, row["key"])


def test_kisystem_owner_team_matches_the_business_unit_of_the_organisation_row(client):
    teams, units = _owner_units(client)
    org_unit = {r["nst_organisationid"]: r["nst_businessunitname"] for r in client.get_all("nst_organisations", {"$select": "nst_businessunitname"})}
    systems = client.get_all(seed.entity_set(client, "nst_kisystem"), {"$select": "nst_name,_ownerid_value,_nst_organisation_value"})
    assert len(systems) >= 20
    for s in systems:
        assert units[teams[s["_ownerid_value"]]["_businessunitid_value"]] == org_unit[s["_nst_organisation_value"]], s["nst_name"]


def test_owner_teams_have_no_members_and_the_owner_role_is_assigned_to_no_user(client, defs):
    teams, _ = _owner_units(client)
    by_name = {t["name"]: t["teamid"] for t in teams.values()}
    for unit in defs.security.business_units:
        members = client.get_all(f"teams({by_name[owner_team_name(unit)]})/teammembership_association", {"$select": "systemuserid"})
        assert members == [], unit
    roles = client.get_all("roles", {"$select": "roleid", "$filter": f"name eq '{OWNER_ROLE}'"})
    assert len(roles) == 1 + len(defs.security.business_units)  # root role and the copy in every unit
    for role in roles:
        assert client.get_all(f"roles({role['roleid']})/systemuserroles_association", {"$select": "systemuserid"}) == []


def test_verify_reports_nothing(client, settings, defs):
    assert run_verify(client, settings, defs) == []
