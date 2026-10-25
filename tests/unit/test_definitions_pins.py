"""Pins the decisions in the TOML definitions so that a silent edit fails a test."""

import shutil
from pathlib import Path

import pytest

from kiregister.definitions import load_definitions

DEFS = Path(__file__).resolve().parents[2] / "provision" / "definitions"


def test_relationship_delete_behaviour_is_pinned():
    d = load_definitions(DEFS)
    expected = {
        "nst_kisystem_risikobewertung": "Restrict",
        "nst_kisystem_massnahme": "Restrict",
        "nst_schulung_teilnahme": "Cascade",
        "nst_mitarbeiter_teilnahme": "Restrict",
    }
    for r in d.relationships:
        assert r.delete == expected.get(r.schema, "RemoveLink"), r.schema


def test_audit_and_notes_only_where_specified():
    d = load_definitions(DEFS)
    wanted = {"nst_kisystem", "nst_risikobewertung", "nst_anwendungsfall"}
    assert {t.schema for t in d.tables if t.audit} == wanted
    assert {t.schema for t in d.tables if t.notes} == wanted


def test_choice_value_lists_are_pinned():
    d = load_definitions(DEFS)
    assert d.choice("nst_risikoklasse").values == ["Nicht bewertet", "Unannehmbar (Art. 5)", "Hoch", "Begrenzt (Transparenzpflicht)", "Minimal"]
    assert d.choice("nst_status_kisystem").values == ["Idee", "In Bewertung", "Freigegeben", "In Betrieb", "Ausgesetzt", "Eingestellt", "Abgelehnt"]


def test_required_flags_and_memo_lengths():
    d = load_definitions(DEFS)

    def column(table, name):
        return next(c for c in d.table(table).columns if c.schema == name)

    assert column("nst_kisystem", "nst_status").required
    assert column("nst_anwendungsfall", "nst_status").required
    assert column("nst_risikobewertung", "nst_ergebnis").required
    assert column("nst_risikobewertung", "nst_datum").required
    assert not column("nst_kisystem", "nst_risikoklasse").required
    assert column("nst_kisystem", "nst_beschreibung").length == 4000
    assert column("nst_kisystem", "nst_zweck").length == 2000
    assert column("nst_kisystem", "nst_internebewertung").length == 4000
    assert column("nst_anwendungsfall", "nst_entscheidung").length == 2000
    assert column("nst_risikobewertung", "nst_begruendung").length == 4000
    assert column("nst_massnahme", "nst_beschreibung").length == 2000
    assert column("nst_schulung", "nst_inhalt").length == 2000


def test_security_roles():
    d = load_definitions(DEFS)
    roles = {r.name: r for r in d.security.roles}
    assert roles["nst KI-Governance"].extra == {"prvReadUser": "Global", "prvReadTeam": "Global", "prvReadBusinessUnit": "Global"}
    assert roles["nst Leser"].tables["nst_organisation"] == {"read": "Local"}
    assert roles["nst Fachbereich"].tables["nst_organisation"] == {"read": "Local", "appendto": "Local"}
    assert roles["nst Fachbereich"].extra == {}


def test_role_with_unknown_table_is_rejected(tmp_path):
    shutil.copytree(DEFS, tmp_path / "defs")
    sec = tmp_path / "defs" / "security.toml"
    text = sec.read_text(encoding="utf-8")
    assert 'nst_massnahme = { read = "Local" }' in text
    sec.write_text(text.replace('nst_massnahme = { read = "Local" }', 'nst_massnahmee = { read = "Local" }', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="nst_massnahmee"):
        load_definitions(tmp_path / "defs")


def test_unknown_names_raise_key_error_with_the_name():
    d = load_definitions(DEFS)
    with pytest.raises(KeyError, match="nst_gibtesnicht"):
        d.table("nst_gibtesnicht")
    with pytest.raises(KeyError, match="nst_gibtesnicht"):
        d.choice("nst_gibtesnicht")
    with pytest.raises(KeyError, match="nst_gibtesnicht"):
        d.relationship_for("nst_kisystem", "nst_gibtesnicht")


def test_kisystem_form_has_the_five_tabs_of_the_spec():
    d = load_definitions(DEFS)
    form = next(f for f in d.app.forms if f.table == "nst_kisystem")
    assert [t.name for t in form.tabs] == ["Allgemein", "Einstufung", "Daten und Betroffene", "Verlauf", "Intern"]
    assert [v.name for v in d.app.views if v.table == "nst_anwendungsfall"] == ["Offene Anträge"]  # no "Meine Anträge" in M1


def test_hochrisiko_view_shows_tier_hoch_only():
    from kiregister import builders
    d = load_definitions(DEFS)
    view = next(v for v in d.app.views if v.name == "Hochrisiko-Systeme")
    assert [(f.column, f.op, f.values) for f in view.filter] == [("nst_risikoklasse", "eq", ["Hoch"])]
    xml = builders.fetch_xml(view, d, 58000)
    assert 'attribute="nst_risikoklasse" operator="eq" value="580000002"' in xml and "580000001" not in xml


def test_the_app_is_open_to_the_three_user_roles_and_never_to_the_owner_role():
    from kiregister.security import OWNER_ROLE
    d = load_definitions(DEFS)
    assert d.app.roles == ["nst KI-Governance", "nst Fachbereich", "nst Leser"]
    assert OWNER_ROLE not in d.app.roles  # held by the member-less owner teams only, never by a user


def test_the_solution_version_is_1_1_0_0_after_milestone_1():
    """Spec 9: raised per milestone (1.1.0.0 after M1, 1.2.0.0 after M2, 1.3.0.0 after M3); `apply` sets it in the solution."""
    from kiregister.config import load_settings
    assert load_settings("dev", Path(__file__).resolve().parents[2]).solution_version == "1.1.0.0"
