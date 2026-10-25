import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from kiregister import seed
from kiregister.client import DataverseClient
from kiregister.config import load_settings
from kiregister.definitions import load_definitions

ROOT = Path(__file__).resolve().parents[2]
DEFS = load_definitions(ROOT / "provision" / "definitions")
DATA = seed.read_seed(ROOT / "data" / "seed")
ANCHOR = seed.SEED_ANCHOR
TODAY = ANCHOR.isoformat()
API = "https://org.crm4.dynamics.com/api/data/v9.2/"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_record_ids_are_stable_and_distinct():
    a = seed.record_id("nst_kisystem", "TALENTFILTER")
    assert a == seed.record_id("nst_kisystem", "TALENTFILTER") and a != seed.record_id("nst_kisystem", "COPILOT-PM")
    assert len(a) == 36


def test_every_lookup_key_resolves():
    keys = {t: {r["key"] for r in rows} for t, rows in DATA.items()}
    for t, rows in DATA.items():
        for rel in DEFS.lookups_of(t):
            for r in rows:
                v = r.get(rel.lookup.schema, "")
                if v:
                    assert v in keys[rel.referenced], (t, rel.lookup.schema, v)
                else:
                    assert not rel.lookup.required, (t, rel.lookup.schema, r["key"])


def test_choice_labels_exist():
    for t, rows in DATA.items():
        table = DEFS.table(t)
        for col in table.columns:
            if col.type not in ("choice", "multichoice"):
                continue
            allowed = set(DEFS.choice(col.choice).values)
            for r in rows:
                for v in filter(None, r.get(col.schema, "").split(";")):
                    assert v in allowed, (t, col.schema, v)


def test_register_contents_match_the_spec():
    systems = DATA["nst_kisystem"]
    assert len(systems) == 20
    by_tier = {}
    for s in systems:
        by_tier.setdefault(s["nst_risikoklasse"], 0)
        by_tier[s["nst_risikoklasse"]] += 1
    assert by_tier["Hoch"] == 5 and by_tier["Unannehmbar (Art. 5)"] == 1 and by_tier["Begrenzt (Transparenzpflicht)"] == 3
    overdue = [s for s in systems if s["nst_status"] == "In Betrieb" and s["nst_naechstepruefung"] < TODAY]
    assert len(overdue) == 4
    assert all(s["nst_risikoklasse"] == r["nst_ergebnis"] for s in systems for r in DATA["nst_risikobewertung"]
               if r["nst_KISystem"] == s["key"] and r["nst_datum"] == max(x["nst_datum"] for x in DATA["nst_risikobewertung"] if x["nst_KISystem"] == s["key"]))
    assert len(DATA["nst_organisation"]) == 3 and len(DATA["nst_mitarbeiter"]) == 21
    assert sum(1 for m in DATA["nst_mitarbeiter"] if m["nst_kiverantwortlich"] == "1") == 3


def test_payload_converts_types_and_binds_lookups_and_owner():
    row = next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER")
    teams = {"PM": "11111111-1111-1111-1111-111111111111", "EN": "2", "KL": "3"}
    p = seed.payload("nst_kisystem", row, DEFS, 58000, teams)
    assert p["nst_name"] == "TalentFilter Bewerbungs-Screening"
    assert p["nst_risikoklasse"] == 580000002  # Hoch
    assert p["nst_Organisation@odata.bind"] == f"/nst_organisations({seed.record_id('nst_organisation', 'PM')})"
    assert p["ownerid@odata.bind"] == "/teams(11111111-1111-1111-1111-111111111111)"
    assert p["nst_transparenzpflicht"] is False and p["nst_inbetriebnahme"].startswith("20")
    assert "key" not in p and "org" not in p


# --- conversions, errors, formats -----------------------------------------------------------------------------------------------


def test_payload_multichoice_is_a_comma_separated_value_string_and_skips_autonumber_and_formula():
    row = next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER")
    p = seed.payload("nst_kisystem", row, DEFS, 58000, {})
    assert p["nst_datenarten"] == "580000000,580000002"  # Personenbezogene Daten, Beschäftigtendaten
    assert "nst_kennung" not in p and "nst_pruefungueberfaellig" not in p and "ownerid@odata.bind" not in p


def test_payload_uses_the_given_entity_set_names_for_binds():
    row = next(r for r in DATA["nst_schulungsteilnahme"] if r["nst_Mitarbeiter"] == "KL-NOWACK")
    sets = {t.schema: t.schema + "x" for t in DEFS.tables}
    p = seed.payload("nst_schulungsteilnahme", row, DEFS, 58000, {}, sets)
    assert p["nst_Mitarbeiter@odata.bind"] == f"/nst_mitarbeiterx({seed.record_id('nst_mitarbeiter', 'KL-NOWACK')})"
    assert p["nst_Schulung@odata.bind"].startswith("/nst_schulungx(")


def talentfilter(**changes):
    return dict(next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER"), **changes)


@pytest.mark.parametrize("changes, match", [
    ({"nst_status": "Gibt es nicht"}, r"nst_kisystem\.nst_status \(Zeile TALENTFILTER\).*Gibt es nicht"),
    ({"nst_datenarten": "Personenbezogene Daten;Unbekannt"}, r"nst_kisystem\.nst_datenarten \(Zeile TALENTFILTER\).*Unbekannt"),
    ({"nst_transparenzpflicht": "true"}, r"nst_kisystem\.nst_transparenzpflicht \(Zeile TALENTFILTER\).*0 oder 1"),
    ({"nst_eudatenbank": " 1"}, r"nst_eudatenbank \(Zeile TALENTFILTER\).*0 oder 1"),
    ({"nst_inbetriebnahme": "03.04.2023"}, r"nst_inbetriebnahme \(Zeile TALENTFILTER\).*YYYY-MM-DD"),
])
def test_payload_errors_name_table_column_and_row_key(changes, match):
    with pytest.raises(seed.SeedError, match=match):
        seed.payload("nst_kisystem", talentfilter(**changes), DEFS, 58000, {})


def test_payload_rejects_a_bad_integer_with_context():
    row = dict(DATA["nst_schulung"][0], nst_dauerminuten="neunzig")
    with pytest.raises(seed.SeedError, match=r"nst_schulung\.nst_dauerminuten \(Zeile SCH-PM-1\)"):
        seed.payload("nst_schulung", row, DEFS, 58000, {})


def test_every_bool_cell_is_0_or_1_and_every_date_cell_is_iso():
    for t, rows in DATA.items():
        for col in DEFS.table(t).columns:
            for r in rows:
                v = r.get(col.schema)
                if v is None:
                    continue
                if col.type == "bool":
                    assert v in ("0", "1"), (t, col.schema, r["key"], v)
                elif col.type == "date" and v:
                    assert ISO_DATE.match(v), (t, col.schema, r["key"], v)
                    date.fromisoformat(v)
                elif col.type == "datetime" and v:
                    assert ISO_DATETIME.match(v), (t, col.schema, r["key"], v)


def test_keys_are_unique_per_table_and_every_row_has_an_org_for_the_owning_team():
    units = {r["key"] for r in DATA["nst_organisation"]}
    for t, rows in DATA.items():
        keys = [r["key"] for r in rows]
        assert len(keys) == len(set(keys)), t
        assert all(r["org"] in units for r in rows), t


def test_organisation_rows_name_the_business_units_of_security_toml():
    assert {r["nst_businessunitname"] for r in DATA["nst_organisation"]} == set(DEFS.security.business_units)
    assert {r["key"] for r in DATA["nst_organisation"]} == {"PM", "EN", "KL"}


def test_order_lists_every_referenced_table_before_the_tables_that_reference_it():
    assert set(seed.ORDER) == {t.schema for t in DEFS.tables} == set(seed.FILES)
    for rel in DEFS.relationships:
        assert seed.ORDER.index(rel.referenced) < seed.ORDER.index(rel.referencing), rel.schema


# --- coherence of the register --------------------------------------------------------------------------------------------------


def test_child_rows_belong_to_the_same_organisation_as_their_parent():
    org = {t: {r["key"]: r["org"] for r in rows} for t, rows in DATA.items()}
    for t, rows in DATA.items():
        for rel in DEFS.lookups_of(t):
            if rel.referenced == "nst_organisation":
                assert all(r[rel.lookup.schema] == r["org"] for r in rows), t
    for r in DATA["nst_risikobewertung"] + DATA["nst_massnahme"]:
        assert org["nst_kisystem"][r["nst_KISystem"]] == r["org"], r["key"]
    for r in DATA["nst_schulungsteilnahme"]:
        assert org["nst_schulung"][r["nst_Schulung"]] == r["org"] == org["nst_mitarbeiter"][r["nst_Mitarbeiter"]], r["key"]
    for s in DATA["nst_kisystem"]:
        assert org["nst_mitarbeiter"][s["nst_Verantwortlicher"]] == s["org"], s["key"]


def test_seed_counts_and_distribution():
    assert {t: len(rows) for t, rows in DATA.items()} == {
        "nst_organisation": 3, "nst_mitarbeiter": 21, "nst_kisystem": 20, "nst_anwendungsfall": 7,
        "nst_risikobewertung": 27, "nst_massnahme": 42, "nst_schulung": 9, "nst_schulungsteilnahme": 51}
    assert {o: sum(1 for m in DATA["nst_mitarbeiter"] if m["org"] == o) for o in ("PM", "EN", "KL")} == {"PM": 7, "EN": 7, "KL": 7}


def test_every_system_has_an_assessment_and_high_risk_systems_have_two():
    for s in DATA["nst_kisystem"]:
        rows = [r for r in DATA["nst_risikobewertung"] if r["nst_KISystem"] == s["key"]]
        assert rows, s["key"]
        if s["nst_risikoklasse"] == "Hoch":
            assert len(rows) >= 2, s["key"]
        newest = max(rows, key=lambda r: r["nst_datum"])
        assert newest["nst_gueltigbis"] == s["nst_naechstepruefung"], s["key"]
        assert newest["nst_datum"] == s["nst_letztepruefung"], s["key"]
        chain = sorted(rows, key=lambda r: r["nst_datum"])
        assert len({r["nst_datum"] for r in rows}) == len(rows), s["key"]
        for older, newer in zip(chain, chain[1:], strict=False):
            assert older["nst_gueltigbis"] == newer["nst_datum"], (s["key"], older["key"])


def test_assessments_are_dated_after_the_regulation_entered_into_force():
    assert all(r["nst_datum"] >= "2024-08-01" for r in DATA["nst_risikobewertung"])


def test_assessment_flags_are_consistent_with_the_result():
    for r in DATA["nst_risikobewertung"]:
        tier = r["nst_ergebnis"]
        assert (r["nst_art5verbotenepraxis"] == "1") == (tier == "Unannehmbar (Art. 5)"), r["key"]
        if tier == "Begrenzt (Transparenzpflicht)":
            assert r["nst_art50transparenz"] == "1", r["key"]
        if tier == "Hoch" and r["nst_anhang3treffer"] != "1":
            assert "Anhang I" in r["nst_begruendung"], r["key"]  # high risk via the product route
        if r["nst_anhang3treffer"] == "1":
            assert r["nst_anhang3kategorie"] != "Keine", r["key"]
    for s in DATA["nst_kisystem"]:
        assert (s["nst_transparenzpflicht"] == "1") == (s["nst_risikoklasse"] == "Begrenzt (Transparenzpflicht)"), s["key"]


def test_eu_database_flag_means_registration_under_art_49_is_required():
    flagged = {s["key"] for s in DATA["nst_kisystem"] if s["nst_eudatenbank"] == "1"}
    assert flagged == {"TALENTFILTER", "ZAHLUNGSAUSFALL", "TRIAGE"}
    texts = {s["key"]: s["nst_internebewertung"] for s in DATA["nst_kisystem"]}
    assert "Art. 49 Abs. 3" in texts["TRIAGE"] and "keine Behörde" in texts["TRIAGE"]
    assert "Art. 49 Abs. 5" in texts["NETZLAST"] and "EUDAMED" in texts["RADIOLOGIE"]


def test_every_assessment_reasoning_names_an_article_or_an_annex_point():
    for r in DATA["nst_risikobewertung"]:
        assert re.search(r"Art\. \d+|Anhang [IVX]+", r["nst_begruendung"]), r["key"]


def test_system_statuses():
    status = {s["key"]: s["nst_status"] for s in DATA["nst_kisystem"]}
    assert status["EMOTION-BAUSTELLE"] == "Abgelehnt" and status["TRIAGE"] == "In Bewertung"
    assert sum(1 for v in status.values() if v == "Freigegeben") == 1
    assert sum(1 for v in status.values() if v == "In Betrieb") == 17
    others = [s for s in DATA["nst_kisystem"] if s["nst_naechstepruefung"] and s["nst_naechstepruefung"] >= TODAY]
    assert all(s["nst_naechstepruefung"].startswith("2027") for s in others if s["nst_status"] == "In Betrieb")


def test_measures_have_eight_overdue_and_the_rest_later():
    rows = DATA["nst_massnahme"]
    past = [r for r in rows if r["nst_faelligam"] < TODAY]
    assert len(past) == 8 and all(r["nst_status"] in ("Offen", "In Arbeit") for r in past)
    assert all(r["nst_faelligam"] > TODAY for r in rows if r not in past)
    assert {r["nst_typ"] for r in rows} == set(DEFS.choice("nst_massnahme_typ").values)


def test_trainings_participations_and_use_cases():
    assert all(s["nst_dauerminuten"] == "90" for s in DATA["nst_schulung"])
    assert {s["nst_name"] for s in DATA["nst_schulung"]} == {"KI-Kompetenz Grundlagen", "Hochrisiko-Systeme im Betrieb", "Transparenz und Kennzeichnung"}
    pairs = [(t["nst_Schulung"], t["nst_Mitarbeiter"]) for t in DATA["nst_schulungsteilnahme"]]
    assert len(pairs) == len(set(pairs))
    status = [t["nst_status"] for t in DATA["nst_schulungsteilnahme"]]
    assert status.count("Abgeschlossen") > len(status) / 2 and 1 <= status.count("Überfällig") <= 5 and status.count("Geplant") > 0
    assert all(bool(t["nst_abgeschlossenam"]) == (t["nst_status"] == "Abgeschlossen") for t in DATA["nst_schulungsteilnahme"])
    cases = DATA["nst_anwendungsfall"]
    assert sum(1 for c in cases if c["nst_status"] in ("Eingereicht", "In Prüfung")) == 5
    assert sum(1 for c in cases if c["nst_status"] in ("Genehmigt", "Abgelehnt")) == 2
    assert all(c["nst_gewuenschterstart"][:7] in ("2026-11", "2026-12") for c in cases)


def test_no_date_falls_on_a_weekend():
    for t, rows in DATA.items():
        for col in DEFS.table(t).columns:
            if col.type in ("date", "datetime"):
                for r in rows:
                    if r.get(col.schema):
                        assert date.fromisoformat(r[col.schema][:10]).weekday() < 5, (t, col.schema, r["key"])


# --- text quality ---------------------------------------------------------------------------------------------------------------

ABBREVIATION = re.compile(r"\b(Nr|Art|Abs|lit|UAbs|ggf|bzw|Dr|Prof|ErwG)\.")


def sentences(text: str) -> int:
    return len(re.findall(r"[.!?](?=\s+[A-ZÄÖÜ]|\s*$)", ABBREVIATION.sub(lambda m: m.group(1), text)))


def test_sentence_counter():
    assert sentences("Hoch nach Anhang III Nr. 4 lit. a, siehe Art. 50 Abs. 4 UAbs. 2 (ErwG 18).") == 1
    assert sentences("Erster Satz. Zweiter Satz.") == 2
    assert sentences("Ein Satz am 2027-12-02 und ohne Punkt") == 0


def test_descriptions_have_two_sentences_and_internal_assessments_one():
    for s in DATA["nst_kisystem"]:
        assert sentences(s["nst_beschreibung"]) == 2, (s["key"], s["nst_beschreibung"])
        assert sentences(s["nst_internebewertung"].rstrip(".") + ".") == 1, (s["key"], s["nst_internebewertung"])
        assert s["nst_internebewertung"].endswith("."), s["key"]


FREE_TEXT = {"nst_kisystem": ("nst_zweck", "nst_beschreibung", "nst_internebewertung"), "nst_risikobewertung": ("nst_begruendung",),
             "nst_massnahme": ("nst_name", "nst_beschreibung"), "nst_anwendungsfall": ("nst_beschreibung", "nst_zweck", "nst_betroffene", "nst_entscheidung"),
             "nst_schulung": ("nst_inhalt", "nst_zielgruppe")}
MASCULINE_GENERICS = re.compile(r"\b(Kunden|Patienten|Bewerber|Nutzer|Ärzte|Hausärzte|Mitarbeiter|Teilnehmer|Projektleiter|Subunternehmer|Ableser|"
                                r"Interessenten|Bauherren|Fachärzte)\b|Patientinnen und Patienten|Ärztin oder Arzt")


def test_one_gender_convention_in_the_free_text():
    for t, columns in FREE_TEXT.items():
        for r in DATA[t]:
            for c in columns:
                assert not MASCULINE_GENERICS.search(r[c]), (t, r["key"], c, MASCULINE_GENERICS.search(r[c]).group(0))


def test_legal_wording_art_50_art_4_and_the_digital_omnibus():
    blob = "".join(r[c] for t, cols in FREE_TEXT.items() for r in DATA[t] for c in cols)
    assert "Schulungspflicht" not in blob and "Art. 50 Abs. 2 verpflichtet den Betreiber" not in blob
    chatbots = [s for s in DATA["nst_kisystem"] if s["nst_risikoklasse"] == "Begrenzt (Transparenzpflicht)"]
    assert len(chatbots) == 3 and all(s["nst_rolle"] == "Betreiber" for s in chatbots)
    assert all("Der Anbieter muss nach Art. 50 Abs. 1 sicherstellen" in s["nst_internebewertung"] for s in chatbots)
    angebot = next(s for s in DATA["nst_kisystem"] if s["key"] == "ANGEBOTSTEXT")["nst_internebewertung"]
    assert "Art. 50 Abs. 2" in angebot and "Art. 50 Abs. 4 UAbs. 2" in angebot and "freiwillig" in angebot
    art4 = {r["key"] for r in DATA["nst_massnahme"] if r["nst_artikelbezug"] == "Art. 4"}
    assert art4 == {"M04", "M15", "M30", "M41"} and all(r["nst_typ"] == "Schulung" for r in DATA["nst_massnahme"] if r["key"] in art4)
    triage = [r for r in DATA["nst_massnahme"] if r["nst_KISystem"] == "TRIAGE" and "Art. 27" in r["nst_artikelbezug"]]
    assert len(triage) == 1


def test_data_is_fictional():
    text = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "data" / "seed").glob("*.csv"))
    emails = {w for w in text.replace(",", " ").split() if "@" in w}
    assert emails and all(e.endswith("@nordstern.example") for e in emails)
    assert "Microsoft" not in "".join(s["nst_anbieter"] for s in DATA["nst_kisystem"])
    lowered = text.lower()
    for real in ("orbis", "dedalus", "siemens", "philips", "cerner", "agfa", "bosch", "telekom", "sap se"):
        assert real not in lowered, real


# --- relative dates -------------------------------------------------------------------------------------------------------------


def shifted(target: date) -> dict[str, list[dict]]:
    days = seed.delta_days(target)
    out = {}
    for t, rows in DATA.items():
        date_cols = [c.schema for c in DEFS.table(t).columns if c.type in ("date", "datetime")]
        out[t] = [{**r, **{c: seed.shift_date(r[c], days) for c in date_cols if r.get(c)}} for r in rows]
    return out


def test_delta_days_is_whole_weeks_rounded_down():
    assert seed.delta_days(ANCHOR) == 0 and seed.delta_days(ANCHOR + timedelta(days=6)) == 0
    assert seed.delta_days(ANCHOR + timedelta(days=7)) == 7 and seed.delta_days(ANCHOR + timedelta(days=400)) == 399
    assert seed.delta_days(ANCHOR - timedelta(days=1)) == -7


def test_shift_date_handles_dates_and_datetimes_and_rejects_other_formats():
    assert seed.shift_date("2026-10-25", 7) == "2026-11-01" and seed.shift_date("2026-10-25", 0) == "2026-10-25"
    assert seed.shift_date("2026-10-14T09:30:00Z", 7) == "2026-10-21T09:30:00Z"
    for bad in ("2026-1-5", "25.10.2026", "2026-10-25 10:00", "2026-10-25T09:30:00"):
        with pytest.raises(ValueError):
            seed.shift_date(bad, 7)


def test_payload_is_unchanged_at_the_anchor_and_every_date_moves_by_seven_days_a_week_later():
    for t, rows in DATA.items():
        date_cols = [c.schema for c in DEFS.table(t).columns if c.type in ("date", "datetime")]
        for r in rows:
            base = seed.payload(t, r, DEFS, 58000, {})
            assert seed.payload(t, r, DEFS, 58000, {}, None, seed.delta_days(ANCHOR)) == base
            later = seed.payload(t, r, DEFS, 58000, {}, None, seed.delta_days(ANCHOR + timedelta(days=7)))
            for c in date_cols:
                if c in base:
                    assert date.fromisoformat(later[c][:10]) - date.fromisoformat(base[c][:10]) == timedelta(days=7), (t, r["key"], c)
            assert {k: v for k, v in later.items() if k not in date_cols} == {k: v for k, v in base.items() if k not in date_cols}


@pytest.mark.parametrize("offset", [0, 1, 2, 3, 4, 5, 6, 30, 400])
def test_shifted_data_keeps_four_overdue_systems_and_eight_overdue_measures(offset):
    target = ANCHOR + timedelta(days=offset)
    data = shifted(target)
    systems = [s for s in data["nst_kisystem"] if s["nst_status"] == "In Betrieb"]
    overdue = {s["key"] for s in systems if s["nst_naechstepruefung"] < (target - timedelta(days=1)).isoformat()}
    assert overdue == {"TALENTFILTER", "CHATBOT-PM", "ZAEHLERSTAND", "DIKTAT-LLM"}
    assert all(s["nst_naechstepruefung"] >= target.isoformat() for s in systems if s["key"] not in overdue)
    measures = [m for m in data["nst_massnahme"] if m["nst_status"] in ("Offen", "In Arbeit")]
    late = [m for m in measures if m["nst_faelligam"] < (target - timedelta(days=1)).isoformat()]
    assert len(late) == 8 and all(m["nst_faelligam"] >= target.isoformat() for m in measures if m not in late)


def test_the_new_option_reaches_the_cli_and_load_seed(monkeypatch):
    from typer.testing import CliRunner

    from kiregister import cli
    seen = {}

    def fake_load_seed(client, settings, defs, day=None):
        seen["day"] = day
        return {"nst_organisation": 3}

    monkeypatch.setattr(cli, "_client", lambda env: (object(), object(), object()))
    monkeypatch.setattr(seed, "load_seed", fake_load_seed)
    runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})
    assert runner.invoke(cli.app, ["seed", "--env", "dev", "--stichtag", "2026-12-24"]).exit_code == 0
    assert seen["day"] == date(2026, 12, 24)
    assert runner.invoke(cli.app, ["seed", "--env", "dev", "--stichtag", "morgen"]).exit_code != 0


# --- upsert against a mocked environment ----------------------------------------------------------------------------------------


class Tokens:
    def token(self):
        return "t"


@respx.mock
def test_entity_set_is_read_once_per_table_and_client():
    api = "https://cache-test.crm4.dynamics.com/api/data/v9.2/"
    route = respx.get(api + "EntityDefinitions(LogicalName='nst_kisystem')").mock(return_value=httpx.Response(200, json={"EntitySetName": "nst_kisystems"}))
    client = DataverseClient(api, Tokens())
    assert seed.entity_set(client, "nst_kisystem") == seed.entity_set(client, "nst_kisystem") == "nst_kisystems"
    assert route.call_count == 1
    other = "https://cache-test-2.crm4.dynamics.com/api/data/v9.2/"
    respx.get(other + "EntityDefinitions(LogicalName='nst_kisystem')").mock(return_value=httpx.Response(200, json={"EntitySetName": "other_sets"}))
    assert seed.entity_set(DataverseClient(other, Tokens()), "nst_kisystem") == "other_sets"


def mock_environment(units=None, teams_exist=True):
    units = DEFS.security.business_units if units is None else units
    bus = [{"businessunitid": "root", "name": "Nordstern", "_parentbusinessunitid_value": None}] + [
        {"businessunitid": f"bu-{n}", "name": n, "_parentbusinessunitid_value": "root"} for n in units]
    respx.get(API + "businessunits").respond(200, json={"value": bus})

    def teams(request):
        flt = request.url.params["$filter"]
        assert "name eq 'Nordstern" in flt and " Datenbesitz'" in flt and "_businessunitid_value eq bu-Nordstern" in flt, flt
        return httpx.Response(200, json={"value": [{"teamid": "team-" + flt.split("_businessunitid_value eq ")[-1]}] if teams_exist else []})

    respx.get(API + "teams").mock(side_effect=teams)
    respx.get(url__regex=r".*EntityDefinitions\(LogicalName='(\w+)'\)").mock(
        side_effect=lambda r: httpx.Response(200, json={"EntitySetName": r.url.path.split("'")[1] + "s"}))
    return respx.patch(url__startswith=API + "nst_").mock(return_value=httpx.Response(204)), respx.post(url__startswith=API).mock(return_value=httpx.Response(204))


@respx.mock
def test_load_seed_upserts_every_row_parents_first_and_provisions_nothing():
    upserts, posts = mock_environment()
    counts = seed.load_seed(DataverseClient(API, Tokens(), solution="NordsternKIRegister"), load_settings("dev", ROOT), DEFS, ANCHOR)
    assert counts == {t: len(rows) for t, rows in DATA.items()}
    assert upserts.call_count == sum(len(rows) for rows in DATA.values())
    assert posts.call_count == 0  # no business unit, team or role is created by the seed
    first = upserts.calls[0].request
    assert first.url.path.endswith(f"nst_organisations({seed.record_id('nst_organisation', 'PM')})")
    assert "MSCRM.SolutionUniqueName" not in first.headers and "If-Match" not in first.headers and "If-None-Match" not in first.headers
    assert json.loads(first.content)["ownerid@odata.bind"] == "/teams(team-bu-Nordstern Projektmanagement)"
    seen = set()
    for call in upserts.calls:
        body = json.loads(call.request.content)
        assert "ownerid@odata.bind" in body
        for key, value in body.items():
            if key.endswith("@odata.bind") and key != "ownerid@odata.bind":
                assert re.search(r"\((.+)\)", value).group(1) in seen, (call.request.url.path, key)  # the parent was upserted earlier
        seen.add(re.search(r"\((.+)\)$", call.request.url.path).group(1))


@respx.mock
def test_load_seed_moves_the_dates_to_the_reference_date():
    upserts, _ = mock_environment()
    seed.load_seed(DataverseClient(API, Tokens()), load_settings("dev", ROOT), DEFS, ANCHOR + timedelta(days=15))
    system = next(json.loads(c.request.content) for c in upserts.calls if c.request.url.path.endswith(seed.record_id("nst_kisystem", "TALENTFILTER") + ")"))
    original = next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER")
    assert date.fromisoformat(system["nst_naechstepruefung"]) - date.fromisoformat(original["nst_naechstepruefung"]) == timedelta(days=14)


@respx.mock
def test_load_seed_defaults_to_todays_utc_date():
    upserts, _ = mock_environment()
    seed.load_seed(DataverseClient(API, Tokens()), load_settings("dev", ROOT), DEFS)
    system = next(json.loads(c.request.content) for c in upserts.calls if c.request.url.path.endswith(seed.record_id("nst_kisystem", "TALENTFILTER") + ")"))
    original = next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER")
    expected = seed.delta_days(datetime.now(UTC).date())
    assert (date.fromisoformat(system["nst_naechstepruefung"]) - date.fromisoformat(original["nst_naechstepruefung"])).days == expected


@respx.mock
def test_load_seed_stops_when_a_business_unit_is_missing():
    upserts, _ = mock_environment(units=DEFS.security.business_units[:2])
    with pytest.raises(RuntimeError, match=r"Unternehmenseinheit Nordstern Klinikum fehlt: zuerst `kiregister apply --only security` ausführen"):
        seed.load_seed(DataverseClient(API, Tokens()), load_settings("dev", ROOT), DEFS, ANCHOR)
    assert upserts.call_count == 0


@respx.mock
def test_load_seed_stops_when_an_owner_team_is_missing():
    upserts, _ = mock_environment(teams_exist=False)
    with pytest.raises(RuntimeError, match=r"Team Nordstern Energie Datenbesitz fehlt: zuerst `kiregister apply --only security` ausführen"):
        seed.load_seed(DataverseClient(API, Tokens()), load_settings("dev", ROOT), DEFS, ANCHOR)
    assert upserts.call_count == 0
