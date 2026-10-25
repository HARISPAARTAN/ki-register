"""Seed CSVs to Dataverse upserts: deterministic GUIDs (uuid5), choice labels to values, lookups and team owners bound.

The owning team of a row is the owner team of its subsidiary (security.ensure_owner_teams), not the default team: see ADR-002."""

from __future__ import annotations

import csv
import logging
import uuid
from pathlib import Path

from .client import DataverseClient
from .config import Settings
from .definitions import Definitions

log = logging.getLogger(__name__)
NAMESPACE = uuid.UUID("6f1f0c1e-3a5b-4d2e-9f8a-2b7c1d0e9a11")
ORDER = ["nst_organisation", "nst_mitarbeiter", "nst_kisystem", "nst_anwendungsfall", "nst_risikobewertung", "nst_massnahme", "nst_schulung", "nst_schulungsteilnahme"]
FILES = {"nst_organisation": "organisationen.csv", "nst_mitarbeiter": "mitarbeiter.csv", "nst_kisystem": "kisysteme.csv", "nst_anwendungsfall": "anwendungsfaelle.csv",
         "nst_risikobewertung": "risikobewertungen.csv", "nst_massnahme": "massnahmen.csv", "nst_schulung": "schulungen.csv", "nst_schulungsteilnahme": "teilnahmen.csv"}
ORG_TO_BU = {"PM": "Nordstern Projektmanagement", "EN": "Nordstern Energie", "KL": "Nordstern Klinikum"}


def record_id(table: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{table}:{key}"))


def read_seed(seed_dir: Path) -> dict[str, list[dict]]:
    out = {}
    for table, name in FILES.items():
        with open(Path(seed_dir) / name, encoding="utf-8", newline="") as f:
            out[table] = list(csv.DictReader(f))
    return out


_entity_sets: dict[str, str] = {}


def entity_set(client: DataverseClient, table: str) -> str:
    if table not in _entity_sets:
        _entity_sets[table] = client.get(f"EntityDefinitions(LogicalName='{table}')", {"$select": "EntitySetName"})["EntitySetName"]
    return _entity_sets[table]


def payload(table: str, row: dict, defs: Definitions, option_prefix: int, team_ids: dict[str, str], sets: dict[str, str] | None = None) -> dict:
    t = defs.table(table)
    sets = sets or {}
    p: dict = {t.primary.schema: row[t.primary.schema]} if t.primary.schema in row else {}
    for col in t.columns:
        v = row.get(col.schema, "")
        if v == "" or col.type in ("autonumber", "formula"):
            continue
        if col.type == "choice":
            p[col.schema] = option_prefix * 10000 + defs.choice(col.choice).values.index(v)
        elif col.type == "multichoice":
            p[col.schema] = ",".join(str(option_prefix * 10000 + defs.choice(col.choice).values.index(x)) for x in v.split(";"))
        elif col.type == "bool":
            p[col.schema] = v == "1"
        elif col.type == "int":
            p[col.schema] = int(v)
        else:
            p[col.schema] = v
    for rel in defs.lookups_of(table):
        v = row.get(rel.lookup.schema, "")
        if v:
            target_set = sets.get(rel.referenced, rel.referenced + "s")
            p[f"{rel.lookup.schema}@odata.bind"] = f"/{target_set}({record_id(rel.referenced, v)})"
    org = row.get("org") or (row["key"] if table == "nst_organisation" else "")
    if org in team_ids:
        p["ownerid@odata.bind"] = f"/teams({team_ids[org]})"
    return p


def load_seed(client: DataverseClient, settings: Settings, defs: Definitions) -> dict[str, int]:
    from .security import ensure_business_units, ensure_owner_teams
    bu_ids = ensure_business_units(client, defs.security.business_units)
    teams_by_bu = ensure_owner_teams(client, bu_ids)
    team_ids = {org: teams_by_bu[bu] for org, bu in ORG_TO_BU.items()}
    data = read_seed(settings.seed_dir)
    sets = {t: entity_set(client, t) for t in ORDER}
    counts = {}
    for table in ORDER:
        n = 0
        for row in data[table]:
            body = payload(table, row, defs, settings.option_prefix, team_ids, sets)
            client.patch(f"{sets[table]}({record_id(table, row['key'])})", body, solution=False, component=f"Seed {table} {row['key']}")
            n += 1
        counts[table] = n
        log.info("%s: %d Zeilen upserted", table, n)
    return counts


def teardown_order() -> list[str]:
    """Delete order for a teardown: children before parents (Teilnahmen before Mitarbeiter, Restrict relationships)."""
    return list(reversed(ORDER))


def teardown_seed(client: DataverseClient) -> dict[str, int]:
    """Delete every seeded row by its deterministic id. Written for completeness; no command calls it and it is never run against an environment."""
    data = read_seed(Path(__file__).resolve().parents[2] / "data" / "seed")
    counts = {}
    for table in teardown_order():
        for row in data[table]:
            client.delete(f"{entity_set(client, table)}({record_id(table, row['key'])})")
        counts[table] = len(data[table])
    return counts
