# Datenmodell des KI-Registers (ERD)

Dieses Dokument wird aus `provision/definitions/*.toml` erzeugt (`uv run python tools/erd.py`) und nicht von Hand geändert; `tests/unit/test_erd.py` schlägt fehl, wenn es vom Stand der Definitionen abweicht. Alle Daten sind fiktiv (Nordstern Gruppe), das Register ist keine Rechtsberatung.

## Diagramm

```mermaid
erDiagram
    nst_organisation {
        guid nst_organisationid PK "Tabelle Organisation"
        string nst_name "Name, Primärspalte"
        string nst_kurzname "Kurzname"
        string nst_branche "Branche"
        string nst_businessunitname "Business-Unit-Name"
        string nst_sitz "Sitz"
    }
    nst_mitarbeiter {
        guid nst_mitarbeiterid PK "Tabelle Mitarbeiter"
        string nst_name "Name, Primärspalte"
        guid nst_organisation FK "Organisation, Nachschlagefeld auf nst_organisation, Pflicht"
        string nst_funktion "Funktion"
        email nst_email "E-Mail"
        bool nst_kiverantwortlich "KI-verantwortlich"
    }
    nst_kisystem {
        guid nst_kisystemid PK "Tabelle KI-System"
        string nst_name "Name, Primärspalte"
        guid nst_organisation FK "Organisation, Nachschlagefeld auf nst_organisation, Pflicht"
        guid nst_verantwortlicher FK "Verantwortlich, Nachschlagefeld auf nst_mitarbeiter"
        autonumber nst_kennung "Kennung, Format KIS-nnnn"
        string nst_fachbereich "Fachbereich"
        memo nst_beschreibung "Beschreibung"
        memo nst_zweck "Zweck"
        string nst_anbieter "Anbieter / Hersteller"
        choice nst_systemtyp "Systemtyp, Auswahl nst_systemtyp"
        choice nst_rolle "Rolle nach KI-Verordnung, Auswahl nst_rolle_kivo"
        choice nst_status "Status, Pflicht, Auswahl nst_status_kisystem"
        date nst_inbetriebnahme "Inbetriebnahme"
        date nst_letztepruefung "Letzte Prüfung"
        date nst_naechstepruefung "Nächste Prüfung"
        choices nst_datenarten "Verarbeitete Datenarten, Auswahl nst_datenart"
        choice nst_risikoklasse "Risikoklasse, Auswahl nst_risikoklasse"
        choice nst_anhang3kategorie "Anhang-III-Kategorie, Auswahl nst_anhang3_kategorie"
        bool nst_transparenzpflicht "Transparenzpflicht (Art. 50)"
        bool nst_eudatenbank "Registrierung EU-Datenbank (Art. 49)"
        url nst_dokumentation "Dokumentation (Link)"
        memo nst_internebewertung "Interne Bewertung, gesichert (Spaltensicherheit)"
        formula nst_pruefungueberfaellig "Prüfung überfällig, Formel, Ergebnis bool"
    }
    nst_anwendungsfall {
        guid nst_anwendungsfallid PK "Tabelle Anwendungsfall"
        string nst_name "Name, Primärspalte"
        guid nst_organisation FK "Organisation, Nachschlagefeld auf nst_organisation, Pflicht"
        guid nst_antragsteller FK "Antragsteller, Nachschlagefeld auf nst_mitarbeiter"
        guid nst_kisystem FK "KI-System, Nachschlagefeld auf nst_kisystem"
        autonumber nst_kennung "Kennung, Format AF-nnnn"
        memo nst_beschreibung "Beschreibung"
        memo nst_zweck "Zweck"
        string nst_betroffene "Betroffene"
        choices nst_datenarten "Verarbeitete Datenarten, Auswahl nst_datenart"
        date nst_gewuenschterstart "Gewünschter Start"
        choice nst_status "Status, Pflicht, Auswahl nst_status_anwendungsfall"
        memo nst_entscheidung "Entscheidung"
        datetime nst_entschiedenam "Entschieden am"
    }
    nst_risikobewertung {
        guid nst_risikobewertungid PK "Tabelle Risikobewertung"
        string nst_name "Name, Primärspalte"
        guid nst_pruefer FK "Prüfer, Nachschlagefeld auf nst_mitarbeiter"
        guid nst_kisystem FK "KI-System, Nachschlagefeld auf nst_kisystem, Pflicht"
        autonumber nst_kennung "Kennung, Format RB-nnnn"
        date nst_datum "Datum, Pflicht"
        bool nst_art5verbotenepraxis "Verbotene Praxis (Art. 5)"
        bool nst_anhang3treffer "Anhang-III-Treffer"
        choice nst_anhang3kategorie "Anhang-III-Kategorie, Auswahl nst_anhang3_kategorie"
        bool nst_ausnahmeart6abs3 "Ausnahme (Art. 6 Abs. 3)"
        bool nst_art50transparenz "Transparenzpflicht (Art. 50)"
        choice nst_ergebnis "Ergebnis, Pflicht, Auswahl nst_risikoklasse"
        memo nst_begruendung "Begründung"
        date nst_gueltigbis "Gültig bis"
    }
    nst_massnahme {
        guid nst_massnahmeid PK "Tabelle Maßnahme"
        string nst_name "Name, Primärspalte"
        guid nst_verantwortlicher FK "Verantwortlich, Nachschlagefeld auf nst_mitarbeiter"
        guid nst_kisystem FK "KI-System, Nachschlagefeld auf nst_kisystem, Pflicht"
        autonumber nst_kennung "Kennung, Format MN-nnnn"
        choice nst_typ "Typ, Auswahl nst_massnahme_typ"
        memo nst_beschreibung "Beschreibung"
        date nst_faelligam "Fällig am"
        choice nst_status "Status, Auswahl nst_massnahme_status"
        string nst_artikelbezug "Artikelbezug"
    }
    nst_schulung {
        guid nst_schulungid PK "Tabelle Schulung"
        string nst_name "Name, Primärspalte"
        guid nst_organisation FK "Organisation, Nachschlagefeld auf nst_organisation, Pflicht"
        date nst_datum "Datum"
        int nst_dauerminuten "Dauer (Minuten)"
        memo nst_inhalt "Inhalt"
        string nst_zielgruppe "Zielgruppe"
    }
    nst_schulungsteilnahme {
        guid nst_schulungsteilnahmeid PK "Tabelle Schulungsteilnahme"
        string nst_name "Name, Primärspalte"
        guid nst_schulung FK "Schulung, Nachschlagefeld auf nst_schulung, Pflicht"
        guid nst_mitarbeiter FK "Mitarbeiter, Nachschlagefeld auf nst_mitarbeiter, Pflicht"
        choice nst_status "Status, Auswahl nst_schulung_status"
        date nst_abgeschlossenam "Abgeschlossen am"
    }
    nst_organisation ||--o{ nst_mitarbeiter : "Organisation"
    nst_organisation ||--o{ nst_kisystem : "Organisation"
    nst_organisation ||--o{ nst_anwendungsfall : "Organisation"
    nst_organisation ||--o{ nst_schulung : "Organisation"
    nst_mitarbeiter |o--o{ nst_kisystem : "Verantwortlich"
    nst_mitarbeiter |o--o{ nst_anwendungsfall : "Antragsteller"
    nst_mitarbeiter |o--o{ nst_risikobewertung : "Prüfer"
    nst_mitarbeiter |o--o{ nst_massnahme : "Verantwortlich"
    nst_kisystem ||--o{ nst_risikobewertung : "KI-System"
    nst_kisystem ||--o{ nst_massnahme : "KI-System"
    nst_kisystem |o--o{ nst_anwendungsfall : "KI-System"
    nst_schulung ||--o{ nst_schulungsteilnahme : "Schulung"
    nst_mitarbeiter ||--o{ nst_schulungsteilnahme : "Mitarbeiter"
```

Lesehilfe: Die Entitäten tragen die Schemanamen der Tabellen, der Kommentar der Schlüsselzeile nennt den deutschen Anzeigenamen. `PK` ist der Primärschlüssel, `FK` ein Nachschlagefeld auf die Elterntabelle; die Beschriftung einer Linie ist der Anzeigename des Nachschlagefelds. `||` bedeutet genau ein Elternsatz (Pflichtfeld), `|o` null oder ein Elternsatz (optional), `o{` null bis viele Kindsätze. Spaltentypen: `string`, `memo` (langer Text), `int`, `bool`, `date`, `datetime`, `url`, `email`, `choice` und `choices` (Auswahl und Mehrfachauswahl eines globalen Auswahlfelds), `autonumber` (Zähler mit Präfix) und `formula` (berechnete Spalte).

Alle Tabellen sind benutzer- oder teameigen (`ownerid`); so bilden Unternehmenseinheiten Zugriffsgrenzen. Systemspalten wie Eigentümer, Erstellt am und Status sind nicht eingezeichnet.

## Tabellen

| Tabelle | Anzeigename | Mehrzahl | Primärspalte | Audit-Flag der Tabelle | Notizen |
| --- | --- | --- | --- | --- | --- |
| `nst_organisation` | Organisation | Organisationen | `nst_name` | nein | nein |
| `nst_mitarbeiter` | Mitarbeiter | Mitarbeiter | `nst_name` | nein | nein |
| `nst_kisystem` | KI-System | KI-Systeme | `nst_name` | ja | ja |
| `nst_anwendungsfall` | Anwendungsfall | Anwendungsfälle | `nst_name` | ja | ja |
| `nst_risikobewertung` | Risikobewertung | Risikobewertungen | `nst_name` | ja | ja |
| `nst_massnahme` | Maßnahme | Maßnahmen | `nst_name` | nein | nein |
| `nst_schulung` | Schulung | Schulungen | `nst_name` | nein | nein |
| `nst_schulungsteilnahme` | Schulungsteilnahme | Teilnahmen | `nst_name` | nein | nein |

## Beziehungen

| Beziehung | Eltern (1) | Kind (n) | Nachschlagefeld | Pflicht | Beim Löschen des Elternsatzes |
| --- | --- | --- | --- | --- | --- |
| `nst_organisation_mitarbeiter` | `nst_organisation` | `nst_mitarbeiter` | `nst_organisation` (Organisation) | ja | Verknüpfung entfernen |
| `nst_organisation_kisystem` | `nst_organisation` | `nst_kisystem` | `nst_organisation` (Organisation) | ja | Verknüpfung entfernen |
| `nst_organisation_anwendungsfall` | `nst_organisation` | `nst_anwendungsfall` | `nst_organisation` (Organisation) | ja | Verknüpfung entfernen |
| `nst_organisation_schulung` | `nst_organisation` | `nst_schulung` | `nst_organisation` (Organisation) | ja | Verknüpfung entfernen |
| `nst_mitarbeiter_kisystem_verantwortlicher` | `nst_mitarbeiter` | `nst_kisystem` | `nst_verantwortlicher` (Verantwortlich) | nein | Verknüpfung entfernen |
| `nst_mitarbeiter_anwendungsfall_antragsteller` | `nst_mitarbeiter` | `nst_anwendungsfall` | `nst_antragsteller` (Antragsteller) | nein | Verknüpfung entfernen |
| `nst_mitarbeiter_risikobewertung_pruefer` | `nst_mitarbeiter` | `nst_risikobewertung` | `nst_pruefer` (Prüfer) | nein | Verknüpfung entfernen |
| `nst_mitarbeiter_massnahme_verantwortlicher` | `nst_mitarbeiter` | `nst_massnahme` | `nst_verantwortlicher` (Verantwortlich) | nein | Verknüpfung entfernen |
| `nst_kisystem_risikobewertung` | `nst_kisystem` | `nst_risikobewertung` | `nst_kisystem` (KI-System) | ja | Löschen verhindern |
| `nst_kisystem_massnahme` | `nst_kisystem` | `nst_massnahme` | `nst_kisystem` (KI-System) | ja | Löschen verhindern |
| `nst_kisystem_anwendungsfall` | `nst_kisystem` | `nst_anwendungsfall` | `nst_kisystem` (KI-System) | nein | Verknüpfung entfernen |
| `nst_schulung_teilnahme` | `nst_schulung` | `nst_schulungsteilnahme` | `nst_schulung` (Schulung) | ja | Datensätze mitlöschen |
| `nst_mitarbeiter_teilnahme` | `nst_mitarbeiter` | `nst_schulungsteilnahme` | `nst_mitarbeiter` (Mitarbeiter) | ja | Löschen verhindern |

Dataverse erlaubt je untergeordneter Tabelle nur eine übergeordnete (kaskadierende) Beziehung. Deshalb ist Schulung die übergeordnete Tabelle der Schulungsteilnahme (Kaskade), und die Beziehung zum Mitarbeiter verhindert das Löschen (ADR-002).

## Auswahlfelder

Die Werte eines Auswahlfelds sind `580000000` plus die Position in der Reihenfolge der Definition (Optionswertpräfix 58000).

| Auswahlfeld | Anzeigename | Werte in Reihenfolge |
| --- | --- | --- |
| `nst_risikoklasse` | Risikoklasse | Nicht bewertet; Unannehmbar (Art. 5); Hoch; Begrenzt (Transparenzpflicht); Minimal |
| `nst_rolle_kivo` | Rolle nach KI-Verordnung | Anbieter; Betreiber; Einführer; Händler; Produkthersteller; Bevollmächtigter |
| `nst_systemtyp` | Systemtyp | Eigenentwicklung; Eingekaufte Standardsoftware; KI-Modell mit allgemeinem Verwendungszweck (GPAI); In Produkt eingebettet |
| `nst_status_kisystem` | Status KI-System | Idee; In Bewertung; Freigegeben; In Betrieb; Ausgesetzt; Eingestellt; Abgelehnt |
| `nst_status_anwendungsfall` | Status Anwendungsfall | Eingereicht; In Prüfung; Genehmigt; Abgelehnt; Zurückgezogen |
| `nst_anhang3_kategorie` | Anhang-III-Kategorie | Keine; 1 Biometrie; 2 Kritische Infrastruktur; 3 Bildung; 4 Beschäftigung; 5 Grundlegende Dienste; 6 Strafverfolgung; 7 Migration und Grenze; 8 Justiz und Demokratie |
| `nst_datenart` | Datenart | Personenbezogene Daten; Besondere Kategorien (Art. 9 DSGVO); Beschäftigtendaten; Patientendaten; Kundendaten; Betriebs- und Sensordaten; Keine personenbezogenen Daten |
| `nst_massnahme_typ` | Maßnahmentyp | Technisch; Organisatorisch; Dokumentation; Schulung; Vertraglich |
| `nst_massnahme_status` | Maßnahmenstatus | Offen; In Arbeit; Erledigt; Entfallen |
| `nst_schulung_status` | Schulungsstatus | Geplant; Abgeschlossen; Überfällig |
