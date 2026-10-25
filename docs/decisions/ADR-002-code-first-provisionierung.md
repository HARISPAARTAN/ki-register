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
