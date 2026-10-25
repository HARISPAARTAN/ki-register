"""Business units, default teams, security roles with privileges, and the column security profile."""

from __future__ import annotations

import logging
import time

from .client import DataverseClient
from .config import Settings
from .definitions import Definitions

log = logging.getLogger(__name__)
PRIV_PREFIX = {"create": "prvCreate", "read": "prvRead", "write": "prvWrite", "delete": "prvDelete", "append": "prvAppend",
               "appendto": "prvAppendTo", "assign": "prvAssign", "share": "prvShare"}
DEPTH_VALUE = {"Basic": "Basic", "Local": "Local", "Deep": "Deep", "Global": "Global"}
DEPTH_MASK = {"Basic": 1, "Local": 2, "Deep": 4, "Global": 8}  # privilegedepthmask of the roleprivileges rows
ALLOWED = 4  # field permission value "Allowed"
NO_BUSINESS_UNIT = "00000000-0000-0000-0000-000000000000"
TEAM_WAIT_SECONDS = (0, 2, 4, 8)
OWNER_ROLE = "nst Datenbesitz"  # read-only role held by the owner teams, never assigned to users


def expand_tables(tables: dict[str, dict[str, str]], all_tables: list[str]) -> dict[str, dict[str, str]]:
    if "*" in tables:
        star = tables["*"]
        return {t: dict(star) for t in all_tables} | {k: v for k, v in tables.items() if k != "*"}
    return tables


def privilege_names(tables: dict[str, dict[str, str]]) -> dict[str, str]:
    out = {}
    for table, privs in tables.items():
        for name, depth in privs.items():
            out[f"{PRIV_PREFIX[name]}{table}"] = depth
    return out


def root_business_unit(client: DataverseClient) -> tuple[str, str]:
    rows = client.get("businessunits", {"$select": "businessunitid,name,_parentbusinessunitid_value"})["value"]
    root = next(r for r in rows if not r.get("_parentbusinessunitid_value"))
    return root["businessunitid"], root["name"]


def ensure_business_units(client: DataverseClient, names: list[str], root: str | None = None) -> dict[str, str]:
    """Child units of the root; pass `root` (from `root_business_unit`) to skip reading it again."""
    if root is None:
        root, _ = root_business_unit(client)
    rows = client.get("businessunits", {"$select": "businessunitid,name,_parentbusinessunitid_value"})["value"]
    existing = {r["name"]: r["businessunitid"] for r in rows}
    ids = {}
    for name in names:
        if name in existing:
            ids[name] = existing[name]
            continue
        ids[name] = client.post_id("businessunits", {"name": name, "parentbusinessunitid@odata.bind": f"/businessunits({root})"},
                                   solution=False, component=f"Unternehmenseinheit {name}")
        log.info("Unternehmenseinheit %s angelegt", name)
    return ids


def default_team_ids(client: DataverseClient, bu_ids: dict[str, str]) -> dict[str, str]:
    """The default team of a business unit is created by Dataverse together with the unit, possibly a moment later."""
    teams = {}
    for name, bu in bu_ids.items():
        team = None
        for wait in TEAM_WAIT_SECONDS:
            time.sleep(wait)
            team = client.find_one("teams", f"_businessunitid_value eq {bu} and isdefault eq true", "teamid")
            if team:
                break
        if not team:
            raise RuntimeError(f"Standardteam der Einheit {name} nicht gefunden")
        teams[name] = team["teamid"]
    return teams


def owner_team_name(business_unit: str) -> str:
    return f"{business_unit} Datenbesitz"


def ensure_owner_teams(client: DataverseClient, bu_ids: dict[str, str]) -> dict[str, str]:
    """One member-less owner team per business unit, holding the read-only role `nst Datenbesitz`.

    Dataverse refuses to assign a record to a team that has no read privilege on the table (0x80040299). The default team of a unit
    cannot carry that role: every user of the unit is a member of it and would inherit read on all tables, Risikobewertung included,
    which `nst Fachbereich` must not see. A separate team without members owns the records instead; the unit still sees them through
    the owning business unit (spec 5)."""
    admin = client.get("WhoAmI")["UserId"]
    teams = {}
    for unit, bu in bu_ids.items():
        name = owner_team_name(unit)
        team = client.find_one("teams", f"name eq '{name}' and _businessunitid_value eq {bu}", "teamid")
        team_id = team["teamid"] if team else client.post_id(
            "teams", {"name": name, "teamtype": 0, "description": "Besitzer der Registerdaten der Einheit (ohne Mitglieder)",
                      "businessunitid@odata.bind": f"/businessunits({bu})", "administratorid@odata.bind": f"/systemusers({admin})"},
            solution=False, component=f"Team {name}")
        if not team:
            log.info("Team %s angelegt", name)
        role_id = _role_in_unit(client, OWNER_ROLE, bu)
        assigned = {r["roleid"] for r in client.get_all(f"teams({team_id})/teamroles_association", {"$select": "roleid"})}
        if role_id not in assigned:
            client.post(f"teams({team_id})/teamroles_association/$ref", {"@odata.id": f"{client.api_url}roles({role_id})"}, solution=False,
                        component=f"Rolle {OWNER_ROLE} fuer Team {name}")
            log.info("Team %s: Rolle %s zugewiesen", name, OWNER_ROLE)
        teams[unit] = team_id
    return teams


def find_owner_teams(client: DataverseClient, units: list[str]) -> dict[str, str]:
    """Owner team id per business unit name; read-only. Stops when a unit or its owner team is missing (created by `apply --only security`)."""
    rows = client.get("businessunits", {"$select": "businessunitid,name"})["value"]
    unit_ids = {r["name"]: r["businessunitid"] for r in rows}
    teams = {}
    for unit in units:
        if unit not in unit_ids:
            raise RuntimeError(f"Unternehmenseinheit {unit} fehlt: zuerst `kiregister apply --only security` ausführen")
        name = owner_team_name(unit)
        team = client.find_one("teams", f"name eq '{name}' and _businessunitid_value eq {unit_ids[unit]}", "teamid")
        if not team:
            raise RuntimeError(f"Team {name} fehlt: zuerst `kiregister apply --only security` ausführen")
        teams[unit] = team["teamid"]
    return teams


def _role_in_unit(client: DataverseClient, role: str, bu: str) -> str:
    """The copy of a root role inside a child unit; Dataverse creates the copy together with the role, possibly a moment later."""
    for wait in TEAM_WAIT_SECONDS:
        time.sleep(wait)
        found = client.find_one("roles", f"name eq '{role}' and _businessunitid_value eq {bu}", "roleid")
        if found:
            return found["roleid"]
    raise RuntimeError(f"Rolle {role} in der Einheit {bu} nicht gefunden (zuerst `apply --only security` ausfuehren)")


def _privilege_ids(client: DataverseClient, names: set[str]) -> dict[str, str]:
    rows = client.get_all("privileges", {"$select": "privilegeid,name"})
    found = {r["name"]: r["privilegeid"] for r in rows if r["name"] in names}
    missing = names - set(found)
    if missing:
        raise RuntimeError(f"Privilegien fehlen (Tabellen noch nicht veroeffentlicht?): {sorted(missing)}")
    return found


def wanted_privileges(role, all_tables: list[str]) -> dict[str, str]:
    """Table privileges of the role (with `*` expanded) plus its extra privileges such as prvReadUser."""
    return {**privilege_names(expand_tables(role.tables, all_tables)), **role.extra}


def ensure_roles(client: DataverseClient, defs: Definitions, root_bu: str) -> dict[str, str]:
    all_tables = [t.schema for t in defs.tables]
    role_ids = {}
    for role in defs.security.roles:
        existing = client.find_one("roles", f"name eq '{role.name}' and _businessunitid_value eq {root_bu}", "roleid")
        role_id = existing["roleid"] if existing else client.post_id(
            "roles", {"name": role.name, "businessunitid@odata.bind": f"/businessunits({root_bu})"}, component=f"Rolle {role.name}")
        if not existing:
            log.info("Rolle %s angelegt", role.name)
        wanted = wanted_privileges(role, all_tables)
        ids = _privilege_ids(client, set(wanted))
        have = {r["privilegeid"]: r["privilegedepthmask"]
                for r in client.get_all("roleprivilegescollection", {"$select": "privilegeid,privilegedepthmask", "$filter": f"roleid eq {role_id}"})}
        todo = [{"PrivilegeId": ids[n], "Depth": DEPTH_VALUE[d], "BusinessUnitId": NO_BUSINESS_UNIT} for n, d in wanted.items()
                if have.get(ids[n]) != DEPTH_MASK[d]]
        if todo:
            client.action(f"roles({role_id})/Microsoft.Dynamics.CRM.AddPrivilegesRole", {"Privileges": todo}, solution=False)
            log.info("Rolle %s: %d Privilegien ergaenzt", role.name, len(todo))
        role_ids[role.name] = role_id
    return role_ids


def ensure_column_security(client: DataverseClient, defs: Definitions) -> str:
    """Profile and field permissions (read, update, create all Allowed; a differing permission is repaired).

    The profile is not bound to any role in code: the governance users are added to it in the portal
    (`security.toml: roles_with_access` documents who it is for; rebuild guide)."""
    cs = defs.security.column_security
    prof = client.find_one("fieldsecurityprofiles", f"name eq '{cs.profile}'", "fieldsecurityprofileid")
    prof_id = prof["fieldsecurityprofileid"] if prof else client.post_id(
        "fieldsecurityprofiles", {"name": cs.profile, "description": "Zugriff auf gesicherte Spalten des KI-Registers"},
        component=f"Spaltensicherheitsprofil {cs.profile}")
    existing = {(p["entityname"], p["attributelogicalname"]): p for p in client.get_all(
        "fieldpermissions", {"$select": "fieldpermissionid,entityname,attributelogicalname,canread,canupdate,cancreate",
                             "$filter": f"_fieldsecurityprofileid_value eq {prof_id}"})}
    wanted = {"canread": ALLOWED, "canupdate": ALLOWED, "cancreate": ALLOWED}
    for table, column in cs.columns:
        have = existing.get((table, column))
        if have is None:
            client.post("fieldpermissions", {"entityname": table, "attributelogicalname": column, **wanted,
                                             "fieldsecurityprofileid@odata.bind": f"/fieldsecurityprofiles({prof_id})"},
                        component=f"Spaltenberechtigung {table}.{column}")
            log.info("Spaltensicherheit %s.%s im Profil %s", table, column, cs.profile)
        elif any(have.get(k) != v for k, v in wanted.items()):
            client.patch(f"fieldpermissions({have['fieldpermissionid']})", wanted, component=f"Spaltenberechtigung {table}.{column}")
            log.info("Spaltensicherheit %s.%s korrigiert", table, column)
    return prof_id


def apply_security(client: DataverseClient, settings: Settings, defs: Definitions) -> dict:
    root_bu, _ = root_business_unit(client)
    bu_ids = ensure_business_units(client, defs.security.business_units, root_bu)
    teams = default_team_ids(client, bu_ids)
    roles = ensure_roles(client, defs, root_bu)
    owner_teams = ensure_owner_teams(client, bu_ids)
    profile = ensure_column_security(client, defs)
    return {"business_units": len(bu_ids), "teams": len(teams), "owner_teams": len(owner_teams), "roles": len(roles), "column_profile": profile}
