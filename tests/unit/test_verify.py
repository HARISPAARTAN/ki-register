from pathlib import Path

import httpx
import pytest
import respx

from kiregister import verify
from kiregister.client import DataverseClient
from kiregister.config import load_settings
from kiregister.definitions import load_definitions
from kiregister.security import OWNER_ROLE, owner_team_name
from kiregister.seed import read_seed

ROOT = Path(__file__).resolve().parents[2]
DEFS = load_definitions(ROOT / "provision" / "definitions")
SETTINGS = load_settings("dev", ROOT)
DATA = read_seed(ROOT / "data" / "seed")
API = "https://verify-test.crm4.dynamics.com/api/data/v9.2/"
UNITS = DEFS.security.business_units


class Tokens:
    def token(self):
        return "t"


def mock_environment(skip_table=None, skip_attribute=None, skip_choice=None, skip_relationship=None, skip_role=None, skip_unit=None,
                     skip_team=None, no_app=False, counts=None, team_members=None, role_holders=0):
    """Everything the definitions ask for exists, with the seed counts of the CSVs unless `counts` overrides them."""
    tables = [t for t in DEFS.tables if t.schema != skip_table]
    respx.get(API + "EntityDefinitions").respond(200, json={"value": [{"LogicalName": t.schema} for t in tables]})
    for t in tables:
        names = [c.schema for c in t.columns] + [r.lookup.logical for r in DEFS.lookups_of(t.schema)]
        names = [n for n in names if n != skip_attribute]
        respx.get(API + f"EntityDefinitions(LogicalName='{t.schema}')/Attributes").respond(200, json={"value": [{"LogicalName": n} for n in names]})
        respx.get(API + f"EntityDefinitions(LogicalName='{t.schema}')").respond(200, json={"EntitySetName": t.schema + "s"})
        respx.get(API + f"{t.schema}s/$count").respond(200, text=str((counts or {}).get(t.schema, len(DATA[t.schema]))))
    respx.get(API + "GlobalOptionSetDefinitions").respond(200, json={"value": [{"Name": c.schema} for c in DEFS.choices if c.schema != skip_choice]})
    respx.get(API + "RelationshipDefinitions").respond(200, json={"value": [{"SchemaName": r.schema} for r in DEFS.relationships if r.schema != skip_relationship]})
    role_rows = [{"name": r.name, "roleid": f"role-{i}"} for i, r in enumerate(DEFS.security.roles) if r.name != skip_role]
    owner_copies = [{"name": OWNER_ROLE, "roleid": f"copy-{u}"} for u in range(3)]

    def roles(request):
        wanted = request.url.params.get("$filter")
        rows = [r for r in role_rows + owner_copies if r["name"] == OWNER_ROLE] if wanted else role_rows + owner_copies
        return httpx.Response(200, json={"value": rows})

    respx.get(API + "roles").mock(side_effect=roles)
    for rid in [r["roleid"] for r in role_rows + owner_copies]:
        holders = [{"systemuserid": "u1"}] * role_holders if rid == "copy-0" else []
        respx.get(API + f"roles({rid})/systemuserroles_association").respond(200, json={"value": holders})
    respx.get(API + "businessunits").respond(200, json={"value": [{"name": n} for n in UNITS if n != skip_unit]})
    teams = [{"name": owner_team_name(u), "teamid": f"team-{i}"} for i, u in enumerate(UNITS) if owner_team_name(u) != skip_team]
    respx.get(API + "teams").respond(200, json={"value": teams})
    for i in range(len(UNITS)):
        members = [{"systemuserid": "u9"}] * (team_members or 0) if i == 0 else []
        respx.get(API + f"teams(team-{i})/teammembership_association").respond(200, json={"value": members})
    respx.get(API + "appmodules").respond(200, json={"value": [] if no_app else [{"appmoduleid": "a1"}]})
    respx.get(API + "appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple()").respond(200, json={"value": []})


def run(**kwargs):
    return verify.run_verify(DataverseClient(API, Tokens()), SETTINGS, DEFS, **kwargs)


@respx.mock
def test_everything_in_place_gives_no_problems():
    mock_environment()
    assert run() == []


@respx.mock
def test_missing_table_is_reported_once_and_not_counted_as_a_seed_problem_crash():
    mock_environment(skip_table="nst_schulung")
    assert run(expect_seed=True) == ["Tabelle nst_schulung", "Seed nst_schulung: Tabelle fehlt"]


@respx.mock
def test_missing_table_without_the_seed_check():
    mock_environment(skip_table="nst_schulung")
    assert run(expect_seed=False) == ["Tabelle nst_schulung"]


@pytest.mark.parametrize("kwargs, expected", [
    ({"skip_attribute": "nst_zweck"}, ["Spalte nst_kisystem.nst_zweck", "Spalte nst_anwendungsfall.nst_zweck"]),
    ({"skip_attribute": "nst_kisystem"}, ["Nachschlagefeld nst_risikobewertung.nst_kisystem", "Nachschlagefeld nst_massnahme.nst_kisystem",
                                          "Nachschlagefeld nst_anwendungsfall.nst_kisystem"]),
    ({"skip_choice": "nst_risikoklasse"}, ["Auswahlfeld nst_risikoklasse"]),
    ({"skip_relationship": "nst_kisystem_massnahme"}, ["Beziehung nst_kisystem_massnahme"]),
    ({"skip_role": "nst Leser"}, ["Rolle nst Leser"]),
    ({"skip_unit": "Nordstern Energie"}, ["Unternehmenseinheit Nordstern Energie"]),
    ({"skip_team": "Nordstern Klinikum Datenbesitz"}, ["Team Nordstern Klinikum Datenbesitz"]),
    ({"no_app": True}, ["App-Modul"]),
    ({"counts": {"nst_kisystem": 19}}, ["Seed nst_kisystem: 19 statt mindestens 20 (kisysteme.csv)"]),
])
@respx.mock
def test_each_kind_of_deviation_is_reported(kwargs, expected):
    mock_environment(**kwargs)
    assert sorted(run()) == sorted(expected)


@respx.mock
def test_expect_seed_false_skips_the_count():
    mock_environment(counts={"nst_kisystem": 0})
    assert run(expect_seed=False) == []


@respx.mock
def test_more_rows_than_the_csv_are_fine():
    mock_environment(counts={"nst_kisystem": 25})
    assert run() == []


@respx.mock
def test_owner_team_with_members_is_reported():
    mock_environment(team_members=2)
    assert run() == [f"Team {owner_team_name(UNITS[0])} hat 2 Mitglieder (muss leer sein)"]


@respx.mock
def test_owner_role_assigned_to_a_user_is_reported():
    mock_environment(role_holders=1)
    assert run() == [f"Rolle {OWNER_ROLE} ist 1 Benutzern zugewiesen (darf nur Teams zugewiesen sein)"]
