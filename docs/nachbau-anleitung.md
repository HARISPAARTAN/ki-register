# Wiederaufbau-Anleitung (Skelett aus Meilenstein 1)

Diese Anleitung ist für den späteren Nachbau des Registers von Hand im Maker-Portal gedacht (als Übung) und für den Wiederaufbau in einer neuen Umgebung. Sie ist ein **Skelett**: Die Reihenfolge und die Zuordnung zu den Definitionsdateien stehen fest. Die Portalpfade sind aus der Oberfläche abgeleitet, die Bezeichnungen folgen der deutschsprachigen Oberfläche und können abweichen; maßgeblich sind die Definitionsdateien unter `provision/definitions/`. Nichts davon wurde bisher auf einer frischen Umgebung durchgespielt. Meilenstein 4 vervollständigt die Anleitung nach dem ersten Nachbau; die Meilensteine 2 bis 4 hängen ihre Abschnitte unten an.

Alle Namen, Personen und Daten sind erfunden; das Register ist keine Rechtsberatung.

## Frist

Nordstern Dev und Nordstern Test werden ab **2026-12-15** ausgesetzt und ab **2027-01-15** gelöscht, wenn sie nicht zu verwalteten Umgebungen werden (ADR-003). Screenshots und Video **vor dem 2026-12-15** aufnehmen (Liste in der README). Für spätere Demos dient eine Standard-Testumgebung mit 30 Tagen; sie wird in der Reihenfolge von Teil A aufgebaut.

## Teil A: Eine neue Umgebung aus dem Repository aufbauen

Diese Reihenfolge ist aus dem Entwurf und den Entscheidungen in ADR-002 und ADR-003 **abgeleitet und noch nicht auf einer frischen Umgebung durchgespielt**. Sie setzt voraus, dass der Lösungsquelltext (`solution/src`) den Stand der Definitionen enthält.

Voraussetzungen: eine Umgebung mit Dataverse-Datenbank (Region Europa, Währung EUR), `az login` mit einem Konto, das Anwendungsbenutzer anlegen darf, die App-Registrierung `ki-register-automation` (`bash tools/setup_app_registration.sh`) und eine `.env` mit `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` und der URL der neuen Umgebung. Für den Import über GitHub Actions muss das Geheimnis `DATAVERSE_URL_DEV` auf die neue Umgebung zeigen.

| Schritt | Befehl oder Weg | Wirkung |
|---|---|---|
| 1 | `uv run --env-file .env kiregister bootstrap --env dev` | legt den Anwendungsbenutzer des Dienstprinzipals mit der Rolle System Administrator an |
| 2 | `gh workflow run import-dev.yml` (Actions, „Lösung nach Dev importieren“) oder Portal-Import eines Archivs, das aus `solution/src` gepackt wurde (`pac solution pack --zipfile NordsternKIRegister.zip --folder solution/src --packagetype Unmanaged`, auf dem Rechner der Eigentümerin) | bringt Herausgeber, Lösung, Auswahlfelder, Tabellen, Spalten, Beziehungen, Rollen, Spaltensicherheitsprofil, Ansichten, Formulare, Diagramme, Dashboard, Sitemap und die App samt Tabellenkomponenten und Rollen |
| 3 | `uv run --env-file .env kiregister apply --env dev --only security` | legt Unternehmenseinheiten und Besitzerteams an (nicht Teil der Lösung) und prüft Rollen und Profil |
| 4 | `uv run --env-file .env kiregister seed --env dev` | lädt das fiktive Register |
| 5 | `uv run --env-file .env kiregister verify --env dev` | prüft alles; Exit-Code 1 bei Abweichung |

Wichtig:

- **Kein volles `apply` vor dem Import.** `apply` ohne `--only` ist der Weg der Code-first-Entwicklung (so ist Dev entstanden). Neben einem Import würde es voraussichtlich Ansichten und Formulare doppelt anlegen, weil deren IDs je Umgebung verschieden sind.
- **Der Import vor `verify`.** `AddAppComponents` kann die Tabellen nicht zu App-Komponenten machen (ADR-002); das leistet der Lösungsimport, und `verify` verlangt es.
- **Hat die Umgebung Änderungen, die noch nicht im Repository stehen,** läuft vorher `export-solution.yml`: `import-dev.yml` überschreibt mit `force-overwrite`.
- Nach dem Import, vor den Benutzerzuweisungen, stehen noch die Portalschritte aus Teil B, Schritte 7 und 15 an (Rollen und Profil den Benutzern zuweisen, Auditing der Umgebung einschalten).

## Teil B: Von Hand im Maker-Portal

Reihenfolge, Portalpfad und Definitionsdatei auf einen Blick:

| Schritt | Was | Portalpfad (Kurzform) | Definitionsdatei |
|---|---|---|---|
| 1 | Herausgeber und Lösung | make.powerapps.com, Lösungen, Neue Lösung | `config.toml` |
| 2 | Auswahlfelder | Lösung, Neu, Mehr, Auswahl | `choices.toml` |
| 3 | Tabellen und Spalten | Lösung, Neu, Tabelle; Tabelle, Spalten | `tables.toml` |
| 4 | Beziehungen | Tabelle, Beziehungen, Neue Beziehung | `relationships.toml` |
| 5 | Unternehmenseinheiten und Besitzerteams | Admin Center, Umgebung, Einstellungen, Benutzer + Berechtigungen | `security.toml` (`business_units`) |
| 6 | Sicherheitsrollen | Admin Center, Sicherheitsrollen | `security.toml` (`role`) |
| 7 | Spaltensicherheitsprofil und Zuweisung | Admin Center, Spaltensicherheitsprofile | `security.toml` (`column_security`) |
| 8 | Ansichten | Tabelle, Ansichten | `app.toml` (`view`) |
| 9 | Formulare | Tabelle, Formulare | `app.toml` (`form`) |
| 10 | Diagramme | Tabelle, Diagramme | `app.toml` (`chart`) |
| 11 | Dashboard | Lösung, Neu, Dashboard | `app.toml` (`dashboard`) |
| 12 | App, Sitemap und Rollen der App | Lösung, Neu, App, Modellgesteuerte App | `app.toml` (`app`, `area`, `roles`) |
| 13 | Seed-Import | Tabelle, Daten importieren, oder `kiregister seed` | `data/seed/*.csv` |
| 14 | Export | Lösung, Lösung exportieren, oder `export-solution.yml` | `solution/src` |
| 15 | Auditing der Umgebung und Prüfung | Admin Center, Audit und Protokolle; `kiregister verify` | `tables.toml` (`audit`) |

Alles, was in die Lösung gehört, wird **in der Lösung** angelegt (Lösung öffnen, Neu) oder ihr danach mit „Vorhandene hinzufügen“ zugefügt; sonst fehlt es im Export. Die Lösung als „Bevorzugte Lösung“ festzulegen, spart das.

### Schritt 1: Herausgeber und Lösung

Portal: make.powerapps.com, Umgebung wählen, Lösungen, Neue Lösung, Herausgeber: Neuer Herausgeber. Datei: `config.toml`, Abschnitt `[solution]`.

- Herausgeber: Anzeigename `Nordstern Gruppe`, Name `nordstern`, Präfix `nst`, Präfix des Auswahlwerts `58000`.
- Lösung: Anzeigename `Nordstern KI-Register`, Name `NordsternKIRegister`, Version `1.1.0.0` (Stand nach Meilenstein 1; je Meilenstein anheben: 1.2.0.0 nach M2, 1.3.0.0 nach M3).

### Schritt 2: Auswahlfelder

Portal: Lösung öffnen, Neu, Mehr, Auswahl. Datei: `provision/definitions/choices.toml` (zehn Auswahlfelder).

- Name = `schema` (zum Beispiel `nst_risikoklasse`), Anzeigename = `display`, die Einträge in genau der Reihenfolge von `values`.
- Das Portal vergibt die Werte aufsteigend ab dem Präfix des Herausgebers (`580000000`, `580000001`, ...). `kiregister seed` rechnet mit `58000 * 10000 + Position`; stimmt die Reihenfolge nicht, passen die Werte nicht. Nach dem Anlegen eines Auswahlfelds den ersten und den letzten Wert ansehen.
- `nst_datenart` wird später als Mehrfachauswahl verwendet.

### Schritt 3: Tabellen und Spalten

Portal: Lösung, Neu, Tabelle, Tabelle (Eigenschaften); danach in der Tabelle Spalten, Neue Spalte. Datei: `provision/definitions/tables.toml` (acht Tabellen). Diagramm und Listen: [docs/erd.md](erd.md).

Je Tabelle: Anzeigename `display`, Mehrzahl `plural`, Name = `schema`, primäre Spalte `primary` (Name `nst_name`, Länge 200). Erweiterte Optionen: Besitz „Benutzer oder Team“ (Standardtabelle), für KI-System, Anwendungsfall und Risikobewertung zusätzlich „Notizen (einschließlich Anlagen) aktivieren“ und „Änderungen an den Daten überwachen“ (`audit` und `notes` in der Datei).

Je Spalte aus `column`: Name = `schema`, Anzeigename = `display`. Der Typ folgt `type`:

| `type` | Spalte im Portal |
|---|---|
| `string` | Text (einzeilig), maximale Länge `length` |
| `memo` | Text (mehrzeilig), maximale Länge `length` |
| `int` | Ganze Zahl |
| `bool` | Ja/Nein |
| `date` | Datum und Uhrzeit, Format „Nur Datum“ |
| `datetime` | Datum und Uhrzeit |
| `url` | Text mit Format URL |
| `email` | Text mit Format E-Mail |
| `choice` | Auswahl, vorhandene globale Auswahl `choice` |
| `multichoice` | Auswahl mit Mehrfachauswahl, globale Auswahl `choice` |
| `autonumber` | Autonummer mit dem Format aus `format`, zum Beispiel `KIS-{SEQNUM:4}` |
| `formula` | Formel mit dem Ergebnistyp `result` |

`required = true` heißt „Geschäftlich erforderlich“, `secured = true` „Spaltensicherheit aktivieren“ (erweiterte Optionen der Spalte; nur `nst_internebewertung`). Die Formelspalte `nst_pruefungueberfaellig` (KI-System) verwendet `UTCToday()` statt `Today()` (ADR-002); der Formeleditor zeigt Anzeigenamen statt der Schemanamen aus der Datei. Die Nachschlagefelder entstehen erst in Schritt 4.

### Schritt 4: Beziehungen

Portal: Tabelle (die Tabelle auf der „Viele“-Seite), Beziehungen, Neue Beziehung, Eins-zu-viele; alternativ in der untergeordneten Tabelle eine Spalte vom Typ Nachschlagen anlegen. Datei: `provision/definitions/relationships.toml` (13 Beziehungen).

- `referenced` ist die Primärtabelle (Eltern), `referencing` die verwandte Tabelle mit der Nachschlagespalte. Nachschlagespalte: Name = `lookup.schema` (zum Beispiel `nst_Organisation`; der logische Name ist die Kleinschreibung), Anzeigename = `lookup.display`, `required = true` heißt erforderlich. Beziehungsname = `schema`.
- Löschverhalten `delete`: `RemoveLink` = Referenziell (Verknüpfung entfernen); `Restrict` = Referenziell, Löschen einschränken; `Cascade` = Übergeordnet (kaskadierend).
- Dataverse erlaubt je untergeordneter Tabelle nur **eine** kaskadierende Elternbeziehung: Schulung ist die Elterntabelle der Schulungsteilnahme (`Cascade`), die Beziehung zum Mitarbeiter ist `Restrict` (ADR-002). Das Menü der Beziehung zeigt den Sammlungsnamen der Tabelle; ein eigenes Etikett wird nicht vergeben (ADR-002).

### Schritt 5: Unternehmenseinheiten und Besitzerteams

Portal: Power Platform Admin Center (admin.powerplatform.microsoft.com), Umgebungen, Umgebung, Einstellungen, Benutzer + Berechtigungen, Unternehmenseinheiten, Neu. Datei: `provision/definitions/security.toml`, Schlüssel `business_units`. Unternehmenseinheiten und Teams gehören **nicht** zur Lösung und werden in jeder Umgebung neu angelegt (ADR-003).

- Drei Einheiten als Kinder der Wurzel: `Nordstern Projektmanagement`, `Nordstern Energie`, `Nordstern Klinikum`.
- Je Einheit ein Besitzerteam: Einstellungen, Benutzer + Berechtigungen, Teams, Team erstellen. Name `<Einheit> Datenbesitz` (zum Beispiel `Nordstern Energie Datenbesitz`), Unternehmenseinheit = die Einheit, Teamtyp Besitzer, **keine Mitglieder**. Die Rolle `nst Datenbesitz` (Schritt 6) wird dem Team zugewiesen. Ein Team ohne Leserecht auf die Tabelle kann keine Datensätze besitzen (Fehler 0x80040299, ADR-002).

### Schritt 6: Sicherheitsrollen

Portal: Admin Center, Einstellungen, Benutzer + Berechtigungen, Sicherheitsrollen, Neue Rolle (Unternehmenseinheit: Wurzel). Datei: `provision/definitions/security.toml`, vier Einträge `role`.

- Je Tabelle in `role.tables` die Rechte Anlegen (`create`), Lesen (`read`), Schreiben (`write`), Löschen (`delete`), Anfügen (`append`), Anfügen an (`appendto`), Zuweisen (`assign`) und Teilen (`share`) mit der Zugriffsstufe: `Basic` = Benutzer, `Local` = Unternehmenseinheit, `Deep` = übergeordnete/untergeordnete Einheit, `Global` = Organisation. `"*"` steht für alle `nst_`-Tabellen. `privileges` sind zusätzliche Rechte (`nst KI-Governance`: Lesen von Benutzer, Team und Unternehmenseinheit, Stufe Organisation).
- Rollen, die im Admin Center angelegt wurden, danach der Lösung zufügen (Lösung, Vorhandene hinzufügen, Sicherheitsrolle), sonst fehlen sie im Export.
- Zum Schluss `nst Datenbesitz` den drei Besitzerteams zuweisen (Schritt 5). Diese Rolle darf nie einem Benutzer gehören; `kiregister verify` meldet jede Zuweisung.

### Schritt 7: Spaltensicherheitsprofil und Zuweisung

Portal: Admin Center, Einstellungen, Benutzer + Berechtigungen, Spaltensicherheitsprofile, Neues Profil. Datei: `provision/definitions/security.toml`, Abschnitt `column_security`.

- Profil `nst KI-Governance Felder`; Spaltenberechtigung für `nst_kisystem` / `nst_internebewertung` mit Lesen, Aktualisieren und Erstellen = Zulässig. Voraussetzung: Die Spalte hat „Spaltensicherheit aktivieren“ (Schritt 3). Das Profil danach der Lösung zufügen.
- **Zuweisung (Portalschritt, auch im Code-Weg):** Governance-Benutzer zum Profil zufügen (Registerkarte Benutzer oder Teams) und die Rollen den Benutzern zuweisen (Admin Center, Benutzer, Rollen verwalten): die Eigentümerin `nst KI-Governance`, ein Demo-Benutzer in der Einheit Energie `nst Fachbereich`. Die Spaltensicherheit gilt nicht für Systemadministratoren: Die Maskierung zeigt nur ein Konto ohne diese Rolle.

### Schritt 8: Ansichten

Portal: Tabelle, Datenerfahrungen, Ansichten, Neue Ansicht. Datei: `provision/definitions/app.toml`, Einträge `view` (acht benannte Ansichten).

- KI-System: `Aktive KI-Systeme` (Standardansicht), `Hochrisiko-Systeme`, `Prüfung überfällig`, `Nach Organisation`, `Mit Transparenzpflicht`. Anwendungsfall: `Offene Anträge` (Standard). Maßnahme: `Offene Maßnahmen` (Standard), `Überfällige Maßnahmen`.
- Spalten (`columns`), Filter (`filter`) und Sortierung (`order`) wie in der Datei; „Prüfung überfällig“ und „Überfällige Maßnahmen“ filtern mit „älter als 1 Tag“ (`olderthan-x-days`).
- Die fünf übrigen Tabellen (Organisation, Mitarbeiter, Risikobewertung, Schulung, Schulungsteilnahme) erhalten je eine Standardansicht „Aktive <Mehrzahl>“ mit bis zu sechs Spalten (Autonummer, Name, Nachschlagefelder, weitere Spalten). Je Tabelle genau **eine** Standardansicht: die Standardansicht der Plattform („Active …“) abwählen (ADR-002).

### Schritt 9: Formulare

Portal: Tabelle, Datenerfahrungen, Formulare, Hauptformular. Datei: `provision/definitions/app.toml`, Einträge `form`.

- KI-System, `KI-System Hauptformular` mit fünf Registerkarten: `Allgemein`, `Einstufung`, `Daten und Betroffene`, `Verlauf` (Unterraster: Risikobewertungen mit der Ansicht „Aktive Risikobewertungen“ über das Nachschlagefeld `nst_kisystem`, Maßnahmen mit „Offene Maßnahmen“), `Intern` (nur die gesicherte Spalte `nst_internebewertung`). Die Spalten je Abschnitt stehen in der Datei.
- Die sieben übrigen Tabellen: je ein Hauptformular „<Anzeigename> Hauptformular“ mit der Registerkarte `Allgemein` (Autonummer, Name und Nachschlagefelder, dann die übrigen Spalten), als Standardformular.

### Schritt 10: Diagramme

Portal: Tabelle, Datenerfahrungen, Diagramme, Neues Diagramm. Datei: `provision/definitions/app.toml`, Einträge `chart` (drei Diagramme, Messgröße: Anzahl der Datensätze).

- `KI-Systeme nach Risikoklasse` (KI-System, Säulen, Kategorie `nst_risikoklasse`, gestapelt nach `nst_organisation`), `Maßnahmen nach Status` (Maßnahme, Kreis, Kategorie `nst_status`), `Anwendungsfälle nach Status` (Anwendungsfall, Säulen, Kategorie `nst_status`).

### Schritt 11: Dashboard

Portal: Lösung, Neu, Dashboard, Dashboard (zweispaltiges Layout). Datei: `provision/definitions/app.toml`, Abschnitt `dashboard`.

- Name `KI-Register Übersicht`, vier Komponenten: Diagramm `KI-Systeme nach Risikoklasse` (Ansicht `Aktive KI-Systeme`), Liste `Prüfung überfällig` (KI-System), Diagramm `Maßnahmen nach Status` (Ansicht `Offene Maßnahmen`), Diagramm `Anwendungsfälle nach Status` (Ansicht `Offene Anträge`).

### Schritt 12: App, Sitemap und Rollen der App

Portal: Lösung, Neu, App, Modellgesteuerte App. Datei: `provision/definitions/app.toml`, Abschnitte `app`, `area` und der Schlüssel `roles`.

- Name `KI-Register`, eindeutiger Name `nst_kiregister`, Beschreibung aus `app.description`.
- Sitemap mit vier Bereichen: `Register` (KI-Systeme, Anwendungsfälle, Risikobewertungen, Maßnahmen), `Schulungen` (Schulungen, Teilnahmen), `Stammdaten` (Organisationen, Mitarbeiter), `Übersicht` (das Dashboard `KI-Register Übersicht`).
- **Tabellen als Komponenten der App:** alle acht Tabellen unter „Vorhandene hinzufügen“ zufügen. Das ist die Portalentsprechung der `AppModuleComponent`-Einträge vom Typ 1 aus dem Lösungsimport (ADR-002); ohne sie meldet die App-Prüfung Warnungen, und `kiregister verify` meldet die fehlenden Komponenten.
- **Rollen der App:** App, Rollen verwalten: `nst KI-Governance`, `nst Fachbereich`, `nst Leser`. Nicht `nst Datenbesitz`.
- Speichern, veröffentlichen, abspielen.

### Schritt 13: Seed-Import

Datei: `data/seed/*.csv` (acht Dateien). Der unterstützte Weg ist `uv run --env-file .env kiregister seed --env dev`: Er ist idempotent, setzt die Besitzerteams, löst die Nachschlagefelder über feste GUIDs auf und verschiebt alle Datumswerte relativ zum Stichtag, damit vier Systeme und acht Maßnahmen überfällig bleiben.

Wer die Daten im Portal üben möchte (Tabelle, Daten importieren, Excel oder CSV): Reihenfolge Organisationen, Mitarbeiter, KI-Systeme, Anwendungsfälle, Risikobewertungen, Maßnahmen, Schulungen, Teilnahmen; Besitzer jeder Zeile ist das Besitzerteam der Gesellschaft. **Entweder-oder:** Nach einem Portalimport würde `kiregister seed` die Datensätze ein zweites Mal anlegen, weil seine GUIDs aus den Schlüsseln der CSV-Dateien gebildet werden. Aufräumen ist von Hand und in dieser Reihenfolge nötig, Kinder zuerst: Teilnahmen, Maßnahmen, Risikobewertungen, Anwendungsfälle, KI-Systeme, Schulungen, Mitarbeiter, Organisationen (ADR-002). Nichts davon ist automatisiert.

### Schritt 14: Export

Portal: Lösung, Version prüfen (Eigenschaften), Lösung exportieren (verwaltet und unverwaltet). Im Repository: `gh workflow run export-solution.yml`, der Workflow öffnet einen Pull Request mit `solution/src`. Der Diff darf nur Dateien unter `solution/src` enthalten, keine Archive, keine Geheimnisse (ADR-003). Manuell entpackt man mit `pac solution unpack --zipfile ... --folder solution/src --packagetype Both`.

### Schritt 15: Auditing der Umgebung und Prüfung

Portal: Admin Center, Umgebungen, Umgebung, Einstellungen, Audit und Protokolle, Audit-Einstellungen (Aufbewahrungsdauer wählen), Globale Audit-Einstellungen, Auditing starten. Der Schalter der Umgebung ist nicht Teil der Lösung und nicht im Code; in Dev stand er am 2026-10-25 auf „aus“ (ADR-002). Erst mit ihm schreiben die Tabellen KI-System, Risikobewertung und Anwendungsfall ein Protokoll. Danach: `uv run --env-file .env kiregister verify --env dev` (bei einem Nachbau ohne Seed mit `KIREGISTER_VERIFY_NO_SEED=1`).

## Meilenstein 2: Erfassung und Genehmigung

Wird in Meilenstein 2 ergänzt: Tabelle Flow-Fehler, die Canvas-App KI-Anmeldung, die Flows „Anwendungsfall genehmigen“ und „Risikoklasse uebernehmen“ mit Verbindungsreferenzen und Einstellungsdatei, die drei Verbindungen (Dataverse, Genehmigungen, Outlook) und die Fehlerdemonstration.

## Meilenstein 3: Agent

Wird in Meilenstein 3 ergänzt: Copilot Studio (Testlizenz), Agent „KI-Lotse“, Wissensquellen, Themen und Anweisungen, Auswertung.

## Meilenstein 4: Governance und Schaufenster

Wird in Meilenstein 4 ergänzt: Governance-Einseiter, Screenshots, Video, der Probelauf dieser Anleitung auf einer frischen Umgebung und die daraus folgenden Korrekturen.
