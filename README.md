# Nordstern KI-Register

Ein Register für KI-Systeme nach EU-KI-Verordnung (EU AI Act), gebaut auf Microsoft Dataverse und vollständig als Code provisioniert: Tabellen, Auswahlfelder, Beziehungen, Sicherheitsrollen, Formulare, Ansichten und die modellgesteuerte App entstehen aus den TOML-Definitionen unter `provision/definitions/`. Alle Daten sind fiktiv (Nordstern Gruppe).

Dieses Projekt ist keine Rechtsberatung.

Rechtsstand der Einstufungen: Verordnung (EU) 2024/1689 in der Fassung der Verordnung (EU) 2026/1744, Stand 2026-10-25; keine Rechtsberatung.

Status: in Arbeit.

## Entscheidungen aus Review 1

- Die Ansicht "Meine Anträge" entfällt in Meilenstein 1: `nst_antragsteller` ist ein Nachschlagefeld auf Mitarbeiter, nicht der angemeldete Benutzer. Die Canvas-App zur Anmeldung in Meilenstein 2 zeigt die eigenen Anträge der Benutzerin oder des Benutzers.
- In Meilenstein 1 hat nur das KI-System ein ausdrückliches Hauptformular; alle übrigen Tabellen verwenden das erzeugte Standardformular.
- Diese Punkte werden in ADR-002 übernommen.

## Inbetriebnahme (Entwicklungsumgebung)

Einmalig, durch die Eigentümerin oder den Eigentümer nach `az login`:

1. `bash tools/setup_app_registration.sh` legt die App-Registrierung `ki-register-automation` an und gibt Mandanten-ID, Client-ID und das Geheimnis (einmalig) aus. Die Werte kommen in die lokale, git-ignorierte `.env` (Vorlage: `.env.example`), nie in einen Chat.
2. `uv run --env-file .env kiregister bootstrap --env dev` (und `--env test`) legt den Anwendungsbenutzer mit der Rolle Systemadministrator an; dafür wird die Azure-CLI-Sitzung der Eigentümerin oder des Eigentümers genutzt.
3. `uv run --env-file .env kiregister apply --env dev --only metadata` legt Auswahlfelder, Tabellen, Spalten und Beziehungen in der Lösung `NordsternKIRegister` an; ein zweiter Lauf legt nichts mehr an.
4. `uv run --env-file .env kiregister apply --env dev --only security` legt Unternehmenseinheiten, je Einheit ein mitgliederloses Besitzerteam `<Einheit> Datenbesitz`, vier Rollen (`nst KI-Governance`, `nst Fachbereich`, `nst Leser` und `nst Datenbesitz`, die nur den Besitzerteams zugewiesen wird) mit ihren Privilegien und das Spaltensicherheitsprofil an (idempotent). Das Zuweisen von Rollen und Profil an Benutzer ist ein Portalschritt.
5. `uv run --env-file .env kiregister apply --env dev --only app` legt Ansichten, Formulare, Diagramme, das Dashboard, die Sitemap und die modellgesteuerte App `nst_kiregister` an (idempotent). Prüfung durch den Eigentümer: https://make.powerapps.com, Apps, KI-Register, Abspielen (vier Bereiche, Ansichten, Formular-Registerkarten).
   Hinweis: `apply` macht die Tabellen nicht zu App-Komponenten (`AddAppComponents` ignoriert die Tabellen-IDs, ADR-002). Das leistet der Lösungsimport: `solution/src` führt die acht Tabellen als `AppModuleComponent` Typ 1, und nach `import-dev.yml` (Dev) oder `deploy-test.yml` (Test) hat die App 34 Komponenten und `ValidateApp` meldet keinen Hinweis mehr (vorher 27 Warnungen). Rückfall in einer Umgebung ohne Import ist der Portalschritt „Vorhandene hinzufügen“; bis dahin zeigt die App die Tabellen nur über die Sitemap, und `ValidateApp` meldet Warnungen (im Abspielen sichtbar), keine Fehler.
6. `uv run --env-file .env kiregister seed --env dev [--stichtag YYYY-MM-DD]` lädt das fiktive Register (drei Gesellschaften, 21 Mitarbeitende, 20 KI-Systeme, 27 Risikobewertungen, 42 Maßnahmen, 9 Schulungen, 51 Teilnahmen, 7 Anwendungsfälle) mit festen GUIDs (uuid5); ein zweiter Lauf innerhalb derselben Woche ändert nichts, denn die Verschiebung um ganze Wochen ändert die Datumswerte einmal pro Woche (der Name einer Risikobewertung endet mit dem Monat ihres verschobenen Datums). Die Schlüssel der CSV-Dateien sind undurchsichtige Bezeichner und werden nie umbenannt (ADR-002). Der Seed legt nichts an: Unternehmenseinheiten und Besitzerteams müssen durch `apply --only security` vorhanden sein, sonst bricht er mit einer Meldung ab. Die Datensätze gehören dem Besitzerteam ihrer Einheit. Alle Datumswerte sind relativ zum Stichtag (Standard: heute, UTC): die CSV-Daten sind auf den 2026-10-25 bezogen und werden um ganze Wochen verschoben, damit „überfällig“ wahr bleibt. Den Seed vor dem Aktivieren der Flows aus Meilenstein 2 laden, sonst lösen die Anlage-Auslöser aus.
   `uv run --env-file .env kiregister verify --env dev` prüft Tabellen, Spalten, Nachschlagefelder, Auswahlfelder, Beziehungen, Rollen, Unternehmenseinheiten, Besitzerteams samt Mitgliedschaft (die Teams müssen leer und die Rolle `nst Datenbesitz` darf keinem Benutzer zugewiesen sein), das Spaltensicherheitsprofil, das App-Modul und die Seed-Anzahlen (Exit-Code 1 bei Abweichung). Mit `KIREGISTER_VERIFY_NO_SEED=1` prüft `verify` nur Lösungskomponenten (Tabellen, Spalten, Nachschlagefelder, Auswahlfelder, Beziehungen, Rollen, Spaltensicherheitsprofil, App-Modul) und lässt Unternehmenseinheiten, Besitzerteams und Seed aus; so prüft `deploy-test.yml` die Testumgebung.
7. Integrationstests: `uv run --env-file .env pytest tests/integration -m dataverse -v`.

## ALM: Export, Import und Deployment

Das Power Platform CLI (`pac`) läuft nur auf GitHub-Runnern, über die Aktionen von `microsoft/powerplatform-actions` (gepinnt auf `v1`), nie auf dem Arbeitsrechner. Die Anmeldung nutzt den Dienstprinzipal und die fünf Repository-Geheimnisse `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, `DATAVERSE_URL_DEV` und `DATAVERSE_URL_TEST`. Begründung, Fristen für Entwicklerumgebungen und Lizenzlage: ADR-003.

| Workflow | Auslöser | Wirkung |
|---|---|---|
| `ci.yml` | Push und Pull Request; der Job `integration` nur von Hand | Ruff und Unit-Tests; von Hand zusätzlich die Integrationstests (`-m dataverse`) gegen Dev |
| `export-solution.yml` | von Hand | exportiert `NordsternKIRegister` aus Dev (unmanaged und managed), entpackt nach `solution/src` und öffnet einen Pull Request, der nur Dateien unter `solution/src` enthalten darf; der Diff wird geprüft und der Pull Request zusammengeführt |
| `import-dev.yml` | von Hand | packt `solution/src` als unmanaged und importiert nach Dev; gebraucht, wenn die Quelle von Hand ergänzt wurde (die Tabellenkomponenten der App), danach folgt ein erneuter Export |
| `deploy-test.yml` | Tag `v*` oder von Hand | packt `solution/src` als managed, importiert nach Test und führt `kiregister verify --env test` mit `KIREGISTER_VERIFY_NO_SEED=1` aus |

Ein Workflow startet über Actions, Workflow, „Run workflow“ oder mit `gh workflow run export-solution.yml`. Test erhält nur die Lösung: Unternehmenseinheiten, Besitzerteams und Seed-Daten sind keine Lösungskomponenten (ADR-003). Eine Umgebung entsteht entweder aus dem Code (`bootstrap`, `apply`, `seed`) oder aus der Lösung (Import; Unternehmenseinheiten, Besitzerteams und Seed kämen dann aus `apply --only security` und `seed`, was nicht erprobt ist). Beide Wege nacheinander sind ebenfalls nicht erprobt und legen voraussichtlich Ansichten und Formulare doppelt an, weil deren IDs je Umgebung verschieden sind.

## Daten

- Die Spalte `nst_eudatenbank` (KI-System) bedeutet: Registrierung in der EU-Datenbank nach Art. 49 ist erforderlich. Sie ist gesetzt für TalentFilter, Zahlungsausfall-Scoring und die Notaufnahme-Triage (Anhang III); nicht gesetzt für die Netzlast-Prognose (Anhang III Nr. 2: nationale Registrierung nach Art. 49 Abs. 5) und die Radiologie-Befundunterstützung (Anhang I, Medizinprodukt: Registrierung des Herstellers in EUDAMED).
- Die Ansicht „Hochrisiko-Systeme“ zeigt nur die Risikoklasse Hoch (5 Systeme); ein verbotenes System (Art. 5) ist kein Hochrisiko-System.
- Die Datumswerte des Seeds sind relativ zum Stichtag (`--stichtag`, siehe Schritt 6).

## Setup (English)

Once, by the owner after `az login`: run `tools/setup_app_registration.sh`, put tenant ID, client ID and secret into the git-ignored `.env`, then `kiregister bootstrap --env dev|test` (creates the application user with System Administrator via the owner's Azure CLI token) and `kiregister apply --env dev --only metadata` (idempotent), then `kiregister apply --env dev --only security` (business units, one member-less owner team per unit, four roles (the fourth, `nst Datenbesitz`, only for the owner teams), column security profile; assigning users is a portal step), then `kiregister apply --env dev --only app` (views, forms, charts, dashboard, site map, the model-driven app), then `kiregister seed --env dev [--stichtag YYYY-MM-DD]` (fictional register with deterministic GUIDs, owned by the owner team of each subsidiary; all dates are relative to the reference date, shifted in whole weeks from the anchor 2026-10-25, so a second run within the same week changes nothing and the dates change once per week; the name of an assessment ends with the month of its shifted date; provisions nothing, run `apply --only security` first; load it before the milestone-2 flows are activated) and `kiregister verify --env dev` (tables, columns, lookups, choices, relationships, roles, business units, owner teams and their membership, app module, seed counts). Integration tests: `pytest tests/integration -m dataverse`.

ALM (English): `pac` runs on GitHub runners only (`microsoft/powerplatform-actions@v1`), never on the owner's machine. `export-solution.yml` (manual) exports the solution unmanaged and managed from Dev, unpacks it to `solution/src` and opens a pull request that may only touch `solution/src`; `import-dev.yml` (manual) packs `solution/src` as unmanaged and imports it into Dev (used to add the app's table components, which `AddAppComponents` cannot add on this environment: ADR-002); `deploy-test.yml` (tag `v*` or manual) packs managed, imports into Test and runs `kiregister verify --env test` with `KIREGISTER_VERIFY_NO_SEED=1`, which checks solution components only because business units, owner teams and seed data are not part of the solution. Why not pipelines or Git integration, and the developer-environment deadlines (2026-11-15, 2026-12-15, 2027-01-15): ADR-003.

Legal state of the classifications: Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744, as of 2026-10-25; not legal advice. The `nst_eudatenbank` column means: registration in the EU database under Art. 49 is required.
