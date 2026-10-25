import pytest

from kiregister.auditing import audit_enabled, ensure_auditing

pytestmark = pytest.mark.dataverse


def test_environment_auditing_is_on_after_apply_and_a_second_run_changes_nothing(client):
    ensure_auditing(client)  # what `kiregister apply --only auditing` does; it changes nothing when the switch is on already
    assert audit_enabled(client) is True
    assert ensure_auditing(client) is False


def test_the_tables_carry_the_audit_flag_of_the_definitions(client, defs):
    """The flag per table (`IsAuditEnabled`); Dataverse writes records for these tables while the environment switch is on."""
    flags = {t.schema: client.get(f"EntityDefinitions(LogicalName='{t.schema}')", {"$select": "IsAuditEnabled"})["IsAuditEnabled"]["Value"]
             for t in defs.tables}
    assert flags == {t.schema: t.audit for t in defs.tables}
    assert {table for table, audited in flags.items() if audited} == {"nst_kisystem", "nst_risikobewertung", "nst_anwendungsfall"}
