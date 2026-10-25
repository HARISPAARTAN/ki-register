import pytest

from kiregister import security

pytestmark = pytest.mark.dataverse


def _role_privileges(client, role_name):
    """Privilege name -> depth mask held by the role (root business unit)."""
    role = client.find_one("roles", f"name eq '{role_name}'", "roleid")
    assert role is not None, role_name
    names = {p["privilegeid"]: p["name"] for p in client.get_all(f"roles({role['roleid']})/roleprivileges_association", {"$select": "privilegeid,name"})}
    masks = {r["privilegeid"]: r["privilegedepthmask"]
             for r in client.get_all("roleprivilegescollection", {"$select": "privilegeid,privilegedepthmask", "$filter": f"roleid eq {role['roleid']}"})}
    return {names[i]: masks[i] for i in names}


def test_business_units_roles_and_profile_exist(client, defs):
    names = {b["name"] for b in client.get("businessunits", {"$select": "name"})["value"]}
    assert set(defs.security.business_units) <= names
    roles = {r["name"] for r in client.get_all("roles", {"$select": "name"})}
    assert {r.name for r in defs.security.roles} <= roles
    prof = client.find_one("fieldsecurityprofiles", f"name eq '{defs.security.column_security.profile}'", "fieldsecurityprofileid")
    assert prof is not None


def test_business_units_are_children_of_the_root_and_have_a_default_team(client, defs):
    root, _ = security.root_business_unit(client)
    rows = client.get("businessunits", {"$select": "businessunitid,name,_parentbusinessunitid_value"})["value"]
    children = {r["name"]: r for r in rows if r["name"] in defs.security.business_units}
    assert set(children) == set(defs.security.business_units)
    assert all(r["_parentbusinessunitid_value"] == root for r in children.values())
    teams = security.default_team_ids(client, {n: r["businessunitid"] for n, r in children.items()})
    assert set(teams) == set(defs.security.business_units)


def test_child_business_units_inherit_the_roles(client, defs):
    rows = client.get("businessunits", {"$select": "businessunitid,name"})["value"]
    children = {r["name"]: r["businessunitid"] for r in rows if r["name"] in defs.security.business_units}
    for unit, unit_id in children.items():
        names = {r["name"] for r in client.get_all("roles", {"$select": "name", "$filter": f"_businessunitid_value eq {unit_id}"})}
        assert {r.name for r in defs.security.roles} <= names, unit


def test_governance_role_has_global_read_on_every_table(client, defs):
    role = client.find_one("roles", "name eq 'nst KI-Governance'", "roleid")
    privs = {p["name"] for p in client.get_all(f"roles({role['roleid']})/roleprivileges_association", {"$select": "name"})}
    for t in defs.tables:
        assert f"prvRead{t.schema}" in privs and f"prvDelete{t.schema}" in privs


def test_fachbereich_cannot_read_risikobewertung(client):
    role = client.find_one("roles", "name eq 'nst Fachbereich'", "roleid")
    privs = {p["name"] for p in client.get_all(f"roles({role['roleid']})/roleprivileges_association", {"$select": "name"})}
    assert "prvReadnst_risikobewertung" not in privs and "prvCreatenst_anwendungsfall" in privs


def test_every_role_holds_exactly_its_privileges_at_the_defined_depth(client, defs):
    all_tables = [t.schema for t in defs.tables]
    for role in defs.security.roles:
        held = _role_privileges(client, role.name)
        wanted = {n: security.DEPTH_MASK[d] for n, d in security.wanted_privileges(role, all_tables).items()}
        # Dataverse adds a few baseline privileges (prvReadSdkMessage ...) to every new role; compare the nst_ and extra ones only
        relevant = {n: m for n, m in held.items() if n in wanted or n.endswith(tuple(all_tables))}
        assert relevant == wanted, role.name


def test_governance_reads_user_team_and_business_unit(client):
    held = _role_privileges(client, "nst KI-Governance")
    for name in ("prvReadUser", "prvReadTeam", "prvReadBusinessUnit"):
        assert held[name] == security.DEPTH_MASK["Global"], name


def test_fachbereich_and_leser_depths(client):
    fachbereich = _role_privileges(client, "nst Fachbereich")
    assert fachbereich["prvReadnst_kisystem"] == security.DEPTH_MASK["Local"]
    assert fachbereich["prvCreatenst_anwendungsfall"] == security.DEPTH_MASK["Basic"]
    leser = _role_privileges(client, "nst Leser")
    nst = {n for n in leser if "nst_" in n}
    assert "prvReadnst_risikobewertung" not in nst and all(n.startswith("prvRead") for n in nst)


def test_column_security_profile_covers_the_secured_columns(client, defs):
    cs = defs.security.column_security
    prof = client.find_one("fieldsecurityprofiles", f"name eq '{cs.profile}'", "fieldsecurityprofileid")
    perms = client.get_all("fieldpermissions", {"$select": "entityname,attributelogicalname,canread,canupdate,cancreate",
                                                "$filter": f"_fieldsecurityprofileid_value eq {prof['fieldsecurityprofileid']}"})
    by_column = {(p["entityname"], p["attributelogicalname"]): p for p in perms}
    assert set(by_column) == set(cs.columns)
    for p in by_column.values():
        assert (p["canread"], p["canupdate"], p["cancreate"]) == (security.ALLOWED,) * 3
    for table, column in cs.columns:
        attr = client.get(f"EntityDefinitions(LogicalName='{table}')/Attributes(LogicalName='{column}')", {"$select": "IsSecured"})
        assert attr["IsSecured"] is True


def test_apply_security_is_idempotent(client, settings, defs):
    def snapshot():
        return (len(client.get("businessunits", {"$select": "name"})["value"]),
                len(client.get_all("roles", {"$select": "name"})),
                len(client.get_all("fieldsecurityprofiles", {"$select": "name"})),
                len(client.get_all("fieldpermissions", {"$select": "fieldpermissionid"})),
                {r.name: _role_privileges(client, r.name) for r in defs.security.roles})

    before = snapshot()
    result = security.apply_security(client, settings, defs)
    assert result["business_units"] == 3 and result["roles"] == 3
    assert snapshot() == before
