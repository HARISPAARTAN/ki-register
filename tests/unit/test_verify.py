from pathlib import Path

import respx

from kiregister import verify
from kiregister.client import DataverseClient
from kiregister.config import load_settings
from kiregister.definitions import load_definitions
from kiregister.security import owner_team_name
from kiregister.seed import read_seed

ROOT = Path(__file__).resolve().parents[2]
DEFS = load_definitions(ROOT / "provision" / "definitions")
SETTINGS = load_settings("dev", ROOT)
DATA = read_seed(ROOT / "data" / "seed")
API = "https://org.crm4.dynamics.com/api/data/v9.2/"


class Tokens:
    def token(self):
        return "t"


def mock_environment(skip_table=None, skip_attribute=None, counts=None, app=True):
    """Everything the definitions ask for exists, with the seed counts of the CSVs unless `counts` overrides them."""
    tables = [t for t in DEFS.tables if t.schema != skip_table]
    respx.get(API + "EntityDefinitions").respond(200, json={"value": [{"LogicalName": t.schema} for t in tables]})
    for t in tables:
        names = [c.schema for c in t.columns] + [r.lookup.logical for r in DEFS.lookups_of(t.schema)]
        names = [n for n in names if n != skip_attribute]
        respx.get(API + f"EntityDefinitions(LogicalName='{t.schema}')/Attributes").respond(200, json={"value": [{"LogicalName": n} for n in names]})
        respx.get(API + f"EntityDefinitions(LogicalName='{t.schema}')").respond(200, json={"EntitySetName": t.schema + "s"})
        n = (counts or {}).get(t.schema, len(DATA[t.schema]))
        respx.get(API + f"{t.schema}s/$count").respond(200, text=str(n))
    respx.get(API + "GlobalOptionSetDefinitions").respond(200, json={"value": [{"Name": c.schema} for c in DEFS.choices]})
    respx.get(API + "RelationshipDefinitions").respond(200, json={"value": [{"SchemaName": r.schema} for r in DEFS.relationships]})
    respx.get(API + "roles").respond(200, json={"value": [{"name": r.name} for r in DEFS.security.roles]})
    respx.get(API + "teams").respond(200, json={"value": [{"name": owner_team_name(b)} for b in DEFS.security.business_units]})
    respx.get(API + "businessunits").respond(200, json={"value": [{"name": n} for n in DEFS.security.business_units]})
    respx.get(API + "appmodules").respond(200, json={"value": [{"appmoduleid": "a1"}] if app else []})
    respx.get(API + "appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple()").respond(200, json={"value": []})


def run(**kwargs):
    from kiregister.seed import _entity_sets
    _entity_sets.clear()
    return verify.run_verify(DataverseClient(API, Tokens()), SETTINGS, DEFS, **kwargs)


@respx.mock
def test_everything_in_place_gives_no_problems():
    mock_environment()
    assert run() == []


@respx.mock
def test_missing_table_column_and_app_are_reported():
    mock_environment(skip_table="nst_schulung", skip_attribute="nst_zweck", app=False)
    problems = run(expect_seed=False)
    assert "Tabelle nst_schulung" in problems and "Spalte nst_kisystem.nst_zweck" in problems and "Spalte nst_anwendungsfall.nst_zweck" in problems
    assert "App-Modul" in problems


@respx.mock
def test_too_few_seed_rows_are_reported_and_expect_seed_false_skips_the_count():
    mock_environment(counts={"nst_kisystem": 19})
    problems = run()
    assert problems == ["Seed nst_kisystem: 19 statt mindestens 20 (kisysteme.csv)"]
    mock_environment(counts={"nst_kisystem": 0})
    assert run(expect_seed=False) == []


@respx.mock
def test_more_rows_than_the_csv_are_fine():
    mock_environment(counts={"nst_kisystem": 25})
    assert run() == []
