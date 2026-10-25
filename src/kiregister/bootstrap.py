"""Create the application user for the service principal in an environment, using the owner's Azure CLI token."""

from __future__ import annotations

import logging

from .client import DataverseClient

log = logging.getLogger(__name__)
SYSTEM_ADMINISTRATOR = "System Administrator"


def root_business_unit(client: DataverseClient) -> str:
    bu = client.find_one("businessunits", "_parentbusinessunitid_value eq null", "businessunitid")
    if not bu:
        raise RuntimeError("Wurzel-Unternehmenseinheit nicht gefunden")
    return bu["businessunitid"]


def ensure_application_user(client: DataverseClient, client_id: str) -> str:
    root_bu = root_business_unit(client)
    user = client.find_one("systemusers", f"applicationid eq {client_id}", "systemuserid")
    if user:
        user_id = user["systemuserid"]
    else:
        created = client.post("systemusers", {"applicationid": client_id, "businessunitid@odata.bind": f"/businessunits({root_bu})"},
                              solution=False, component="Anwendungsbenutzer")
        # with Prefer: return=representation the Web API may answer with the entity body instead of an OData-EntityId header
        user_id = created["systemuserid"] if isinstance(created, dict) else created
        log.info("Anwendungsbenutzer %s angelegt", user_id)
    role = client.find_one("roles", f"name eq '{SYSTEM_ADMINISTRATOR}' and _businessunitid_value eq {root_bu}", "roleid")
    if not role:
        raise RuntimeError("Rolle System Administrator nicht gefunden")
    assigned = client.get(f"systemusers({user_id})/systemuserroles_association", {"$select": "roleid"}).get("value", [])
    if not any(r["roleid"] == role["roleid"] for r in assigned):
        client.post(f"systemusers({user_id})/systemuserroles_association/$ref", {"@odata.id": f"{client.api_url}roles({role['roleid']})"},
                    solution=False, component="Rollenzuweisung System Administrator")
        log.info("Rolle System Administrator zugewiesen")
    return user_id
