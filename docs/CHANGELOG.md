# Änderungsprotokoll

Die Version des Repositorys steht in `pyproject.toml` (0.1.0), die Version der Lösung `NordsternKIRegister` in `config.toml` (1.1.0.0 nach Meilenstein 1). Git-Tags `v0.1.0` bis `v0.4.0` bilden die Meilensteine ab; einen Tag setzt der Mensch, er löst `deploy-test.yml` aus.

## v0.1.0 (2026-10-25) Meilenstein 1 Registerkern

Das Register ist in Nordstern Dev provisioniert, mit dem fiktiven Register gefüllt und geprüft; Nordstern Test erhält die Lösung als verwaltete Lösung. Alle Daten sind erfunden, das Register ist keine Rechtsberatung.

1. **Projektgerüst und Definitionen (Aufgabe 1).** uv-verwaltetes Python 3.13, Ruff, pytest. TOML-Definitionen unter `provision/definitions/`: 10 Auswahlfelder, 8 Tabellen, 13 Beziehungen, 4 Rollen mit Spaltensicherheitsprofil, App mit Ansichten, Formularen, Diagrammen und Dashboard. Builder für die Nutzlasten der Web API, FormXML, FetchXML, Diagramm- und Sitemap-XML mit Beschriftungen in Deutsch (1031) und Englisch (1033), abgesichert durch Snapshot-Tests.
2. **Web-API-Client und Metadaten-Funktionen (Aufgabe 2).** `DataverseClient` mit OData-Kopfzeilen, Lösungskopfzeile bei jedem Anlegen, Wiederholung bei 429 und 503 (Lesezugriffe auch bei 502 und 504) nach `Retry-After`, höchstens fünfmal, und Fehlern mit Status, Code, Meldung und Komponentenname. Anmeldung mit MSAL (Client-Credentials) und über die Azure CLI. Idempotente Funktionen für Herausgeber, Lösung, Auswahlfelder, Tabellen, Spalten (Formelspalte mit Rückfall), Beziehungen und Veröffentlichung.
3. **Bootstrap, Kommandozeile und erste Provisionierung gegen Dev (Aufgabe 3).** `kiregister bootstrap` und `apply --only metadata`, das Skript `tools/setup_app_registration.sh`, Integrationstests (Marker `dataverse`). Die Umgebung erzwang vier Abweichungen vom Entwurf, festgehalten in ADR-002: `UTCToday()` in der Formelspalte, kein Menüetikett an Beziehungen, kein `Prefer: return=representation`, nur eine kaskadierende Elternbeziehung je Tabelle.
4. **Sicherheit (Aufgabe 4).** `apply --only security`: drei Unternehmenseinheiten als Kinder der Wurzel, die Rollen `nst KI-Governance`, `nst Fachbereich` und `nst Leser` mit Privilegien und Zugriffsstufen, das Spaltensicherheitsprofil `nst KI-Governance Felder` für die interne Bewertung eines KI-Systems.
5. **App (Aufgabe 5).** `apply --only app`: 13 Ansichten (acht benannte und fünf erzeugte Standardansichten), acht Hauptformulare (das des KI-Systems mit fünf Registerkarten), drei Diagramme, das Dashboard „KI-Register Übersicht“, die Sitemap mit vier Bereichen und die modellgesteuerte App `nst_kiregister` mit Prüfung durch `ValidateApp`.
6. **Seed und Prüfung (Aufgabe 6).** Das fiktive Register: drei Gesellschaften, 21 Mitarbeitende, 20 KI-Systeme (5 Hoch, 1 Unannehmbar, 3 Begrenzt, 11 Minimal), 27 Risikobewertungen, 42 Maßnahmen, 9 Schulungen, 51 Teilnahmen, 7 Anwendungsfälle. Feste GUIDs, mitgliederlose Besitzerteams `<Einheit> Datenbesitz` mit der Rolle `nst Datenbesitz`, Datumswerte relativ zum Stichtag (`--stichtag`), Rechtsstand Verordnung (EU) 2024/1689 in der Fassung der Verordnung (EU) 2026/1744. `kiregister seed` und `kiregister verify` (Exit-Code 1 bei Abweichung).
7. **ALM (Aufgabe 7).** Die Workflows `ci.yml`, `export-solution.yml`, `import-dev.yml` und `deploy-test.yml`; die Lösungsquelle `solution/src` (erster Export der Version 1.0.0.0, Tabellenkomponenten der App über den Import); `verify` im Modus nur für Lösungskomponenten für Test; ADR-003 zu den Fristen der Entwicklerumgebungen und zur Entscheidung gegen Pipelines und Git-Integration.
8. **Dokumentation und Abschluss (Aufgabe 8).** ERD mit Erzeuger (`tools/erd.py`, `docs/erd.md`), ADR-001 (Dataverse statt SharePoint-Listen), ADR-002 aktualisiert, ADR-003 ergänzt, README auf Deutsch und Englisch, Wiederaufbau-Anleitung als Skelett, dieses Protokoll.
   - Die drei Benutzerrollen dürfen die App öffnen (`appmoduleroles_association`, im Export enthalten).
   - Die Lösungsversion 1.1.0.0 steht in `config.toml`; `apply` setzt sie in der Lösung.
   - `verify` prüft, dass die Tabellen Komponenten der App sind, auch für Test.
   - Nachbesserungen am ALM nach der Prüfung von Aufgabe 7: alle Aktionen von Dritten auf Commit-SHAs festgelegt, `dependabot.yml`, Geheimnisse des Integrationsjobs nur im Testschritt, `persist-credentials: false` im Export.

### Bekannte Grenzen

- Das Auditing der Umgebung ist in Dev ausgeschaltet (Portalschritt, ADR-002); die Tabellen tragen das Prüfprotokoll bereits.
- Rollen und Spaltensicherheitsprofil sind noch keinem Benutzer zugewiesen und es gibt keinen Demo-Benutzer; das Öffnen der App mit nur einer `nst`-Rolle und die Maskierung der gesicherten Spalte sind nicht gezeigt.
- Die Reihenfolge für einen Wiederaufbau (Bootstrap, Import, `apply --only security`, `seed`, `verify`) ist abgeleitet und nicht auf einer frischen Umgebung erprobt.
- Test enthält nur die verwaltete Lösung, keine Unternehmenseinheiten, Besitzerteams oder Seed-Daten.
- Dev und Test werden ab 2026-12-15 ausgesetzt und ab 2027-01-15 gelöscht, wenn sie nicht zu verwalteten Umgebungen werden (ADR-003). Screenshots und Video vor dem 2026-12-15 aufnehmen.
