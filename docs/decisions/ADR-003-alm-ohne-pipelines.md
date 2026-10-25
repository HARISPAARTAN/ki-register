# ADR-003: ALM ohne Pipelines (GitHub Actions und Power Platform CLI)

- Datum: 2026-10-25
- Status: angenommen

## Kontext

Das Register soll einen vollständigen Lebenszyklus zeigen: die Lösung `NordsternKIRegister` kommt aus der Entwicklungsumgebung als Quelltext ins Repository (`solution/src`), wird als verwaltete Lösung gepackt und in eine Testumgebung importiert, und ein Prüflauf belegt das Ergebnis. Microsoft bietet dafür zwei eingebaute Wege (Pipelines in Power Platform, Dataverse-Git-Integration) und das Werkzeug `pac` mit GitHub Actions. Die Umgebungen sind kostenlose Entwicklerumgebungen aus dem Developer Plan; das schränkt die Wahl ein. Alle Angaben in diesem Abschnitt wurden am 2026-10-25 gegen Seiten von Microsoft Learn geprüft (Belege am Ende, jeweils mit dem Seitendatum `ms.date`).

### Fristen für unverwaltete Entwicklerumgebungen

Nordstern Dev und Nordstern Test sind unverwaltete Entwicklerumgebungen. Für sie gilt (Seite „important changes coming“, Abschnitt zur Abkündigung unverwalteter Entwicklerumgebungen und des Developer Plans):

| Datum | Wirkung |
|---|---|
| 2026-11-15 | Die Anmeldung zum Developer Plan legt keine Entwicklerumgebung mehr an; neue unverwaltete Entwicklerumgebungen sind weder in Power Apps noch im Admin Center, in PowerShell oder mit dem CLI möglich. Jede Nutzerin und jeder Nutzer darf nur eine verwaltete Entwicklerumgebung anlegen. |
| 2026-12-15 | Bestehende unverwaltete Entwicklerumgebungen werden ausgesetzt; Apps, Flows, Agenten, Power-Pages-Entwicklerseiten und Daten sind nicht mehr verfügbar. |
| 2027-01-15 | Ausgesetzte unverwaltete Entwicklerumgebungen werden gelöscht. |

Entwicklerumgebungen, die verwaltete Umgebungen sind, sind nicht betroffen. Der Entwicklertyp bleibt bestehen, aber nur noch als verwaltete Entwicklerumgebung (Seite „Developer Plan“). Außerdem gilt für den Developer Plan: 2 GB Datenbank und 750 Flow-Läufe im Monat, und Umgebungen ohne Aktivität in den letzten 30 Tagen werden automatisch deaktiviert.

### Lizenzen und die eingebauten Wege

- **Managed Environments und der Developer Plan.** Die Nutzungsrechte für Managed Environments sind im Developer Plan nicht enthalten: Wer Assets in einer verwalteten Entwicklerumgebung ausführt, braucht zusätzlich eine Premium-Lizenz (Seiten „Developer Plan“ und „Managed Environments licensing“). Eine Umgebung zu einer verwalteten zu machen, löst die Frist also nur mit zusätzlichen Premium-Lizenzen, die für dieses Projekt nicht vorgesehen sind.
- **Pipelines in Power Platform.** Entwicklerumgebungen müssen nach der Seite zu Pipelines nicht verwaltet sein, alle anderen Umgebungen einer Pipeline schon, und für verwaltete Umgebungen sind Lizenzen mit Premium-Nutzungsrechten nötig. Ab Oktober 2026 meldet die Bereitstellungsseite des Admin Centers Bereitstellungen in unverwaltete Zielumgebungen; Administratoren haben 30 Tage (einmal um 30 Tage verlängerbar), die Aktivierung von Managed Environments zu genehmigen, sonst werden weitere Bereitstellungen dorthin blockiert.
- **Dataverse-Git-Integration.** Nach den FAQ müssen Entwicklungs- und Zielumgebungen verwaltete Umgebungen sein, und alle Benutzer der Umgebung müssen die Lizenzanforderungen für Managed Environments erfüllen, unabhängig vom Umgebungstyp. Als Git-Anbieter sind Azure DevOps und GitHub unterstützt. Die Git-Integration schreibt ein YAML-Format; `pac solution unpack` schreibt standardmäßig das XML-Format des SolutionPackager, und `pac solution pack` liest beide Formate.
- **GitHub Actions für Power Platform.** Die Aktionen (`actions-install`, `export-solution`, `unpack-solution`, `pack-solution`, `import-solution`) authentifizieren sich mit einem Dienstprinzipal (App-Registrierung mit Client-Geheimnis und Anwendungsbenutzer) und laufen auf Windows- und Linux-Runnern. Die Seite verlangt eine Dataverse-Umgebung mit Datenbank und nennt keine Voraussetzung Managed Environments; die Aktionen selbst kosten nichts, es genügt ein GitHub-Konto (laut Seite 2.000 freie Minuten im Monat).

## Entscheidung

1. **ALM mit `pac` und GitHub Actions statt Pipelines und Git-Integration.** Die Lösungsquelle liegt im XML-Format des SolutionPackager unter `solution/src` (`pac solution unpack --packagetype Both`). Der Weg ist ohne Managed Environments und ohne Premium-Lizenzen gangbar und macht die Abläufe als Workflows im Repository sichtbar.
2. **`pac` läuft nur auf GitHub-Runnern**, nie auf dem Arbeitsrechner: Der Rechner behält seine bestehenden Anmeldeprofile unberührt, und jeder Schritt ist ohne lokale Installation nachvollziehbar. Die Aktionen von `microsoft/powerplatform-actions` sind auf den Major-Tag `v1` gepinnt (letzter veröffentlichter Release: v1.9.2 vom 2026-05-14; der Tag `v1` wandert mit); alle Jobs laufen auf `ubuntu-24.04`.
3. **Vier Workflows.**
   - `ci.yml`: Lint und Unit-Tests bei Push und Pull Request; der Job `integration` (Marker `dataverse`, Geheimnisse als Umgebung) nur per Hand.
   - `export-solution.yml` (nur per Hand): exportiert unmanaged und managed aus Dev, entpackt mit `solution-type: Both` nach `solution/src` (die Aktion übergibt `--allowDelete true`, entfernte Komponenten verschwinden also auch aus der Quelle) und öffnet einen Pull Request, der nur `solution/src` enthalten darf (`add-paths`). Die Eigentümerin oder der Eigentümer sieht den Diff an und führt zusammen.
   - `import-dev.yml` (nur per Hand): packt `solution/src` als unmanaged Lösung und importiert sie nach Dev. Er wird gebraucht, wenn die Quelle von Hand ergänzt wurde, etwa um die App-Komponenten der Tabellen (siehe ADR-002), und schließt danach mit einem erneuten Export.
   - `deploy-test.yml` (bei Tag `v*` und per Hand): packt `solution/src` als managed Lösung, importiert nach Test (`force-overwrite`, `publish-changes`, Abhängigkeitsprüfung an) und ruft `kiregister verify --env test` auf.
4. **Test erhält nur die Lösung, `verify` prüft nur Lösungskomponenten.** Unternehmenseinheiten, Besitzerteams und Seed-Daten sind keine Lösungskomponenten. Sie in Test anzulegen hieße, `apply --only security` gegen eine Umgebung auszuführen, in der die Rollen bereits als verwaltete Schicht liegen, und damit unverwaltete Änderungen über sie zu legen. Mit `KIREGISTER_VERIFY_NO_SEED=1` (gesetzt in `deploy-test.yml`) prüft `verify` Tabellen, Spalten, Nachschlagefelder, Auswahlfelder, Beziehungen, Rollen, das Spaltensicherheitsprofil mit seinen Berechtigungen und das App-Modul; Unternehmenseinheiten, Besitzerteams samt Mitgliedschaft und Seed-Anzahlen entfallen. Ohne die Variable bleibt die volle Prüfung gegen Dev.
5. **Nichts wird automatisch gelöscht.** Der Import legt an und aktualisiert; er entfernt keine Komponenten. Ein Upgrade-Import (`stage-and-upgrade`) wird nicht verwendet. Das Löschen von Komponenten bleibt Handarbeit (Reihenfolge in ADR-002).
6. **Tags setzt der Mensch.** Kein Workflow erzeugt oder pusht einen Tag; `deploy-test.yml` ist zusätzlich per Hand startbar, damit der Weg ohne Tag erprobt werden kann.

## Folgen

- **Die Fristen bleiben bestehen.** Dev und Test werden ab 2026-12-15 ausgesetzt und ab 2027-01-15 gelöscht. Alle Meilensteine enden deshalb vor 2026-12-10 (Entwurf, Abschnitt 2); der Wiederaufbau läuft aus dem Repository (`provision/`, `data/seed/`, `solution/src`) in einer Standard-Testumgebung (30 Tage; laut Seite „Developer Plan“ bleibt dieser Typ verfügbar) oder in einer verwalteten Entwicklerumgebung, falls die Lizenzfrage bis dahin anders liegt. Der Ablauf kommt in den Wiederaufbau-Leitfaden (Meilenstein 4).
- **Die Quelle ist ein Artefakt, nicht die Wahrheit.** Die Wahrheit sind die TOML-Definitionen (ADR-002); `solution/src` ist der Export daraus plus die Ergänzungen, die sich nur über den Lösungsimport setzen lassen. Jede Handänderung an `solution/src` läuft über `import-dev.yml` und einen erneuten Export, damit Quelle und Dev nicht auseinanderlaufen.
- **Export-Pull-Requests lösen kein CI aus.** Pull Requests, die ein Workflow mit dem Token von Actions anlegt, lösen `pull_request`-Läufe aus, die eine Freigabe verlangen („This workflow run required approval but was not approved before it expired“) und beim Zusammenführen als roter Lauf ohne Jobs enden; so geschehen bei den Pull Requests 1 und 2. Deshalb ignoriert `ci.yml` bei `pull_request` Änderungen unter `solution/**`; Ruff und die Unit-Tests prüfen XML ohnehin nicht. Der Diff wird von Hand geprüft: nur Dateien unter `solution/src`, keine Archive, keine Geheimnisse.
- **Unverwaltete Entwicklerumgebungen ohne Aktivität** werden nach 30 Tagen deaktiviert. Ob ein Deploy-Lauf als Aktivität zählt, wurde nicht geprüft; vor einer Demo ist Test zu öffnen.
- **Meilenstein 2 braucht Einstellungen für die Umgebung.** Sobald Flows mit Verbindungsreferenzen und Umgebungsvariablen in die Lösung kommen, braucht `import-solution` eine Einstellungsdatei (`use-deployment-settings-file`); die Verbindungen selbst legt die Eigentümerin oder der Eigentümer einmal im Portal an.
- **Prüftiefe in Test.** `verify` belegt, dass die Komponenten der Lösung vorhanden sind. Es belegt nicht, dass ein Benutzer mit einer Rolle die erwarteten Daten sieht; dafür gibt es in Test keine Daten.

### Was eine bezahlte Lizenz ändern würde

Mit Managed Environments für Dev und Test und Premium-Lizenzen für die Benutzer, die Assets ausführen:

- Dev und Test wären verwaltete Umgebungen; Dev wäre als verwaltete Entwicklerumgebung von den Fristen nicht betroffen.
- **Pipelines in Power Platform** könnten `deploy-test.yml` ersetzen: Host-Umgebung, Stufen, Genehmigungen und delegierte Bereitstellungen mit Dienstprinzipal, Vorabprüfung von Abhängigkeiten, automatische Sicherung der managed und unmanaged Artefakte im Host. Der Standardimport einer Pipeline ist ein Upgrade ohne Überschreiben von Anpassungen. Pipelines lassen sich zudem mit GitHub Actions erweitern, die Workflows entfielen also nicht ganz.
- **Dataverse-Git-Integration** könnte `export-solution.yml` ersetzen: Änderungen werden aus dem Lösungsbereich heraus committet. Dabei wechselt die Quelle vom XML- ins YAML-Format; die FAQ empfehlen dafür einen neuen Ort im Repository. `solution/src` würde neu angelegt, nicht fortgeschrieben.
- Unverändert blieben das Provisionierungspaket, `kiregister verify` und die Tests.

## Belege und offene Punkte

Abgerufen am 2026-10-25 (Seitendatum `ms.date` in Klammern):

- Fristen: https://learn.microsoft.com/en-us/power-platform/important-changes-coming (2026-10-06)
- Developer Plan, verwaltete Entwicklerumgebungen, Kapazität, 30-Tage-Regel: https://learn.microsoft.com/en-us/power-platform/developer/plan (2026-10-17)
- Lizenzierung von Managed Environments: https://learn.microsoft.com/en-us/power-platform/admin/managed-environment-licensing (2026-08-31)
- Pipelines: https://learn.microsoft.com/en-us/power-platform/alm/pipelines (2026-09-29)
- Git-Integration, FAQ: https://learn.microsoft.com/en-us/power-platform/alm/git-integration/faqs (2026-10-14)
- GitHub Actions für Power Platform: https://learn.microsoft.com/en-us/power-platform/alm/devops-github-actions (2026-08-19)
- `pac solution` (`pack`, `unpack`, `--packagetype`): https://learn.microsoft.com/en-us/power-platform/developer/cli/reference/solution (2026-02-25)
- Aktionen und Releases: https://github.com/microsoft/powerplatform-actions/releases

Bestätigt sind die drei Fristen (2026-11-15, 2026-12-15, 2027-01-15), die Aussage, dass der Developer Plan keine Nutzungsrechte für Managed Environments enthält, und die Anforderung verwalteter Umgebungen für die Git-Integration. Berichtigt gegenüber dem Entwurf (Abschnitte 1 und 12), der Pipelines und Git-Integration gemeinsam an Managed Environments bindet: Für Pipelines gilt das nach der Seite zu Pipelines für alle Umgebungen außer den Entwicklerumgebungen. Nicht bestätigen ließ sich, ob die Durchsetzung ab Oktober 2026 (Blockade nach 30 Tagen) auch Entwicklerumgebungen als Ziel trifft; die Seite spricht von „unmanaged target environments“, ohne den Entwicklertyp auszunehmen oder zu nennen. Ebenfalls nicht geprüft sind Preise der Premium-Lizenzen (sie stehen hier bewusst nicht) und die Frage, ob ein Importlauf die 30-Tage-Inaktivitätsregel zurücksetzt.
