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
PROFILE = DEFS.security.column_security.profile
APP_ID = "a1"
APP_UNIQUE = "nst_kiregister"
SEED_PARAMETERS = {"skip_unit", "skip_team", "counts", "team_members", "role_holders"}
AUDIT_OFF = "Umgebungs-Auditing ist ausgeschaltet (organizations.isauditenabled)"


class Tokens:
    def token(self):
        return "t"


def metadata_id(table):
    return f"meta-{table}"


def mock_solution(skip_table=None, skip_attribute=None, skip_choice=None, skip_relationship=None, skip_role=None, skip_profile=False,
                  skip_permission=False, no_app=False, not_in_app=None, audit_off=False):
    """Everything that belongs to the solution exists: what Nordstern Test has after the managed import, plus the environment audit switch
    (an organization setting that `apply --only auditing` sets in Test; `audit_off` leaves it off).

    `not_in_app` names a table that exists but is no component of the app: the app still lists its id, but under another component
    type, which must not count. No route is registered for anything else, so a request for it fails the test as unmocked."""
    tables = [t for t in DEFS.tables if t.schema != skip_table]
    respx.get(API + "EntityDefinitions").respond(200, json={"value": [{"LogicalName": t.schema, "MetadataId": metadata_id(t.schema)} for t in tables]})
    for t in tables:
        names = [c.schema for c in t.columns] + [r.lookup.logical for r in DEFS.lookups_of(t.schema)]
        respx.get(API + f"EntityDefinitions(LogicalName='{t.schema}')/Attributes").respond(
            200, json={"value": [{"LogicalName": n} for n in names if n != skip_attribute]})
    respx.get(API + "GlobalOptionSetDefinitions").respond(200, json={"value": [{"Name": c.schema} for c in DEFS.choices if c.schema != skip_choice]})
    respx.get(API + "RelationshipDefinitions").respond(200, json={"value": [{"SchemaName": r.schema} for r in DEFS.relationships if r.schema != skip_relationship]})
    role_rows = [{"name": r.name, "roleid": f"role-{i}"} for i, r in enumerate(DEFS.security.roles) if r.name != skip_role]
    owner_copies = [{"name": OWNER_ROLE, "roleid": f"copy-{u}"} for u in range(len(UNITS))]

    def roles(request):
        rows = role_rows + owner_copies
        if request.url.params.get("$filter"):  # only the owner invariant of a full verify asks for the role by name
            rows = [r for r in rows if r["name"] == OWNER_ROLE]
        return httpx.Response(200, json={"value": rows})

    respx.get(API + "roles").mock(side_effect=roles)
    column_security = DEFS.security.column_security
    respx.get(API + "fieldsecurityprofiles").respond(200, json={"value": [] if skip_profile else [{"fieldsecurityprofileid": "profile-1"}]})
    respx.get(API + "fieldpermissions").respond(200, json={"value": [] if skip_permission else [
        {"entityname": table, "attributelogicalname": column} for table, column in column_security.columns]})
    respx.get(API + "organizations").respond(200, json={"value": [{"organizationid": "org-1", "isauditenabled": not audit_off}]})
    respx.get(API + "appmodules").respond(200, json={"value": [] if no_app else [{"appmoduleid": APP_ID}]})
    respx.get(API + "appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple()").respond(200, json={"value": []})
    if not no_app:  # without the app module there is nothing to ask for
        components = [{"componenttype": 60, "objectid": "form-1"}, {"componenttype": 26, "objectid": "view-1"}]
        components += [{"componenttype": 1, "objectid": metadata_id(t.schema)} for t in tables if t.schema != not_in_app]
        if not_in_app:
            components.append({"componenttype": 26, "objectid": metadata_id(not_in_app)})
        respx.get(API + f"RetrieveAppComponents(AppModuleId={APP_ID})").respond(200, json={"value": components})


def mock_seed(skip_table=None, skip_unit=None, skip_team=None, counts=None, team_members=0, role_holders=0):
    """What only a full environment (Nordstern Dev) has: entity sets with the seed counts, business units, owner teams and their members."""
    for t in DEFS.tables:
        if t.schema != skip_table:
            respx.get(API + f"EntityDefinitions(LogicalName='{t.schema}')").respond(200, json={"EntitySetName": t.schema + "s"})
            respx.get(API + f"{t.schema}s/$count").respond(200, text=str((counts or {}).get(t.schema, len(DATA[t.schema]))))
    for rid in [f"role-{i}" for i in range(len(DEFS.security.roles))] + [f"copy-{u}" for u in range(len(UNITS))]:
        holders = [{"systemuserid": "u1"}] * role_holders if rid == "copy-0" else []
        respx.get(API + f"roles({rid})/systemuserroles_association").respond(200, json={"value": holders})
    respx.get(API + "businessunits").respond(200, json={"value": [{"name": n} for n in UNITS if n != skip_unit]})
    teams = [{"name": owner_team_name(u), "teamid": f"team-{i}"} for i, u in enumerate(UNITS) if owner_team_name(u) != skip_team]
    respx.get(API + "teams").respond(200, json={"value": teams})
    for i in range(len(UNITS)):
        members = [{"systemuserid": "u9"}] * team_members if i == 0 else []
        respx.get(API + f"teams(team-{i})/teammembership_association").respond(200, json={"value": members})


def mock_environment(solution_only=False, **kwargs):
    """The whole environment (Nordstern Dev) with the seed counts of the CSVs unless `counts` overrides them, or with `solution_only` just
    the solution components, as in Nordstern Test after the managed import: no business units, owner teams or seed, and no route for them."""
    seed = {name: kwargs.pop(name) for name in SEED_PARAMETERS & kwargs.keys()}
    mock_solution(**kwargs)
    if not solution_only:
        mock_seed(skip_table=kwargs.get("skip_table"), **seed)


def run(**kwargs):
    return verify.run_verify(DataverseClient(API, Tokens()), SETTINGS, DEFS, **kwargs)


@respx.mock
def test_everything_in_place_gives_no_problems():
    mock_environment()
    assert run() == []


@respx.mock
def test_missing_table_is_reported_and_its_seed_check_says_the_table_is_missing_instead_of_failing():
    mock_environment(skip_table="nst_schulung")
    assert run(expect_seed=True) == ["Tabelle nst_schulung", "Seed nst_schulung: Tabelle fehlt"]


@respx.mock
def test_missing_table_without_the_seed_check():
    mock_environment(solution_only=True, skip_table="nst_schulung")
    assert run(expect_seed=False) == ["Tabelle nst_schulung"]  # not also reported as a missing app component


SOLUTION_CASES = [  # deviations in solution components: reported by a full verify and by the solution-only verify alike
    ({"skip_attribute": "nst_zweck"}, ["Spalte nst_kisystem.nst_zweck", "Spalte nst_anwendungsfall.nst_zweck"]),
    ({"skip_attribute": "nst_kisystem"}, ["Nachschlagefeld nst_risikobewertung.nst_kisystem", "Nachschlagefeld nst_massnahme.nst_kisystem",
                                          "Nachschlagefeld nst_anwendungsfall.nst_kisystem"]),
    ({"skip_choice": "nst_risikoklasse"}, ["Auswahlfeld nst_risikoklasse"]),
    ({"skip_relationship": "nst_kisystem_massnahme"}, ["Beziehung nst_kisystem_massnahme"]),
    ({"skip_role": "nst Leser"}, ["Rolle nst Leser"]),
    ({"skip_profile": True}, [f"Spaltensicherheitsprofil {PROFILE}"]),
    ({"skip_permission": True}, [f"Spaltenberechtigung {table}.{column}" for table, column in DEFS.security.column_security.columns]),
    ({"no_app": True}, ["App-Modul"]),
    ({"not_in_app": "nst_massnahme"}, [f"App-Komponente {APP_UNIQUE}: Tabelle nst_massnahme"]),
    ({"audit_off": True}, [AUDIT_OFF]),
]
SEED_CASES = [  # business units, owner teams and the seed exist only in the full environment
    ({"skip_unit": "Nordstern Energie"}, ["Unternehmenseinheit Nordstern Energie"]),
    ({"skip_team": "Nordstern Klinikum Datenbesitz"}, ["Team Nordstern Klinikum Datenbesitz"]),
    ({"counts": {"nst_kisystem": 19}}, ["Seed nst_kisystem: 19 statt mindestens 20 (kisysteme.csv)"]),
]


@pytest.mark.parametrize("solution_only", [False, True], ids=["voll", "nur-loesung"])
@pytest.mark.parametrize("kwargs, expected", SOLUTION_CASES)
@respx.mock
def test_each_kind_of_solution_deviation_is_reported_in_both_modes(solution_only, kwargs, expected):
    mock_environment(solution_only=solution_only, **kwargs)
    assert sorted(run(expect_seed=not solution_only)) == sorted(expected)


@pytest.mark.parametrize("kwargs, expected", SEED_CASES)
@respx.mock
def test_each_kind_of_seed_deviation_is_reported(kwargs, expected):
    mock_environment(**kwargs)
    assert sorted(run()) == sorted(expected)


@respx.mock
def test_solution_only_mode_asks_for_no_business_unit_owner_team_membership_or_seed_count():
    mock_environment(solution_only=True)  # a request for any of them is unmocked and fails the test
    assert run(expect_seed=False) == []


@respx.mock
def test_a_table_id_held_under_another_component_type_is_no_table_component():
    mock_environment(solution_only=True, not_in_app="nst_kisystem")  # the id is in the app, as a view (type 26)
    assert run(expect_seed=False) == [f"App-Komponente {APP_UNIQUE}: Tabelle nst_kisystem"]


@pytest.mark.parametrize("solution_only", [False, True], ids=["voll", "nur-loesung"])
@respx.mock
def test_the_app_components_are_asked_for_once_in_both_modes(solution_only):
    mock_environment(solution_only=solution_only)
    assert run(expect_seed=not solution_only) == []
    assert len([c for c in respx.calls if "RetrieveAppComponents" in str(c.request.url)]) == 1


@pytest.mark.parametrize("solution_only", [False, True], ids=["voll", "nur-loesung"])
@respx.mock
def test_the_audit_switch_is_read_once_in_both_modes_and_reported_next_to_other_deviations(solution_only):
    mock_environment(solution_only=solution_only, audit_off=True, skip_role="nst Leser")
    assert sorted(run(expect_seed=not solution_only)) == sorted(["Rolle nst Leser", AUDIT_OFF])
    assert [c.request.method for c in respx.calls if str(c.request.url).startswith(API + "organizations")] == ["GET"]


@pytest.mark.parametrize("solution_only", [False, True], ids=["voll", "nur-loesung"])
@respx.mock
def test_the_audit_switch_on_gives_no_deviation_and_verify_never_writes(solution_only):
    mock_environment(solution_only=solution_only)
    assert run(expect_seed=not solution_only) == []
    assert {c.request.method for c in respx.calls} == {"GET"}


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
