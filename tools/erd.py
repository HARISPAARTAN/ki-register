"""Write docs/erd.md: a Mermaid entity relationship diagram generated from provision/definitions/*.toml.

    uv run python tools/erd.py            # write docs/erd.md
    uv run python tools/erd.py --check    # exit code 1 if docs/erd.md is not what the definitions produce

Entity names are the schema names of the tables (ASCII and underscores only), so GitHub renders the diagram without special characters in
names. The German display names stand in the column comments, in the relationship labels and in the tables below the diagram.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from kiregister.config import load_settings
from kiregister.definitions import Column, Definitions, Relationship, Table, load_definitions

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "erd.md"

# Mermaid attribute types: a letter first, then letters, digits and underscores. One entry per column type of the definitions
# (tests/unit/test_erd.py fails when a new column type has none).
TYPE_NAMES = {"string": "string", "memo": "memo", "int": "int", "bool": "bool", "date": "date", "datetime": "datetime", "url": "url",
              "email": "email", "choice": "choice", "multichoice": "choices", "autonumber": "autonumber", "formula": "formula"}
DELETE_TEXT = {"Cascade": "Datensätze mitlöschen", "RemoveLink": "Verknüpfung entfernen", "Restrict": "Löschen verhindern"}


def _comment(text: str) -> str:
    """A Mermaid comment sits in double quotes and cannot contain one."""
    return '"' + text.replace('"', "'") + '"'


def _autonumber(pattern: str | None) -> str:
    """KIS-{SEQNUM:4} becomes KIS-nnnn: braces stay out of the diagram."""
    return re.sub(r"\{SEQNUM:(\d+)\}", lambda m: "n" * int(m.group(1)), pattern or "")


def column_line(col: Column) -> str:
    notes = [col.display]
    if col.required:
        notes.append("Pflicht")
    if col.secured:
        notes.append("gesichert (Spaltensicherheit)")
    if col.type in ("choice", "multichoice"):
        notes.append(f"Auswahl {col.choice}")
    if col.type == "autonumber":
        notes.append(f"Format {_autonumber(col.format)}")
    if col.type == "formula":
        notes.append(f"Formel, Ergebnis {col.result}")
    return f"        {TYPE_NAMES[col.type]} {col.schema} {_comment(', '.join(notes))}"


def entity_block(table: Table, defs: Definitions) -> str:
    """One entity: the key, the primary name column, the lookups of the table (foreign keys), then its columns in definition order."""
    lines = [f"    {table.schema} {{",
             f"        guid {table.schema}id PK {_comment('Tabelle ' + table.display)}",
             f"        string {table.primary.schema} {_comment(table.primary.display + ', Primärspalte')}"]
    for rel in defs.lookups_of(table.schema):
        notes = [rel.lookup.display, f"Nachschlagefeld auf {rel.referenced}"] + (["Pflicht"] if rel.lookup.required else [])
        lines.append(f"        guid {rel.lookup.logical} FK {_comment(', '.join(notes))}")
    lines += [column_line(c) for c in table.columns]
    lines.append("    }")
    return "\n".join(lines)


def relationship_line(rel: Relationship) -> str:
    """Parent ||--o{ child, labelled with the display name of the lookup; an optional lookup makes the parent side |o (zero or one)."""
    parent = "||" if rel.lookup.required else "|o"
    return f"    {rel.referenced} {parent}--o{{ {rel.referencing} : {_comment(rel.lookup.display)}"


def _row(*cells: str) -> str:
    return "| " + " | ".join(cells) + " |"


def render(defs: Definitions, option_prefix: int = 58000) -> str:
    diagram = ["erDiagram", *[entity_block(t, defs) for t in defs.tables], *[relationship_line(r) for r in defs.relationships]]
    tables = [_row("Tabelle", "Anzeigename", "Mehrzahl", "Primärspalte", "Prüfprotokoll (Audit)", "Notizen"), _row(*["---"] * 6)]
    tables += [_row(f"`{t.schema}`", t.display, t.plural, f"`{t.primary.schema}`", "ja" if t.audit else "nein", "ja" if t.notes else "nein")
               for t in defs.tables]
    rels = [_row("Beziehung", "Eltern (1)", "Kind (n)", "Nachschlagefeld", "Pflicht", "Beim Löschen des Elternsatzes"), _row(*["---"] * 6)]
    rels += [_row(f"`{r.schema}`", f"`{r.referenced}`", f"`{r.referencing}`", f"`{r.lookup.logical}` ({r.lookup.display})",
                  "ja" if r.lookup.required else "nein", DELETE_TEXT[r.delete]) for r in defs.relationships]
    choices = [_row("Auswahlfeld", "Anzeigename", "Werte in Reihenfolge"), _row(*["---"] * 3)]
    choices += [_row(f"`{c.schema}`", c.display, "; ".join(c.values)) for c in defs.choices]
    base = option_prefix * 10000
    parts = [
        "# Datenmodell des KI-Registers (ERD)",
        "Dieses Dokument wird aus `provision/definitions/*.toml` erzeugt (`uv run python tools/erd.py`) und nicht von Hand geändert; "
        "`tests/unit/test_erd.py` schlägt fehl, wenn es vom Stand der Definitionen abweicht. Alle Daten sind fiktiv (Nordstern Gruppe), "
        "das Register ist keine Rechtsberatung.",
        "## Diagramm",
        "```mermaid\n" + "\n".join(diagram) + "\n```",
        "Lesehilfe: Die Entitäten tragen die Schemanamen der Tabellen, der Kommentar der Schlüsselzeile nennt den deutschen Anzeigenamen. "
        "`PK` ist der Primärschlüssel, `FK` ein Nachschlagefeld auf die Elterntabelle; die Beschriftung einer Linie ist der Anzeigename "
        "des Nachschlagefelds. `||` bedeutet genau ein Elternsatz (Pflichtfeld), `|o` null oder ein Elternsatz (optional), `o{` null bis "
        "viele Kindsätze. Spaltentypen: `string`, `memo` (langer Text), `int`, `bool`, `date`, `datetime`, `url`, `email`, `choice` und "
        "`choices` (Auswahl und Mehrfachauswahl eines globalen Auswahlfelds), `autonumber` (Zähler mit Präfix) und `formula` (berechnete "
        "Spalte).",
        "Alle Tabellen sind benutzer- oder teameigen (`ownerid`); so bilden Unternehmenseinheiten Zugriffsgrenzen. Systemspalten wie "
        "Eigentümer, Erstellt am und Status sind nicht eingezeichnet.",
        "## Tabellen",
        "\n".join(tables),
        "## Beziehungen",
        "\n".join(rels),
        "Dataverse erlaubt je untergeordneter Tabelle nur eine übergeordnete (kaskadierende) Beziehung. Deshalb ist Schulung die "
        "übergeordnete Tabelle der Schulungsteilnahme (Kaskade), und die Beziehung zum Mitarbeiter verhindert das Löschen (ADR-002).",
        "## Auswahlfelder",
        f"Die Werte eines Auswahlfelds sind `{base}` plus die Position in der Reihenfolge der Definition (Optionswertpräfix {option_prefix}).",
        "\n".join(choices),
    ]
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="docs/erd.md aus provision/definitions erzeugen")
    parser.add_argument("--check", action="store_true", help="nichts schreiben; Exit-Code 1, wenn die Datei veraltet ist")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Zieldatei (Standard: docs/erd.md)")
    args = parser.parse_args(argv)
    settings = load_settings("dev", ROOT)
    text = render(load_definitions(settings.definitions_dir), settings.option_prefix)
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current != text:
            print(f"{args.output} ist veraltet: uv run python tools/erd.py", file=sys.stderr)
            return 1
        print(f"{args.output} entspricht den Definitionen")
        return 0
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"{args.output} geschrieben ({len(text.splitlines())} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
