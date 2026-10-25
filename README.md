# Nordstern KI-Register

Ein Register für KI-Systeme nach EU-KI-Verordnung (EU AI Act), gebaut auf Microsoft Dataverse und vollständig als Code provisioniert: Tabellen, Auswahlfelder, Beziehungen, Sicherheitsrollen, Formulare, Ansichten und die modellgesteuerte App entstehen aus den TOML-Definitionen unter `provision/definitions/`. Alle Daten sind fiktiv (Nordstern Gruppe).

Dieses Projekt ist keine Rechtsberatung.

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
4. `uv run --env-file .env kiregister apply --env dev --only security` legt Unternehmenseinheiten, die Rollen `nst KI-Governance`, `nst Fachbereich`, `nst Leser` mit ihren Privilegien und das Spaltensicherheitsprofil an (idempotent). Das Zuweisen von Rollen und Profil an Benutzer ist ein Portalschritt.
5. `uv run --env-file .env kiregister apply --env dev --only app` legt Ansichten, Formulare, Diagramme, das Dashboard, die Sitemap und die modellgesteuerte App `nst_kiregister` an (idempotent). Prüfung durch den Eigentümer: https://make.powerapps.com, Apps, KI-Register, Abspielen (vier Bereiche, Ansichten, Formular-Registerkarten).
   Hinweis: Die Tabellen werden erst mit dem Lösungsimport (Aufgabe 7, `AppModuleComponent` Typ 1) App-Komponenten; Rückfall im Wiederaufbau-Leitfaden ist der Portalschritt „Vorhandene hinzufügen“. Bis dahin zeigt die App die Tabellen nur über die Sitemap, und `ValidateApp` meldet Warnungen (im Abspielen sichtbar), keine Fehler.
6. Integrationstests: `uv run --env-file .env pytest tests/integration -m dataverse -v`.

## Setup (English)

Once, by the owner after `az login`: run `tools/setup_app_registration.sh`, put tenant ID, client ID and secret into the git-ignored `.env`, then `kiregister bootstrap --env dev|test` (creates the application user with System Administrator via the owner's Azure CLI token) and `kiregister apply --env dev --only metadata` (idempotent), then `kiregister apply --env dev --only security` (business units, three roles, column security profile; assigning users is a portal step), then `kiregister apply --env dev --only app` (views, forms, charts, dashboard, site map, the model-driven app). Integration tests: `pytest tests/integration -m dataverse`.
