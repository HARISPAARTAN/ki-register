import pytest

pytestmark = pytest.mark.dataverse


def test_every_table_column_and_relationship_exists(client, defs):
    entities = {e["LogicalName"] for e in client.get("EntityDefinitions", {"$select": "LogicalName"})["value"]}
    for t in defs.tables:
        assert t.schema in entities
        attrs = {a["LogicalName"] for a in client.get(f"EntityDefinitions(LogicalName='{t.schema}')/Attributes", {"$select": "LogicalName"})["value"]}
        missing = {c.schema for c in t.columns if c.type != "formula"} - attrs
        assert not missing, (t.schema, missing)
    rels = {r["SchemaName"] for r in client.get("RelationshipDefinitions", {"$select": "SchemaName"})["value"]}
    assert {r.schema for r in defs.relationships} <= rels


def test_choice_values_match_definitions(client, defs, settings):
    for c in defs.choices:
        data = client.get(f"GlobalOptionSetDefinitions(Name='{c.schema}')")
        labels = [o["Label"]["LocalizedLabels"][0]["Label"] for o in data["Options"]]
        values = [o["Value"] for o in data["Options"]]
        assert labels == c.values and values == [settings.option_prefix * 10000 + i for i in range(len(c.values))]


def test_apply_is_idempotent(client, settings, defs):
    from kiregister.metadata import apply_metadata
    before = client.get("EntityDefinitions", {"$select": "LogicalName"})["value"]
    apply_metadata(client, settings, defs)
    after = client.get("EntityDefinitions", {"$select": "LogicalName"})["value"]
    assert len(before) == len(after)
