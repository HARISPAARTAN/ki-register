import json
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
TODAY = "2026-10-25"
API = "https://org.crm4.dynamics.com/api/data/v9.2/"


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
    overdue = [s for s in systems if s["nst_status"] == "In Betrieb" and s["nst_naechstepruefung"] < "2026-10-25"]
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


def test_keys_are_unique_per_table_and_every_row_has_an_org_for_the_owning_team():
    for t, rows in DATA.items():
        keys = [r["key"] for r in rows]
        assert len(keys) == len(set(keys)), t
        assert all(r["org"] in seed.ORG_TO_BU for r in rows), t


def test_organisation_rows_name_the_business_units_of_security_toml():
    assert set(seed.ORG_TO_BU.values()) == set(DEFS.security.business_units)
    for r in DATA["nst_organisation"]:
        assert r["nst_businessunitname"] == seed.ORG_TO_BU[r["key"]]


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
        "nst_risikobewertung": 27, "nst_massnahme": 41, "nst_schulung": 9, "nst_schulungsteilnahme": 51}
    assert {o: sum(1 for m in DATA["nst_mitarbeiter"] if m["org"] == o) for o in seed.ORG_TO_BU} == {"PM": 7, "EN": 7, "KL": 7}


def test_every_system_has_an_assessment_and_high_risk_systems_have_two():
    for s in DATA["nst_kisystem"]:
        rows = [r for r in DATA["nst_risikobewertung"] if r["nst_KISystem"] == s["key"]]
        assert rows, s["key"]
        if s["nst_risikoklasse"] == "Hoch":
            assert len(rows) >= 2, s["key"]
        newest = max(rows, key=lambda r: r["nst_datum"])
        assert newest["nst_gueltigbis"] == s["nst_naechstepruefung"], s["key"]
        assert newest["nst_datum"] == s["nst_letztepruefung"], s["key"]


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
    assert {s["key"] for s in DATA["nst_kisystem"] if s["nst_eudatenbank"] == "1"} == {"RADIOLOGIE", "TRIAGE"}


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


def test_data_is_fictional():
    text = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "data" / "seed").glob("*.csv"))
    emails = {w for w in text.replace(",", " ").split() if "@" in w}
    assert emails and all(e.endswith("@nordstern.example") for e in emails)
    assert "Microsoft" not in "".join(s["nst_anbieter"] for s in DATA["nst_kisystem"])


class Tokens:
    def token(self):
        return "t"


@respx.mock
def test_entity_set_is_read_once_per_table(monkeypatch):
    monkeypatch.setattr(seed, "_entity_sets", {})
    route = respx.get(API + "EntityDefinitions(LogicalName='nst_kisystem')").mock(return_value=httpx.Response(200, json={"EntitySetName": "nst_kisystems"}))
    client = DataverseClient(API, Tokens())
    assert seed.entity_set(client, "nst_kisystem") == seed.entity_set(client, "nst_kisystem") == "nst_kisystems"
    assert route.call_count == 1


@respx.mock
def test_load_seed_upserts_every_row_with_its_deterministic_id_and_no_solution_header(monkeypatch):
    monkeypatch.setattr(seed, "_entity_sets", {})
    monkeypatch.setattr("kiregister.security.time.sleep", lambda s: None)
    settings = load_settings("dev", ROOT)
    bus = [{"businessunitid": "root", "name": "Nordstern", "_parentbusinessunitid_value": None}] + [
        {"businessunitid": f"bu-{i}", "name": n, "_parentbusinessunitid_value": "root"} for i, n in enumerate(DEFS.security.business_units)]
    respx.get(API + "businessunits").respond(200, json={"value": bus})
    respx.get(API + "WhoAmI").respond(200, json={"UserId": "app-user"})
    respx.get(API + "teams").mock(side_effect=lambda r: httpx.Response(200, json={"value": [{"teamid": "team-" + r.url.params["$filter"].split()[-1]}]}))
    respx.get(API + "roles").respond(200, json={"value": [{"roleid": "owner-role"}]})
    respx.get(url__regex=r".*/teams\(.*\)/teamroles_association").respond(200, json={"value": [{"roleid": "owner-role"}]})
    respx.get(url__regex=r".*EntityDefinitions\(LogicalName='(\w+)'\)").mock(
        side_effect=lambda r: httpx.Response(200, json={"EntitySetName": r.url.path.split("'")[1] + "s"}))
    upserts = respx.patch(url__startswith=API + "nst_").mock(return_value=httpx.Response(204))
    counts = seed.load_seed(DataverseClient(API, Tokens(), solution="NordsternKIRegister"), settings, DEFS)
    assert counts == {t: len(rows) for t, rows in DATA.items()}
    assert upserts.call_count == sum(counts.values()) == 179
    first = upserts.calls[0].request
    assert first.url.path.endswith(f"nst_organisations({seed.record_id('nst_organisation', 'PM')})")
    assert "MSCRM.SolutionUniqueName" not in first.headers and "If-Match" not in first.headers and "If-None-Match" not in first.headers
    assert json.loads(first.content)["ownerid@odata.bind"] == "/teams(team-bu-0)"
    assert all("ownerid@odata.bind" in json.loads(c.request.content) for c in upserts.calls)


@pytest.mark.parametrize("bad", ["Gibt es nicht"])
def test_payload_rejects_an_unknown_choice_label(bad):
    row = dict(next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER"), nst_status=bad)
    with pytest.raises(ValueError):
        seed.payload("nst_kisystem", row, DEFS, 58000, {})


def test_teardown_deletes_participations_before_employees_and_systems_before_organisations():
    order = seed.teardown_order()
    assert order[0] == "nst_schulungsteilnahme"
    assert order.index("nst_schulungsteilnahme") < order.index("nst_mitarbeiter") < order.index("nst_organisation")
    for rel in DEFS.relationships:
        assert order.index(rel.referencing) < order.index(rel.referenced), rel.schema
