# ADR-001: Dataverse statt SharePoint-Listen

- Datum: 2026-10-25
- Status: angenommen
- Hinweis: Alle Daten sind erfunden; keine Rechtsberatung.

## Kontext

Das KI-Register hält KI-Systeme, Risikobewertungen, Maßnahmen, Schulungen und Anwendungsfälle von drei Gesellschaften der fiktiven Nordstern Gruppe fest (acht Tabellen, 13 Beziehungen). In früheren Fachanwendungen wurden SharePoint-Listen als Datenspeicher gewählt: Sie sind schnell angelegt, im Microsoft-365-Abonnement enthalten und den Anwendern vertraut. Für das Register fällt die Wahl anders aus, weil vier Anforderungen zusammentreffen, die Listen nur schlecht abdecken:

1. **Beziehungen mit Löschverhalten.** Risikobewertungen und Maßnahmen sind Nachweise der Governance und dürfen nicht mit ihrem KI-System verschwinden, während die Teilnahmen an einer Schulung mit der Schulung gelöscht werden sollen.
2. **Zugriffsgrenzen innerhalb der Daten.** Die Benutzer einer Gesellschaft sehen nur deren Datensätze, Risikobewertungen sind nur für die Governance-Rolle lesbar, und die interne Bewertung eines KI-Systems ist ein Feld, das nur diese Rolle sehen darf.
3. **Änderungsnachweis.** Wer hat wann welche Risikoklasse oder welchen Status geändert, und was stand vorher dort?
4. **Lebenszyklus.** Das Datenmodell soll als Quelltext im Repository liegen, aus einer Entwicklungs- in eine Testumgebung wandern und sich aus dem Repository neu aufbauen lassen (ADR-002, ADR-003).

Die Angaben zu Seiten von Microsoft Learn wurden am 2026-10-25 geprüft (Belege am Ende, jeweils mit dem Seitendatum `ms.date`).

## Entscheidung

Das Register speichert seine Daten in **Microsoft Dataverse**, nicht in SharePoint-Listen.

| Anforderung | SharePoint-Listen | Dataverse (im Register) |
|---|---|---|
| Beziehungen und Löschverhalten | Nachschlagespalten verweisen von einer Liste auf eine andere. | 1:N-Beziehungen mit einem Verhalten beim Löschen des Elternsatzes: Verknüpfung entfernen, Löschen verhindern oder mitlöschen. Die Seite zu Tabellenbeziehungen nennt das Verhalten als Mittel, die Datenintegrität zu sichern. Im Register: KI-System zu Risikobewertung und Maßnahme `Restrict`, Schulung zu Teilnahme `Cascade` (`provision/definitions/relationships.toml`). |
| Zugriff | Berechtigungen auf Website, Liste und Element. Elementberechtigungen sind begrenzt: unterstützt werden 50.000 eindeutige Berechtigungsbereiche je Liste, empfohlen höchstens 5.000, und ab 100.000 Elementen lässt sich die Vererbung auf der Liste nicht mehr trennen (Seite „SharePoint limits“). Berechtigungen für einzelne Spalten kennt SharePoint nicht (so die Antworten auf Microsoft Q&A, keine Seite der Produktdokumentation). | Sicherheitsrollen mit Zugriffsstufen (Benutzer, Unternehmenseinheit, übergeordnete Einheit, Organisation), Unternehmenseinheiten als Sicherheitsgrenzen und Besitzerteams (Seite zur eigentümerbasierten Sicherheit). Spaltensicherheit mit Profilen: Wer eine gesicherte Spalte nicht lesen darf, sieht sie maskiert (Seite zur Spaltensicherheit). Im Register: drei Unternehmenseinheiten, vier Rollen, ein Spaltensicherheitsprofil. |
| Änderungsnachweis | Versionsverlauf je Element. | Auditing, einstellbar für Umgebung, Tabelle und Spalte: wer, wann, welches Feld, welcher vorherige Wert; auswertbar in der App und über die Web API (Seite zum Auditing). Im Register ist der Schalter der Tabellen KI-System, Risikobewertung und Anwendungsfall gesetzt (`IsAuditEnabled`); Dataverse schreibt ein Protokoll aber erst, wenn auch der Schalter der Umgebung eingeschaltet ist, und der stand in Dev am 2026-10-25 auf „aus“ (ADR-002). |
| Lebenszyklus | Das Schema einer Liste liegt in der SharePoint-Website. Die Seite „Solutions in Power Apps“ nennt Listen nicht unter den Lösungskomponenten. | Lösungen sind der Mechanismus für den Anwendungslebenszyklus der Power Platform und enthalten Tabellen, Auswahlfelder, Apps und Flows (Seite „Solutions in Power Apps“); Sicherheitsrollen und Spaltensicherheitsprofile wandern mit der Lösung (Seite zur eigentümerbasierten Sicherheit). Im Register: `solution/src`, ADR-003. |

## Wann Listen weiterhin die richtige Wahl sind

SharePoint-Listen bleiben das passende Werkzeug, wenn

- eine Liste oder wenige flache Listen genügen, ohne Beziehungen, die beim Löschen halten müssen (Erfassungen, Checklisten, Aufgaben eines Teams);
- alle Beteiligten dasselbe sehen und ändern dürfen oder ein Zugriff je Liste ausreicht, und kein Feld eigene Rechte braucht;
- ein Versionsverlauf je Element reicht und kein Nachweis je Feld verlangt wird;
- Dateien und Dokumente im Mittelpunkt stehen (Bibliotheken) und die Zusammenarbeit in Teams und Microsoft 365 stattfindet, ohne zusätzliche Lizenz;
- ein schneller Prototyp oder eine kurzlebige Erfassung gebraucht wird; wachsen Beziehungen und Zugriffsgrenzen nach, ist der Umzug nach Dataverse der nächste Schritt (nicht Teil dieses Projekts);
- die Menge innerhalb der Grenze von 30 Millionen Elementen je Liste bleibt (Seite „SharePoint limits“).

Faustregel dieses Projekts: Treffen zwei der vier Anforderungen aus dem Kontext zu, ist Dataverse die bessere Wahl; sonst genügt eine Liste. Beides lässt sich verbinden: Das Register speichert nur einen Link auf die Dokumentation eines Systems (`nst_dokumentation`), die Dokumente selbst können in einer SharePoint-Bibliothek liegen.

## Folgen

- **Die Umgebungsfrage kommt hinzu.** Dataverse braucht eine Umgebung mit Datenbank. Nordstern Dev und Test sind Entwicklerumgebungen mit den Fristen aus ADR-003 (ausgesetzt ab 2026-12-15, gelöscht ab 2027-01-15); SharePoint-Listen wären davon nicht betroffen gewesen. Ein Betrieb über das Portfolio hinaus bräuchte passende Lizenzen (ADR-003 nennt keine Preise).
- **Mehr Aufwand vorab.** Datenmodell, Beziehungsverhalten, Rollen und Provisionierung als Code (ADR-002) kosten mehr als eine Liste in der Oberfläche; dafür ist das Ergebnis reproduzierbar und prüfbar.
- **Speicher.** Audit-Protokolle belegen Log-Speicher der Umgebung (Seite zum Auditing). Deshalb ist der Schalter der Tabellen nur bei KI-System, Risikobewertung und Anwendungsfall gesetzt (`IsAuditEnabled`). Ein Protokoll entsteht erst, wenn auch der Schalter der Umgebung eingeschaltet ist; in Dev stand er am 2026-10-25 auf „aus“ (ADR-002), das Register weist dort also noch keine Änderungen nach.
- **Grenzen von Dataverse, die das Register trifft.** Eine untergeordnete Tabelle kann nur eine kaskadierende Elternbeziehung haben; deshalb ist Schulung die Elterntabelle der Schulungsteilnahme und die Beziehung zum Mitarbeiter verhindert nur das Löschen (ADR-002, Seite zu Tabellenbeziehungen). Nachschlage-, Formel- und Primärspalten lassen sich nicht über die Spaltensicherheit schützen (Seite zur Spaltensicherheit); die interne Bewertung ist deshalb ein eigenes Memo-Feld.
- **Die Spaltensicherheit gilt nicht für Systemadministratoren** (Seite zur Spaltensicherheit). Die maskierte Darstellung zeigt nur ein Konto ohne diese Rolle, zum Beispiel die Demo-Rolle `nst Fachbereich`.
- **Nicht geprüft und nicht Teil dieses Projekts.** Der Umfang des Versionsverlaufs von Listenelementen, das Verhalten von SharePoint-Nachschlagespalten beim Löschen, die Schwellen für große Ansichten und der Umzug bestehender Listen nach Dataverse.

## Belege

Abgerufen am 2026-10-25 (Seitendatum `ms.date` in Klammern):

- SharePoint-Grenzen (Elemente, Berechtigungsbereiche, Vererbung): https://learn.microsoft.com/en-us/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits (2026-10-06)
- Tabellenbeziehungen und ihr Verhalten: https://learn.microsoft.com/en-us/power-apps/maker/data-platform/create-edit-entity-relationships (2026-09-14)
- Eigentümerbasierte Sicherheit, Unternehmenseinheiten, Teams: https://learn.microsoft.com/en-us/power-platform/admin/wp-security-cds (2026-10-05)
- Spaltensicherheit: https://learn.microsoft.com/en-us/power-platform/admin/field-level-security (2026-09-21)
- Auditing: https://learn.microsoft.com/en-us/power-platform/admin/manage-dataverse-auditing (2026-10-07)
- Lösungen: https://learn.microsoft.com/en-us/power-apps/maker/data-platform/solutions-overview (2026-01-09)
- Keine Spaltenberechtigungen in SharePoint-Listen: Antworten auf Microsoft Q&A, zum Beispiel https://learn.microsoft.com/en-us/answers/questions/5434500/microsoft-lists-cant-restrict-column-level-permiss (Forenbeitrag, keine Produktdokumentation)
