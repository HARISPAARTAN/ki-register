"""docs/erd.md is generated from the definitions by tools/erd.py: it lists every table, column and relationship, uses only syntax that
Mermaid accepts, and is up to date."""

import importlib.util
import re
from pathlib import Path

from kiregister.config import load_settings
from kiregister.definitions import COLUMN_TYPES, load_definitions

ROOT = Path(__file__).resolve().parents[2]
DEFS = load_definitions(ROOT / "provision" / "definitions")
OPTION_PREFIX = load_settings("dev", ROOT).option_prefix


def _load_tool():
    spec = importlib.util.spec_from_file_location("erd_tool", ROOT / "tools" / "erd.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


erd = _load_tool()
TEXT = erd.render(DEFS, OPTION_PREFIX)
DIAGRAM = TEXT.split("```mermaid\n", 1)[1].split("\n```", 1)[0]
BELOW = TEXT.split("\n```\n", 1)[1]  # everything after the diagram


def entity_body(table: str) -> str:
    block = re.search(rf"^    {table} \{{\n(.*?)^    \}}$", DIAGRAM, re.S | re.M)
    assert block, f"{table} fehlt im Diagramm"
    return block.group(1)


def test_every_table_is_an_entity_with_its_key_primary_column_columns_and_lookups():
    assert len(DEFS.tables) == 8
    for t in DEFS.tables:
        body = entity_body(t.schema)
        assert f"        guid {t.schema}id PK " in body, t.schema
        assert f"        string {t.primary.schema} " in body, t.schema
        for col in t.columns:
            assert re.search(rf"^        {erd.TYPE_NAMES[col.type]} {col.schema} \"", body, re.M), (t.schema, col.schema)
        for rel in DEFS.lookups_of(t.schema):
            assert f"        guid {rel.lookup.logical} FK " in body, (t.schema, rel.schema)
    assert DIAGRAM.count(" {\n") == len(DEFS.tables)  # no entity beyond the tables


def test_every_relationship_is_one_line_labelled_with_the_lookup_display_name():
    lines = [line for line in DIAGRAM.splitlines() if "--o{" in line]
    assert len(lines) == len(DEFS.relationships) == 13
    for rel in DEFS.relationships:
        parent_side = "||" if rel.lookup.required else "|o"
        assert f'    {rel.referenced} {parent_side}--o{{ {rel.referencing} : "{rel.lookup.display}"' in lines, rel.schema
    assert any(line.split()[1] == "||--o{" for line in lines) and any(line.split()[1] == "|o--o{" for line in lines)


def test_the_diagram_uses_only_plain_mermaid_er_syntax():
    """The grammar of Mermaid's erDiagram: names of letters, digits and underscores, a quoted comment at the end of every attribute, and
    no attribute or entity that the lexer would take for a key (PK, FK, UK, case-insensitive) or a relationship keyword."""
    lines = DIAGRAM.splitlines()
    assert lines[0] == "erDiagram"
    name = r"[A-Za-z_][A-Za-z0-9_]*"
    patterns = [rf"^    {name} \{{$", r"^    \}$", rf'^        [a-z]+ {name}( PK| FK)? "[^"%\\]*"$',
                rf'^    {name} (\|\||\|o)--o\{{ {name} : "[^"%\\]+"$']
    for line in lines[1:]:
        assert any(re.match(p, line) for p in patterns), line
    unquoted = [re.sub(r' (PK|FK)$', "", re.sub(r'"[^"]*"', "", line).rstrip()) for line in lines[1:]]  # leaves types, names and entities
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", "\n".join(unquoted)))
    reserved = {"pk", "fk", "uk", "one", "only", "many", "zero", "style", "class", "classdef", "subgraph", "end", "to", "optionally"}
    assert not {w for w in words if w.lower() in reserved}
    assert "~" not in DIAGRAM and "`" not in DIAGRAM


def test_every_column_type_has_a_mermaid_type():
    assert set(erd.TYPE_NAMES) == COLUMN_TYPES
    assert all(re.fullmatch(r"[a-z]+", t) for t in erd.TYPE_NAMES.values())


def test_columns_say_what_they_use():
    body = entity_body("nst_kisystem")
    assert 'choice nst_status "Status, Pflicht, Auswahl nst_status_kisystem"' in body
    assert 'choices nst_datenarten "Verarbeitete Datenarten, Auswahl nst_datenart"' in body
    assert 'autonumber nst_kennung "Kennung, Format KIS-nnnn"' in body
    assert "gesichert (Spaltensicherheit)" in next(line for line in body.splitlines() if " nst_internebewertung " in line)
    assert 'formula nst_pruefungueberfaellig "Prüfung überfällig, Formel, Ergebnis bool"' in body
    assert 'guid nst_organisation FK "Organisation, Nachschlagefeld auf nst_organisation, Pflicht"' in body
    assert 'guid nst_verantwortlicher FK "Verantwortlich, Nachschlagefeld auf nst_mitarbeiter"' in body  # optional: no "Pflicht"


def test_tables_relationships_and_choices_are_listed_below_the_diagram():
    for t in DEFS.tables:
        assert f"| `{t.schema}` | {t.display} | {t.plural} | `{t.primary.schema}` |" in BELOW, t.schema
    for rel in DEFS.relationships:
        assert f"| `{rel.schema}` | `{rel.referenced}` | `{rel.referencing}` | `{rel.lookup.logical}` ({rel.lookup.display}) |" in BELOW, rel.schema
    for c in DEFS.choices:
        assert f"| `{c.schema}` | {c.display} | {'; '.join(c.values)} |" in BELOW, c.schema
    assert "| `nst_schulung_teilnahme` | `nst_schulung` | `nst_schulungsteilnahme` | `nst_schulung` (Schulung) | ja | Datensätze mitlöschen |" in BELOW
    assert "| `nst_mitarbeiter_teilnahme` | `nst_mitarbeiter` | `nst_schulungsteilnahme` | `nst_mitarbeiter` (Mitarbeiter) | ja | Löschen verhindern |" in BELOW
    assert f"`{OPTION_PREFIX * 10000}` plus die Position" in BELOW


def test_docs_erd_md_is_what_the_definitions_produce():
    """Fails when a definition changed and docs/erd.md was not regenerated: uv run python tools/erd.py"""
    assert (ROOT / "docs" / "erd.md").read_text(encoding="utf-8") == TEXT


def test_main_writes_the_file_and_check_reports_a_stale_or_missing_one(tmp_path, capsys):
    target = tmp_path / "erd.md"
    assert erd.main(["--check", "--output", str(target)]) == 1  # missing
    assert "veraltet" in capsys.readouterr().err
    assert erd.main(["--output", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == TEXT and "\r" not in target.read_text(encoding="utf-8", newline="")
    assert erd.main(["--check", "--output", str(target)]) == 0
    target.write_text(TEXT.replace("nst_kisystem", "nst_kisystemx", 1), encoding="utf-8")
    assert erd.main(["--check", "--output", str(target)]) == 1  # stale
