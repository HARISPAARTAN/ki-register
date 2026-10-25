"""Environment auditing: the switch `organizations.isauditenabled`.

Dataverse writes audit records only while this switch is on, whatever the tables carry (`IsAuditEnabled` of KI-System, Risikobewertung and
Anwendungsfall, set by `apply --only metadata`). The switch is an organization setting, not a solution component: it does not travel with the
solution and is set per environment (ADR-002, ADR-003). `kiregister apply --only auditing` is the one apply variant that is also run against
Nordstern Test, because it touches the organization row and nothing else."""

from __future__ import annotations

import logging

from .client import DataverseClient

log = logging.getLogger(__name__)
COMPONENT = "Umgebungs-Auditing"


def _organization(client: DataverseClient) -> dict:
    """The single organization row of the environment."""
    rows = client.get("organizations", {"$select": "organizationid,isauditenabled"}).get("value", [])
    if len(rows) != 1:
        raise RuntimeError(f"Organisation nicht eindeutig: {len(rows)} Zeilen in organizations (erwartet: genau eine)")
    return rows[0]


def audit_enabled(client: DataverseClient) -> bool:
    """Whether auditing is switched on for the environment."""
    return bool(_organization(client)["isauditenabled"])


def ensure_auditing(client: DataverseClient) -> bool:
    """Switch environment auditing on. Reads first and sends a PATCH only if the switch is off; True only when it changed something."""
    org = _organization(client)
    if org["isauditenabled"]:
        return False
    client.patch(f"organizations({org['organizationid']})", {"isauditenabled": True}, solution=False, component=COMPONENT)
    log.info("Auditing der Umgebung eingeschaltet")
    return True
