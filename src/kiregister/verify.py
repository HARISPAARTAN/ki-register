"""Verification used by `kiregister verify`, the integration tests and the deploy workflow."""

from __future__ import annotations

from .app import find_app_module
from .client import DataverseClient
from .config import Settings
from .definitions import Definitions
from .security import owner_team_name
from .seed import FILES, ORDER, entity_set, read_seed


def run_verify(client: DataverseClient, settings: Settings, defs: Definitions, expect_seed: bool = True) -> list[str]:
    """Human-readable deviations from the definitions (and the seed CSVs); an empty list means everything matches."""
    problems = []
    entities = {e["LogicalName"] for e in client.get("EntityDefinitions", {"$select": "LogicalName"})["value"]}
    for t in defs.tables:
        if t.schema not in entities:
            problems.append(f"Tabelle {t.schema}")
            continue
        attrs = {a["LogicalName"] for a in client.get(f"EntityDefinitions(LogicalName='{t.schema}')/Attributes", {"$select": "LogicalName"})["value"]}
        problems += [f"Spalte {t.schema}.{c.schema}" for c in t.columns if c.schema not in attrs]
        problems += [f"Nachschlagefeld {t.schema}.{r.lookup.logical}" for r in defs.lookups_of(t.schema) if r.lookup.logical not in attrs]
    option_sets = {o["Name"] for o in client.get("GlobalOptionSetDefinitions", {"$select": "Name"})["value"]}
    problems += [f"Auswahlfeld {c.schema}" for c in defs.choices if c.schema not in option_sets]
    rels = {r["SchemaName"] for r in client.get("RelationshipDefinitions", {"$select": "SchemaName"})["value"]}
    problems += [f"Beziehung {r.schema}" for r in defs.relationships if r.schema not in rels]
    roles = {r["name"] for r in client.get_all("roles", {"$select": "name"})}
    problems += [f"Rolle {r.name}" for r in defs.security.roles if r.name not in roles]
    bus = {b["name"] for b in client.get("businessunits", {"$select": "name"})["value"]}
    problems += [f"Unternehmenseinheit {b}" for b in defs.security.business_units if b not in bus]
    teams = {t["name"] for t in client.get_all("teams", {"$select": "name"})}
    problems += [f"Team {owner_team_name(b)}" for b in defs.security.business_units if owner_team_name(b) not in teams]
    if not find_app_module(client, f"{settings.prefix}_{defs.app.unique_name.removeprefix(settings.prefix + '_')}"):
        problems.append("App-Modul")
    if expect_seed:
        data = read_seed(settings.seed_dir)
        for table in ORDER:
            n = client.get_text(f"{entity_set(client, table)}/$count")
            if int(n) < len(data[table]):
                problems.append(f"Seed {table}: {n} statt mindestens {len(data[table])} ({FILES[table]})")
    return problems
