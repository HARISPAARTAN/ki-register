"""Verification used by `kiregister verify`, the integration tests and the deploy workflow."""

from __future__ import annotations

from .app import app_unique_name, find_app_module
from .client import DataverseClient
from .config import Settings
from .definitions import Definitions
from .security import OWNER_ROLE, owner_team_name
from .seed import FILES, ORDER, entity_set, read_seed


def _owner_invariants(client: DataverseClient, defs: Definitions, teams: dict[str, str]) -> list[str]:
    """Owner teams hold the read-only role on every table (Risikobewertung included): they must stay member-less and the role must
    never be assigned to a user, otherwise that user would read all records (ADR-002)."""
    problems = []
    for unit in defs.security.business_units:
        team_id = teams.get(owner_team_name(unit))
        if team_id:
            members = client.get_all(f"teams({team_id})/teammembership_association", {"$select": "systemuserid"})
            if members:
                problems.append(f"Team {owner_team_name(unit)} hat {len(members)} Mitglieder (muss leer sein)")
    for role in client.get_all("roles", {"$select": "roleid", "$filter": f"name eq '{OWNER_ROLE}'"}):
        holders = client.get_all(f"roles({role['roleid']})/systemuserroles_association", {"$select": "systemuserid"})
        if holders:
            problems.append(f"Rolle {OWNER_ROLE} ist {len(holders)} Benutzern zugewiesen (darf nur Teams zugewiesen sein)")
    return problems


def _column_security(client: DataverseClient, defs: Definitions) -> list[str]:
    """The column security profile and its field permissions (both are solution components)."""
    cs = defs.security.column_security
    profile = client.find_one("fieldsecurityprofiles", f"name eq '{cs.profile}'", "fieldsecurityprofileid")
    if not profile:
        return [f"Spaltensicherheitsprofil {cs.profile}"]
    permissions = {(p["entityname"], p["attributelogicalname"]) for p in client.get_all(
        "fieldpermissions", {"$select": "entityname,attributelogicalname", "$filter": f"_fieldsecurityprofileid_value eq {profile['fieldsecurityprofileid']}"})}
    return [f"Spaltenberechtigung {table}.{column}" for table, column in cs.columns if (table, column) not in permissions]


def run_verify(client: DataverseClient, settings: Settings, defs: Definitions, expect_seed: bool = True) -> list[str]:
    """Human-readable deviations from the definitions (and the seed CSVs); an empty list means everything matches.

    `expect_seed=False` checks the solution components only: tables, columns, choices, relationships, roles, the column security profile
    and the app module. Business units, owner teams, their membership and the seed are not solution components, so an environment that
    only received the managed solution (Nordstern Test, `deploy-test.yml`) has none of them (ADR-003)."""
    problems = []
    entities = {e["LogicalName"] for e in client.get("EntityDefinitions", {"$select": "LogicalName"})["value"]}
    missing_tables = set()
    for t in defs.tables:
        if t.schema not in entities:
            problems.append(f"Tabelle {t.schema}")
            missing_tables.add(t.schema)
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
    problems += _column_security(client, defs)
    if not find_app_module(client, app_unique_name(settings, defs)):
        problems.append("App-Modul")
    if expect_seed:
        bus = {b["name"] for b in client.get("businessunits", {"$select": "name"})["value"]}
        problems += [f"Unternehmenseinheit {b}" for b in defs.security.business_units if b not in bus]
        teams = {t["name"]: t["teamid"] for t in client.get_all("teams", {"$select": "teamid,name"})}
        problems += [f"Team {owner_team_name(b)}" for b in defs.security.business_units if owner_team_name(b) not in teams]
        problems += _owner_invariants(client, defs, teams)
        data = read_seed(settings.seed_dir)
        for table in ORDER:
            if table in missing_tables:
                problems.append(f"Seed {table}: Tabelle fehlt")
                continue
            n = client.get_text(f"{entity_set(client, table)}/$count")
            if int(n) < len(data[table]):
                problems.append(f"Seed {table}: {n} statt mindestens {len(data[table])} ({FILES[table]})")
    return problems
