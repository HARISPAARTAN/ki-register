# Nordstern KI-Register

Ein Register für KI-Systeme nach EU-KI-Verordnung (EU AI Act), gebaut auf Microsoft Dataverse und vollständig als Code provisioniert: Tabellen, Auswahlfelder, Beziehungen, Sicherheitsrollen, Formulare, Ansichten und die modellgesteuerte App entstehen aus den TOML-Definitionen unter `provision/definitions/`. Alle Daten sind fiktiv (Nordstern Gruppe).

Dieses Projekt ist keine Rechtsberatung.

Status: in Arbeit.

## Entscheidungen aus Review 1

- Die Ansicht "Meine Anträge" entfällt in Meilenstein 1: `nst_antragsteller` ist ein Nachschlagefeld auf Mitarbeiter, nicht der angemeldete Benutzer. Die Canvas-App zur Anmeldung in Meilenstein 2 zeigt die eigenen Anträge der Benutzerin oder des Benutzers.
- In Meilenstein 1 hat nur das KI-System ein ausdrückliches Hauptformular; alle übrigen Tabellen verwenden das erzeugte Standardformular.
- Diese Punkte werden in ADR-002 übernommen.
