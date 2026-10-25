# ADR-002: Code-first-Provisionierung über die Web API

- Datum: 2026-10-25
- Status: angenommen

## Kontext

Handgeschriebenes Lösungs-XML ist brüchig und schwer zu prüfen; im Portal gebaut und exportiert ist nicht reproduzierbar. Das Register wird deshalb aus TOML-Definitionen (`provision/definitions/`) über die Dataverse Web API provisioniert (idempotent: lesen, dann anlegen oder aktualisieren, nie löschen). Die Quelle der Wahrheit sind die TOML-Dateien; die exportierte Lösungsquelle kommt als Artefakt für Microsoft-Werkzeuge hinzu.

Der erste echte Lauf gegen die Entwicklungsumgebung (Nordstern Dev, Basissprache 1033) hat vier Abweichungen vom Entwurf erzwungen. Sie sind hier festgehalten, damit sie nicht erneut gebaut werden.

## Entscheidung

1. **Formelspalte mit `UTCToday()`.** Die Spalte `nst_pruefungueberfaellig` (KI-System) verwendet `UTCToday()` statt `Today()`. Die Formelspalte wurde akzeptiert; der Ersatz über einen Ansichtsfilter (`olderthan-x-days`) ist nicht nötig.
2. **Kein Menüetikett an Beziehungen.** Die Basissprache der Organisation ist ausschließlich 1033. Ein Etikett mit LCID 1031 am zugehörigen Menü einer Beziehung wird abgelehnt. Das Menüetikett wird weggelassen (`AssociatedMenuConfiguration.Behavior = UseCollectionName`); sichtbar ist der Sammlungsname der Tabelle. Etiketten mit LCID 1031 auf Tabellen und Spalten werden akzeptiert, in einer Umgebung nur mit 1033 aber nicht gespeichert; gespeichert und geprüft wird das englische Etikett (1033).
3. **Kein `Prefer: return=representation`.** Der Header wird bei POST nicht gesendet. Dataverse antwortet mit 204 und dem Header `OData-EntityId`; der Client liest die ID daraus. Alle Aufrufer verwenden den Rückgabewert nur als ID.
4. **`nst_mitarbeiter_teilnahme` ist `Restrict` statt `Cascade`.** Dataverse erlaubt je untergeordneter Tabelle nur eine übergeordnete (kaskadierende) Beziehung; ein zweiter Versuch endet mit Fehler `0x80047007`. **Schulung ist die übergeordnete Tabelle** von Schulungsteilnahme (`Cascade`). Das Löschen eines Mitarbeiters wird dadurch blockiert, solange Teilnahmen bestehen. Das weicht von Entwurf 4.3 (Kaskade für beide Eltern) ab und ist für Schulungsnachweise ohnehin die sicherere Wahl.

   Regel: **Ein Teilnahme-Datensatz hat genau eine übergeordnete Beziehung (Schulung). Seeds und Abbau löschen Teilnahmen vor Mitarbeitern.** Das Ausscheiden einer Person erfordert, ihre Teilnahmen zuvor zu entfernen oder zu archivieren.

Weitere Entscheidungen aus Review 1 (siehe README): Die Ansicht "Meine Anträge" entfällt in Meilenstein 1, weil `nst_antragsteller` auf Mitarbeiter zeigt und nicht auf den angemeldeten Benutzer; in Meilenstein 1 hat nur das KI-System ein ausdrückliches Hauptformular, alle übrigen Tabellen verwenden das erzeugte Standardformular.

## Folgen

- Builder werden an die Web API angepasst, nie die Umgebung von Hand; jede Korrektur wird mit Test und Eintrag in dieser ADR festgehalten.
- Die Beschriftung der Beziehungen im Menü folgt dem Sammlungsnamen; in einer Umgebung mit deutscher Basissprache könnte ein eigenes Etikett später ergänzt werden.
- Seed- und Abbauabläufe (Meilenstein 1, Aufgaben 5 und 6) müssen die Reihenfolge Teilnahme vor Mitarbeiter einhalten.
- Die Sicherheitsschicht (Unternehmenseinheiten, Rollen, Spaltensicherheit) wurde ohne Ablehnung durch die Web API angelegt; Beobachtungen stehen in der Chronik.

## Chronik der Web-API-Korrekturen

| Datum | Bereich | Korrektur |
|---|---|---|
| 2026-10-25 | Formelspalte | `Today()` zu `UTCToday()` |
| 2026-10-25 | Beziehungen | Menüetikett weggelassen |
| 2026-10-25 | Client | `Prefer: return=representation` entfernt |
| 2026-10-25 | Beziehungen | `nst_mitarbeiter_teilnahme` von `Cascade` zu `Restrict` |
| 2026-10-25 | Sicherheit | Rollenprivilegien werden über `AddPrivilegesRole` mit `Depth` und `BusinessUnitId` (Nullwert) gesetzt; Tiefe und Vorhandensein werden aus `roleprivilegescollection` (`privilegedepthmask` 1/2/4/8) gelesen, damit auch eine abweichende Tiefe korrigiert wird |
| 2026-10-25 | Sicherheit | Neue Rollen erhalten von Dataverse neun Basisprivilegien (z. B. `prvReadSdkMessage`); Prüfungen vergleichen daher nur die `nst_`- und Zusatzprivilegien exakt |
| 2026-10-25 | Sicherheit | Rollen, Profile und Berechtigungen laufen durch die Lösung; Unternehmenseinheiten und der Anwendungsbenutzer nicht (Header `solution=False`) |
| 2026-10-25 | Sicherheit | Rolle `nst Fachbereich`: Lesen und Anfügen-an auf `nst_organisation` stehen nicht in Entwurf 5, werden aber für das Organisationsfeld des Anwendungsfalls gebraucht. Tiefe `Local` statt `Global` (Datensätze gehören dem Standardteam der Einheit, ein Benutzer sieht nur die Gesellschaft der eigenen Einheit) |
| 2026-10-25 | Sicherheit | Spaltenberechtigungen mit abweichenden Werten (`canread`, `canupdate`, `cancreate`) werden per PATCH auf Allowed korrigiert; das Profil ist im Code keiner Rolle zugeordnet, die Zuweisung der Governance-Benutzer ist ein Portalschritt |
| 2026-10-25 | Diagramme | Gestapeltes Diagramm: die zweite Gruppierung ist nur ein zweites `groupby`-Attribut im Abruf, nicht eine zweite `<category>`. Eine zweite Kategorie ohne `measurecollection` verletzt das Schema, mit `measurecollection` meldet die API „A measure collection cannot use more than two Group By clauses“ (0x8004e006) |
| 2026-10-25 | Dashboard | Zellen-, Registerkarten- und Abschnitts-IDs in der Dashboard-FormXML müssen echte GUIDs sein (`{tab-dash}` wird abgelehnt, 0x80048425); sie werden deterministisch erzeugt |
| 2026-10-25 | App | `appmodules` verlangt `webresourceid` (Standard-Symbol `953b9fac-1e5e-e611-80d6-00155ded156f`, wird akzeptiert). Eine angelegte, noch nicht veröffentlichte App liefert `appmodules` nicht; die Suche fällt auf `RetrieveUnpublishedMultiple()` zurück, sonst würde ein zweiter Lauf eine doppelte App anlegen |
| 2026-10-25 | App | `PublishXml` für die App erwartet die App-ID im Element `<appmodule>`, nicht den eindeutigen Namen (0x80040216) |
| 2026-10-25 | App | `ValidateApp` ist eine ungebundene Funktion `ValidateApp(AppModuleId=…)` und liefert `ErrorType` als Text (`Error`, `Warning`), nicht als Zahl |
| 2026-10-25 | App | `AddAppComponents` mit `{"@odata.type": ".entity", "entityid": <MetadataId>}` wird angenommen, aber die ID wird ignoriert: jede GUID (auch die Null-GUID) erzeugt einen Eintrag, der auf die Tabelle „Entity“ zeigt (Diagnose: kein `objectid` entspricht einer der acht Tabellen; Veröffentlichen vor dem Hinzufügen ändert nichts). `metadataid` und `LogicalName` werden als unbekannte Eigenschaft abgelehnt. Tabellen gelangen daher nur über die Sitemap in die App (`ADD_ENTITY_COMPONENTS = False`); `ValidateApp` meldet dafür Warnungen, keine Fehler. Ein falscher Eintrag verschwindet mit `RemoveAppComponents` erst nach `PublishXml` der App |
| 2026-10-25 | App | Unsere Hauptformulare und Standardansichten werden mit `isdefault` angelegt; die Standardansicht „Active …“ der Plattform wird auf nicht-Standard gesetzt, sonst bleiben zwei Standardansichten je Tabelle. Das Formular „Information“ wird von der Plattform selbst abgewählt |
| 2026-10-25 | App | Entscheidung zu den Tabellenkomponenten: Die Tabellen werden mit dem Lösungsimport in Aufgabe 7 zu App-Komponenten (`AppModuleComponent`, Typ 1). Als Rückfall steht der Portalschritt „Vorhandene hinzufügen“ in der Wiederaufbau-Anleitung. Bis dahin zeigt die App die Tabellen nur über die Sitemap, und `ValidateApp` meldet Warnungen (keine Fehler) |
| 2026-10-25 | App | Definitionsprüfung: je Tabelle höchstens eine Ansicht mit `default = true` (`load_definitions` lehnt mehr ab), damit die Abwahl der Plattform-Standardansicht nicht bei jedem Lauf zwischen zwei Ansichten wechselt |
