"""Rules over the content of the seed CSVs: references, choices, formats, coherence of the register and text quality.

How the CSVs become Dataverse rows (payload, date shift, upsert) is tested in test_seed_mechanics.py."""

import re
from datetime import date
from pathlib import Path

from kiregister import seed
from kiregister.definitions import load_definitions

ROOT = Path(__file__).resolve().parents[2]
DEFS = load_definitions(ROOT / "provision" / "definitions")
DATA = seed.read_seed(ROOT / "data" / "seed")
TODAY = seed.SEED_ANCHOR.isoformat()
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# --- references, choices, formats -----------------------------------------------------------------------------------------------


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


TRIAGE_REGISTRATION = ("registriert das System als Anbieter vor der Inbetriebnahme selbst (Art. 49 Abs. 1); "
                       "als Betreiber ist es keine Behörde, daher keine zusätzliche Registrierung nach Art. 49 Abs. 3.")


def test_eu_database_flag_means_registration_under_art_49_is_required():
    flagged = {s["key"] for s in DATA["nst_kisystem"] if s["nst_eudatenbank"] == "1"}
    assert flagged == {"TALENTFILTER", "ZAHLUNGSAUSFALL", "TRIAGE"}
    texts = {s["key"]: s["nst_internebewertung"] for s in DATA["nst_kisystem"]}
    assert "Art. 49 Abs. 5" in texts["NETZLAST"] and "EUDAMED" in texts["RADIOLOGIE"]


def test_triage_is_an_in_house_build_that_the_klinikum_registers_itself_as_provider():
    system = next(s for s in DATA["nst_kisystem"] if s["key"] == "TRIAGE")
    assessment = next(r for r in DATA["nst_risikobewertung"] if r["key"] == "RB-TRIAGE-2026")
    measure = next(m for m in DATA["nst_massnahme"] if m["key"] == "M36")
    assert system["nst_rolle"] == "Anbieter" and system["nst_eudatenbank"] == "1"
    assert f"Das Klinikum {TRIAGE_REGISTRATION}" in system["nst_internebewertung"]
    assert f"das Klinikum {TRIAGE_REGISTRATION}" in assessment["nst_begruendung"]
    assert measure["nst_name"] == "Registrierung des Systems in der EU-Datenbank vornehmen"
    assert measure["nst_beschreibung"] == f"Das Klinikum {TRIAGE_REGISTRATION}" and measure["nst_artikelbezug"] == "Art. 49 Abs. 1"
    for text in (system["nst_internebewertung"], assessment["nst_begruendung"], measure["nst_name"], measure["nst_beschreibung"]):
        assert "keine eigene Registrierung" not in text and "durch den Anbieter" not in text and "Registrierung des Anbieters" not in text


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


def test_no_date_falls_on_a_weekend(date_columns):
    for t, rows in DATA.items():
        for col in date_columns(t):
            for r in rows:
                if r.get(col):
                    assert date.fromisoformat(r[col][:10]).weekday() < 5, (t, col, r["key"])


# --- text quality ---------------------------------------------------------------------------------------------------------------

ABBREVIATION = re.compile(r"\b(?:Nr|Art|Abs|lit|UAbs|ggf|bzw|Dr|Prof|ErwG)\.|\bz\.\s?B\.")


def sentences(text: str) -> int:
    """Sentences of a text: ".", "!" or "?" before a capital letter or the end; an abbreviation such as "Art." or "z. B." does not end one."""
    return len(re.findall(r"[.!?](?=\s+[A-ZÄÖÜ]|\s*$)", ABBREVIATION.sub(lambda m: m.group(0).replace(".", ""), text)))


def test_sentence_counter():
    assert sentences("Hoch nach Anhang III Nr. 4 lit. a, siehe Art. 50 Abs. 4 UAbs. 2 (ErwG 18).") == 1
    assert sentences("Erster Satz. Zweiter Satz.") == 2
    assert sentences("Ein Satz am 2027-12-02 und ohne Punkt") == 0
    assert sentences("Das gilt z. B. für Daten und z.B. für Texte.") == 1
    assert sentences("Das gilt z. B. Daten. Und mehr.") == 2


def test_descriptions_have_two_sentences_and_internal_assessments_one():
    for s in DATA["nst_kisystem"]:
        assert sentences(s["nst_beschreibung"]) == 2, (s["key"], s["nst_beschreibung"])
        assert sentences(s["nst_internebewertung"].rstrip(".") + ".") == 1, (s["key"], s["nst_internebewertung"])
        assert s["nst_internebewertung"].endswith("."), s["key"]


def test_chatbot_pm_says_that_the_notice_is_missing_and_tracked_as_a_measure():
    system = next(s for s in DATA["nst_kisystem"] if s["key"] == "CHATBOT-PM")
    assessment = next(r for r in DATA["nst_risikobewertung"] if r["key"] == "RB-CHATBOT-PM-2025")
    measure = next(m for m in DATA["nst_massnahme"] if m["key"] == "M03")
    assert "Hinweis im Chatfenster fehlt noch und wird als Maßnahme verfolgt" in system["nst_internebewertung"]
    assert "dokumentiert" not in system["nst_internebewertung"] and "dokumentiert" not in assessment["nst_begruendung"]
    assert "noch fehlt" in assessment["nst_begruendung"] and "als Maßnahme" in assessment["nst_begruendung"]
    assert measure["nst_KISystem"] == "CHATBOT-PM" and measure["nst_status"] == "Offen"


FREE_TEXT = {"nst_kisystem": ("nst_zweck", "nst_beschreibung", "nst_internebewertung"), "nst_risikobewertung": ("nst_begruendung",),
             "nst_massnahme": ("nst_name", "nst_beschreibung"), "nst_anwendungsfall": ("nst_beschreibung", "nst_zweck", "nst_betroffene", "nst_entscheidung"),
             "nst_schulung": ("nst_inhalt", "nst_zielgruppe")}
MASCULINE_GENERICS = re.compile(r"\b(Kunden|Patienten|Bewerber|Bewerberauswahl|Nutzer|Ärzte|Hausärzte|Mitarbeiter|Teilnehmer|Projektleiter|Subunternehmer|Ableser|"
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


# Application dates of the Digital Omnibus (Regulation (EU) 2026/1744, published 2026-07-24): fixed by law, they do not follow the date shift.
OMNIBUS_PUBLISHED = "2026-07-24"
OMNIBUS_DATES = ("2027-12-02", "2028-08-02")


def test_assessments_dated_before_the_omnibus_do_not_quote_its_application_dates():
    for r in DATA["nst_risikobewertung"]:
        if r["nst_datum"] < OMNIBUS_PUBLISHED:
            assert not any(d in r["nst_begruendung"] for d in OMNIBUS_DATES), r["key"]
    assert any(d in r["nst_begruendung"] for r in DATA["nst_risikobewertung"] if r["nst_datum"] >= OMNIBUS_PUBLISHED for d in OMNIBUS_DATES)


def test_free_text_holds_no_year_that_the_date_shift_would_leave_behind():
    for t, columns in FREE_TEXT.items():
        for r in DATA[t]:
            for c in columns:
                text = r[c]
                for legal in OMNIBUS_DATES:
                    text = text.replace(legal, "")
                assert not re.search(r"\b(?:19|20)\d\d\b", text), (t, r["key"], c)


def test_assessment_names_are_base_texts_without_a_date():
    """`seed.payload` appends the month of the shifted `nst_datum`, so the CSV name carries none."""
    for r in DATA["nst_risikobewertung"]:
        assert r["nst_name"].startswith("Risikobewertung ") and not re.search(r"\b(?:19|20)\d\d(?:-\d\d)?\b", r["nst_name"]), r["key"]


def test_data_is_fictional():
    text = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "data" / "seed").glob("*.csv"))
    emails = {w for w in text.replace(",", " ").split() if "@" in w}
    assert emails and all(e.endswith("@nordstern.example") for e in emails)
    assert "Microsoft" not in "".join(s["nst_anbieter"] for s in DATA["nst_kisystem"])
    lowered = text.lower()
    for real in ("orbis", "dedalus", "siemens", "philips", "cerner", "agfa", "bosch", "telekom", "sap se"):
        assert real not in lowered, real
