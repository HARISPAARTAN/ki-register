"""How the seed CSVs become Dataverse rows: ids, payload conversion, the date shift and the upsert against a mocked environment.

Rules over the content of the CSVs are tested in test_seed_data.py."""

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
API = "https://org.crm4.dynamics.com/api/data/v9.2/"


def test_record_ids_are_stable_and_distinct():
    a = seed.record_id("nst_kisystem", "TALENTFILTER")
    assert a == seed.record_id("nst_kisystem", "TALENTFILTER") and a != seed.record_id("nst_kisystem", "COPILOT-PM")
    assert len(a) == 36


# --- payload: conversions, errors, formats --------------------------------------------------------------------------------------


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


# --- relative dates -------------------------------------------------------------------------------------------------------------


def shifted(target: date, date_columns) -> dict[str, list[dict]]:
    days = seed.delta_days(target)
    return {t: [{**r, **{c: seed.shift_date(r[c], days) for c in date_columns(t) if r.get(c)}} for r in rows] for t, rows in DATA.items()}


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


def test_payload_is_unchanged_at_the_anchor_and_every_date_moves_by_seven_days_a_week_later(date_columns):
    for t, rows in DATA.items():
        for r in rows:
            base = seed.payload(t, r, DEFS, 58000, {})
            assert seed.payload(t, r, DEFS, 58000, {}, None, seed.delta_days(ANCHOR)) == base
            later = seed.payload(t, r, DEFS, 58000, {}, None, seed.delta_days(ANCHOR + timedelta(days=7)))
            for c in date_columns(t):
                if c in base:
                    assert date.fromisoformat(later[c][:10]) - date.fromisoformat(base[c][:10]) == timedelta(days=7), (t, r["key"], c)
            moved = set(date_columns(t)) | ({DEFS.table(t).primary.schema} if t in seed.DATED_NAME_COLUMN else set())  # the name follows its date
            assert {k: v for k, v in later.items() if k not in moved} == {k: v for k, v in base.items() if k not in moved}


def test_the_assessment_name_ends_with_the_month_of_the_shifted_date():
    """Anchor and anchor + 7 days: the suffix is the shifted `nst_datum[:7]`, one space after the CSV name; no other table gets a suffix."""
    names = {}
    for days in (0, 7):
        shift = seed.delta_days(ANCHOR + timedelta(days=days))
        for r in DATA["nst_risikobewertung"]:
            p = seed.payload("nst_risikobewertung", r, DEFS, 58000, {}, None, shift)
            assert p["nst_datum"] == seed.shift_date(r["nst_datum"], shift), r["key"]
            assert p["nst_name"] == f"{r['nst_name']} {p['nst_datum'][:7]}", r["key"]
            names[days, r["key"]] = p["nst_name"]
    changed = [r["key"] for r in DATA["nst_risikobewertung"] if names[7, r["key"]] != names[0, r["key"]]]
    assert changed  # the name really follows the date: RB-DIENSTPLAN-2026 moves from 2026-02-23 to 2026-03-02
    assert all(seed.payload(t, r, DEFS, 58000, {})["nst_name"] == r["nst_name"] for t in ("nst_kisystem", "nst_massnahme", "nst_schulung") for r in DATA[t])


@pytest.mark.parametrize("offset", [0, 1, 2, 3, 4, 5, 6, 30, 400])
def test_shifted_data_keeps_four_overdue_systems_and_eight_overdue_measures(offset, date_columns):
    target = ANCHOR + timedelta(days=offset)
    data = shifted(target, date_columns)
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


def upsert_body(upserts, table, key):
    return next(json.loads(c.request.content) for c in upserts.calls if c.request.url.path.endswith(seed.record_id(table, key) + ")"))


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
    system = upsert_body(upserts, "nst_kisystem", "TALENTFILTER")
    original = next(r for r in DATA["nst_kisystem"] if r["key"] == "TALENTFILTER")
    assert date.fromisoformat(system["nst_naechstepruefung"]) - date.fromisoformat(original["nst_naechstepruefung"]) == timedelta(days=14)


@respx.mock
def test_load_seed_names_an_assessment_after_its_shifted_date():
    upserts, _ = mock_environment()
    seed.load_seed(DataverseClient(API, Tokens()), load_settings("dev", ROOT), DEFS, ANCHOR + timedelta(days=15))
    body = upsert_body(upserts, "nst_risikobewertung", "RB-DIENSTPLAN-2026")  # 2026-02-23 + 14 days = 2026-03-09
    assert body["nst_datum"] == "2026-03-09" and body["nst_name"] == "Risikobewertung Dienstplan-Optimierung 2026-03"


@respx.mock
def test_load_seed_defaults_to_todays_utc_date():
    upserts, _ = mock_environment()
    seed.load_seed(DataverseClient(API, Tokens()), load_settings("dev", ROOT), DEFS)
    system = upsert_body(upserts, "nst_kisystem", "TALENTFILTER")
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
