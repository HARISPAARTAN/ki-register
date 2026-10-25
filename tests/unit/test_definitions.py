from pathlib import Path

from kiregister.definitions import load_definitions

DEFS = Path(__file__).resolve().parents[2] / "provision" / "definitions"


def test_loads_all_tables_choices_and_relationships():
    d = load_definitions(DEFS)
    assert [t.schema for t in d.tables] == ["nst_organisation", "nst_mitarbeiter", "nst_kisystem", "nst_anwendungsfall",
                                            "nst_risikobewertung", "nst_massnahme", "nst_schulung", "nst_schulungsteilnahme"]
    assert len(d.choices) == 10
    assert len(d.relationships) == 13
    assert d.security.business_units == ["Nordstern Projektmanagement", "Nordstern Energie", "Nordstern Klinikum"]


def test_every_choice_column_names_an_existing_choice():
    d = load_definitions(DEFS)
    names = {c.schema for c in d.choices}
    for t in d.tables:
        for col in t.columns:
            if col.type in ("choice", "multichoice"):
                assert col.choice in names, f"{t.schema}.{col.schema}"


def test_every_relationship_names_existing_tables_and_unique_lookups():
    d = load_definitions(DEFS)
    tables = {t.schema for t in d.tables}
    seen = set()
    for r in d.relationships:
        assert r.referenced in tables and r.referencing in tables
        key = (r.referencing, r.lookup.logical)
        assert key not in seen, f"duplicate lookup {key}"
        seen.add(key)


def test_lookup_schema_is_pascal_and_logical_is_lower():
    d = load_definitions(DEFS)
    schemas = {r.lookup.schema for r in d.relationships}
    assert schemas == {"nst_Organisation", "nst_Verantwortlicher", "nst_Antragsteller", "nst_Pruefer", "nst_KISystem",
                       "nst_Schulung", "nst_Mitarbeiter"}
    for r in d.relationships:
        assert r.lookup.schema.startswith("nst_") and r.lookup.schema.isascii()
        assert r.lookup.logical == r.lookup.schema.lower()


def test_schema_names_are_ascii_and_prefixed():
    d = load_definitions(DEFS)
    for t in d.tables:
        assert t.schema.startswith("nst_") and t.schema.isascii()
        for col in t.columns:
            assert col.schema.startswith("nst_") and col.schema.isascii(), col.schema


def test_app_views_reference_existing_columns():
    d = load_definitions(DEFS)
    cols = {t.schema: {c.schema for c in t.columns} | {t.primary.schema} for t in d.tables}
    lookups = {}
    for r in d.relationships:
        lookups.setdefault(r.referencing, set()).add(r.lookup.logical)
    for v in d.app.views:
        allowed = cols[v.table] | lookups.get(v.table, set())
        assert set(v.columns) <= allowed, (v.name, set(v.columns) - allowed)
