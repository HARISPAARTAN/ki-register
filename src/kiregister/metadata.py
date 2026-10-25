"""Ensure publisher, solution, global choices, tables, columns and relationships; publish."""

from __future__ import annotations

import logging

from . import builders
from .client import DataverseClient, DataverseError
from .config import Settings
from .definitions import Definitions

log = logging.getLogger(__name__)


def ensure_publisher_and_solution(client: DataverseClient, settings: Settings) -> None:
    pub = client.find_one("publishers", f"uniquename eq '{settings.publisher_unique}'", "publisherid")
    if not pub:
        pub_id = client.post_id("publishers", {"uniquename": settings.publisher_unique, "friendlyname": settings.publisher_display,
                                            "customizationprefix": settings.prefix, "customizationoptionvalueprefix": settings.option_prefix},
                             solution=False, component=settings.publisher_unique)
        log.info("Publisher %s angelegt", settings.publisher_unique)
    else:
        pub_id = pub["publisherid"]
    sol = client.find_one("solutions", f"uniquename eq '{settings.solution}'", "solutionid,version")
    if not sol:
        client.post("solutions", {"uniquename": settings.solution, "friendlyname": settings.solution_display, "version": settings.solution_version,
                                  "publisherid@odata.bind": f"/publishers({pub_id})"},
                    solution=False, component=settings.solution)
        log.info("Loesung %s angelegt", settings.solution)
    elif sol.get("version") != settings.solution_version:
        # the version is raised per milestone in config.toml (spec 9); the next export and the managed deployment carry it
        client.patch(f"solutions({sol['solutionid']})", {"version": settings.solution_version}, solution=False,
                     component=f"Loesung {settings.solution} Version")
        log.info("Loesung %s: Version %s auf %s gesetzt", settings.solution, sol.get("version"), settings.solution_version)


def ensure_choices(client: DataverseClient, defs: Definitions, option_prefix: int) -> dict[str, str]:
    existing = {o["Name"]: o["MetadataId"] for o in client.get("GlobalOptionSetDefinitions", {"$select": "Name,MetadataId"}).get("value", [])}
    ids = {}
    for c in defs.choices:
        if c.schema in existing:
            ids[c.schema] = existing[c.schema]
            continue
        ids[c.schema] = client.post_id("GlobalOptionSetDefinitions", builders.choice_payload(c, option_prefix), component=c.schema)
        log.info("Auswahl %s angelegt", c.schema)
    return ids


def ensure_tables(client: DataverseClient, defs: Definitions) -> None:
    existing = {e["LogicalName"] for e in client.get("EntityDefinitions", {"$select": "LogicalName"}).get("value", [])}
    for t in defs.tables:
        if t.schema in existing:
            continue
        client.post("EntityDefinitions", builders.table_payload(t), component=t.schema)
        log.info("Tabelle %s angelegt", t.schema)


def _attribute_names(client: DataverseClient, table: str) -> set[str]:
    rows = client.get(f"EntityDefinitions(LogicalName='{table}')/Attributes", {"$select": "LogicalName"}).get("value", [])
    return {r["LogicalName"] for r in rows}


def ensure_columns(client: DataverseClient, defs: Definitions, choice_ids: dict[str, str]) -> None:
    for t in defs.tables:
        present = _attribute_names(client, t.schema)
        for col in t.columns:
            if col.schema in present:
                continue
            try:
                client.post(f"EntityDefinitions(LogicalName='{t.schema}')/Attributes", builders.column_payload(t, col, choice_ids),
                            component=f"{t.schema}.{col.schema}")
            except DataverseError as exc:
                if col.type == "formula" and exc.status == 400:
                    log.warning("Formelspalte %s.%s abgelehnt (%s); Ansichtsfilter ist der Ersatz (ADR-002)", t.schema, col.schema, exc.message)
                    continue
                raise
            log.info("Spalte %s.%s angelegt", t.schema, col.schema)


def ensure_relationships(client: DataverseClient, defs: Definitions) -> None:
    existing = {r["SchemaName"] for r in client.get("RelationshipDefinitions", {"$select": "SchemaName"}).get("value", [])}
    for r in defs.relationships:
        if r.schema in existing:
            continue
        client.post("RelationshipDefinitions", builders.relationship_payload(r), component=r.schema)
        log.info("Beziehung %s angelegt", r.schema)


def publish_all(client: DataverseClient) -> None:
    client.action("PublishAllXml", solution=False)


def apply_metadata(client: DataverseClient, settings: Settings, defs: Definitions) -> dict[str, int]:
    if client.solution != settings.solution:
        raise ValueError(f"Client-Loesung {client.solution!r} entspricht nicht der Konfiguration {settings.solution!r}")
    ensure_publisher_and_solution(client, settings)
    choice_ids = ensure_choices(client, defs, settings.option_prefix)
    ensure_tables(client, defs)
    ensure_columns(client, defs, choice_ids)
    ensure_relationships(client, defs)
    publish_all(client)
    return {"choices": len(choice_ids), "tables": len(defs.tables), "relationships": len(defs.relationships)}
