"""Seed CSVs to Dataverse upserts: deterministic GUIDs (uuid5), choice labels to values, lookups and team owners bound.

The owning team of a row is the owner team of its subsidiary (security.find_owner_teams), not the default team: see ADR-002.
All dates in the CSVs are anchored at SEED_ANCHOR; `load_seed` shifts them by whole weeks to the reference date (`--stichtag`),
so that "überfällig" stays true over time (spec 10)."""

from __future__ import annotations

import csv
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import builders
from .client import DataverseClient
from .config import Settings
from .definitions import Definitions
from .security import find_owner_teams

log = logging.getLogger(__name__)
DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")
NAMESPACE = uuid.UUID("6f1f0c1e-3a5b-4d2e-9f8a-2b7c1d0e9a11")
SEED_ANCHOR = date(2026, 10, 25)  # reference date of the dates in the CSVs
ORDER = ["nst_organisation", "nst_mitarbeiter", "nst_kisystem", "nst_anwendungsfall", "nst_risikobewertung", "nst_massnahme", "nst_schulung", "nst_schulungsteilnahme"]
FILES = {"nst_organisation": "organisationen.csv", "nst_mitarbeiter": "mitarbeiter.csv", "nst_kisystem": "kisysteme.csv", "nst_anwendungsfall": "anwendungsfaelle.csv",
         "nst_risikobewertung": "risikobewertungen.csv", "nst_massnahme": "massnahmen.csv", "nst_schulung": "schulungen.csv", "nst_schulungsteilnahme": "teilnahmen.csv"}


class SeedError(ValueError):
    """A cell of a seed CSV cannot be converted; the message names table, column and row key."""


def record_id(table: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{table}:{key}"))


def read_seed(seed_dir: Path) -> dict[str, list[dict]]:
    out = {}
    for table, name in FILES.items():
        with open(Path(seed_dir) / name, encoding="utf-8", newline="") as f:
            out[table] = list(csv.DictReader(f))
    return out


def delta_days(target: date) -> int:
    """Whole weeks between SEED_ANCHOR and `target` (rounded down), in days; whole weeks keep the weekdays."""
    return ((target - SEED_ANCHOR).days // 7) * 7


def shift_date(value: str, days: int) -> str:
    """Shift an ISO date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM:SSZ) by `days`; raises ValueError on any other format."""
    if "T" in value:
        moment = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return (moment + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not DATE_FORMAT.fullmatch(value):
        raise ValueError(f"Datum muss YYYY-MM-DD sein, ist {value!r}")
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


_entity_sets: dict[tuple[str, str], str] = {}


def entity_set(client: DataverseClient, table: str) -> str:
    key = (client.api_url, table)
    if key not in _entity_sets:
        _entity_sets[key] = client.get(f"EntityDefinitions(LogicalName='{table}')", {"$select": "EntitySetName"})["EntitySetName"]
    return _entity_sets[key]


def _option(defs: Definitions, col, label: str, option_prefix: int) -> int:
    if label not in defs.choice(col.choice).values:
        raise ValueError(f"unbekannte Auswahl {label!r} ({col.choice})")
    return builders.choice_value(defs, col.choice, label, option_prefix)


def _convert(defs: Definitions, col, v: str, option_prefix: int, shift_days: int):
    if col.type == "choice":
        return _option(defs, col, v, option_prefix)
    if col.type == "multichoice":
        return ",".join(str(_option(defs, col, x, option_prefix)) for x in v.split(";"))
    if col.type == "bool":
        if v not in ("0", "1"):
            raise ValueError(f"Wahrheitswert muss 0 oder 1 sein, ist {v!r}")
        return v == "1"
    if col.type == "int":
        return int(v)
    if col.type in ("date", "datetime"):
        return shift_date(v, shift_days)
    return v


def payload(table: str, row: dict, defs: Definitions, option_prefix: int, team_ids: dict[str, str], sets: dict[str, str] | None = None,
            shift_days: int = 0) -> dict:
    t = defs.table(table)
    sets = sets or {}
    p: dict = {t.primary.schema: row[t.primary.schema]} if t.primary.schema in row else {}
    for col in t.columns:
        v = row.get(col.schema, "")
        if v == "" or col.type in ("autonumber", "formula"):
            continue
        try:
            p[col.schema] = _convert(defs, col, v, option_prefix, shift_days)
        except ValueError as exc:
            raise SeedError(f"{table}.{col.schema} (Zeile {row.get('key', '?')}): {exc}") from exc
    for rel in defs.lookups_of(table):
        v = row.get(rel.lookup.schema, "")
        if v:
            target_set = sets.get(rel.referenced, rel.referenced + "s")
            p[f"{rel.lookup.schema}@odata.bind"] = f"/{target_set}({record_id(rel.referenced, v)})"
    org = row.get("org") or (row["key"] if table == "nst_organisation" else "")
    if org in team_ids:
        p["ownerid@odata.bind"] = f"/teams({team_ids[org]})"
    return p


def load_seed(client: DataverseClient, settings: Settings, defs: Definitions, stichtag: date | None = None) -> dict[str, int]:
    """Upsert every CSV row. Provisions nothing: business units and owner teams must exist (`kiregister apply --only security`)."""
    data = read_seed(settings.seed_dir)
    org_units = {r["key"]: r["nst_businessunitname"] for r in data["nst_organisation"]}
    owner_by_unit = find_owner_teams(client, sorted(set(org_units.values())))
    team_ids = {org: owner_by_unit[unit] for org, unit in org_units.items()}
    shift = delta_days(stichtag or datetime.now(UTC).date())
    log.info("Stichtag-Verschiebung: %d Tage gegenueber %s", shift, SEED_ANCHOR)
    sets = {t: entity_set(client, t) for t in ORDER}
    counts = {}
    for table in ORDER:
        n = 0
        for row in data[table]:
            body = payload(table, row, defs, settings.option_prefix, team_ids, sets, shift)
            client.patch(f"{sets[table]}({record_id(table, row['key'])})", body, solution=False, component=f"Seed {table} {row['key']}")
            n += 1
        counts[table] = n
        log.info("%s: %d Zeilen upserted", table, n)
    return counts
