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


TYPE_NAMES = {"string": "StringType", "url": "StringType", "email": "StringType", "autonumber": "StringType", "memo": "MemoType",
              "int": "IntegerType", "date": "DateTimeType", "datetime": "DateTimeType", "bool": "BooleanType",
              "choice": "PicklistType", "multichoice": "MultiSelectPicklistType", "formula": "BooleanType"}


def _attributes(client, table):
    rows = client.get(f"EntityDefinitions(LogicalName='{table}')/Attributes",
                      {"$select": "LogicalName,AttributeTypeName,RequiredLevel,IsSecured,SourceType"})["value"]
    return {a["LogicalName"]: a for a in rows}


def _string_lengths(client, table):
    rows = client.get(f"EntityDefinitions(LogicalName='{table}')/Attributes/Microsoft.Dynamics.CRM.StringAttributeMetadata",
                      {"$select": "LogicalName,MaxLength"})["value"]
    return {a["LogicalName"]: a["MaxLength"] for a in rows}


def test_columns_have_the_defined_type_length_required_level_and_security(client, defs):
    for t in defs.tables:
        attrs = _attributes(client, t.schema)
        lengths = _string_lengths(client, t.schema)
        for c in t.columns:
            a = attrs[c.schema]
            where = f"{t.schema}.{c.schema}"
            assert a["AttributeTypeName"]["Value"] == TYPE_NAMES[c.type], where
            assert bool(a["IsSecured"]) == c.secured, where
            wanted_level = "ApplicationRequired" if c.required else "None"
            assert a["RequiredLevel"]["Value"] == wanted_level, where
            if c.type == "string":
                assert lengths[c.schema] == c.length, where
        primary = attrs[t.primary.schema]
        assert primary["AttributeTypeName"]["Value"] == "StringType" and lengths[t.primary.schema] == t.primary.length, t.schema


def test_formula_column_exists_with_its_formula(client, defs):
    formulas = [(t, c) for t in defs.tables for c in t.columns if c.type == "formula"]
    assert formulas
    for t, c in formulas:
        a = client.get(f"EntityDefinitions(LogicalName='{t.schema}')/Attributes(LogicalName='{c.schema}')/Microsoft.Dynamics.CRM.BooleanAttributeMetadata",
                       {"$select": "LogicalName,SourceType,FormulaDefinition"})
        assert a["SourceType"] == 3, c.schema
        assert "UTCToday()" in a["FormulaDefinition"], c.schema


def test_relationships_match_definitions(client, defs):
    rows = client.get("RelationshipDefinitions/Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata",
                      {"$select": "SchemaName,ReferencedEntity,ReferencingEntity,CascadeConfiguration"})["value"]
    by_name = {r["SchemaName"]: r for r in rows}
    for rel in defs.relationships:
        r = by_name[rel.schema]
        assert r["ReferencedEntity"] == rel.referenced and r["ReferencingEntity"] == rel.referencing, rel.schema
        assert r["CascadeConfiguration"]["Delete"] == rel.delete, rel.schema
        assert rel.lookup.logical in _attributes(client, rel.referencing), rel.schema


def test_choice_labels_exist_in_the_base_language(client, defs):
    # the org base language is 1033 only: Dataverse accepts the 1031 twin but stores no label for a language that is not provisioned
    for c in defs.choices:
        data = client.get(f"GlobalOptionSetDefinitions(Name='{c.schema}')")
        for o, expected in zip(data["Options"], c.values, strict=True):
            labels = {x["LanguageCode"]: x["Label"] for x in o["Label"]["LocalizedLabels"]}
            assert labels.get(1033) == expected, c.schema


def test_choice_values_match_definitions(client, defs, settings):
    for c in defs.choices:
        data = client.get(f"GlobalOptionSetDefinitions(Name='{c.schema}')")
        labels = [o["Label"]["LocalizedLabels"][0]["Label"] for o in data["Options"]]
        values = [o["Value"] for o in data["Options"]]
        assert labels == c.values and values == [settings.option_prefix * 10000 + i for i in range(len(c.values))]


def test_apply_is_idempotent(client, settings, defs):
    from kiregister.metadata import apply_metadata
    def snapshot():
        entities = {e["LogicalName"] for e in client.get("EntityDefinitions", {"$select": "LogicalName"})["value"]}
        columns = {t.schema: len(_attributes(client, t.schema)) for t in defs.tables}
        rels = len(client.get("RelationshipDefinitions", {"$select": "SchemaName"})["value"])
        choices = len(client.get("GlobalOptionSetDefinitions", {"$select": "Name"})["value"])
        return entities, columns, rels, choices

    before = snapshot()
    apply_metadata(client, settings, defs)
    assert snapshot() == before
