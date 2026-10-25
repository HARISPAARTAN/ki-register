"""The documentation of milestone 1 is complete and consistent: the two READMEs, the decision records, the changelog and the links."""

import datetime
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README_DE = (ROOT / "README.md").read_text(encoding="utf-8")
README_EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
MARKDOWN = [ROOT / "README.md", ROOT / "README.en.md", ROOT / "docs" / "erd.md", ROOT / "docs" / "nachbau-anleitung.md",
            ROOT / "docs" / "CHANGELOG.md", *sorted((ROOT / "docs" / "decisions").glob("ADR-*.md"))]
ISO_DATE = r"\d{4}-\d{2}-\d{2}"
ADR_STATUSES = {"vorgeschlagen", "angenommen", "abgelöst", "verworfen"}
ADR_NAMES = {"ADR-001-dataverse-statt-sharepoint.md", "ADR-002-code-first-provisionierung.md", "ADR-003-alm-ohne-pipelines.md"}


def test_each_readme_links_to_the_other_at_the_top():
    assert "[README.en.md](README.en.md)" in "\n".join(README_DE.splitlines()[:6])
    assert "[README.md](README.md)" in "\n".join(README_EN.splitlines()[:6])


def test_both_readmes_carry_the_disclaimer_the_legal_state_and_the_status():
    assert "keine Rechtsberatung" in README_DE and "not legal advice" in README_EN
    assert ("Rechtsstand der Einstufungen: Verordnung (EU) 2024/1689 in der Fassung der Verordnung (EU) 2026/1744, "
            "Stand 2026-10-25; keine Rechtsberatung.") in README_DE
    assert ("Legal state of the classifications: Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744, "
            "as of 2026-10-25; not legal advice.") in README_EN
    assert "Meilenstein 1" in README_DE and "milestone 1" in README_EN


def test_the_german_readme_is_german_only_and_the_english_twin_has_the_same_sections():
    assert "## Setup (English)" not in README_DE and "ALM (English)" not in README_DE
    headings_de = [h for h in re.findall(r"^## (.+)$", README_DE, re.M)]
    headings_en = [h for h in re.findall(r"^## (.+)$", README_EN, re.M)]
    assert len(headings_de) == len(headings_en) == 11
    for heading in ("Die vier Befehle", "Rollenmodell", "Screenshots (Platzhalter)", "Frist der Entwicklerumgebungen und Nachbau"):
        assert f"## {heading}" in README_DE
    for heading in ("The four commands", "Role model", "Screenshots (placeholders)", "Environment deadline and rebuild"):
        assert f"## {heading}" in README_EN


@pytest.mark.parametrize("readme", [README_DE, README_EN], ids=["de", "en"])
def test_each_readme_names_the_commands_the_workflows_the_secrets_and_the_deadlines(readme):
    for command in ("bootstrap", "apply", "seed", "verify"):
        assert f"`{command}" in readme
    for workflow in ("ci.yml", "export-solution.yml", "import-dev.yml", "deploy-test.yml"):
        assert f"`{workflow}`" in readme
    for secret in ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET", "DATAVERSE_URL_DEV", "DATAVERSE_URL_TEST"):
        assert f"`{secret}`" in readme
    for date in ("2026-11-15", "2026-12-15", "2027-01-15"):
        assert date in readme
    for role in ("nst KI-Governance", "nst Fachbereich", "nst Leser", "nst Datenbesitz"):
        assert role in readme
    assert "```mermaid\nflowchart LR" in readme
    assert "apply --only security" in readme and "apply --only auditing" in readme and "import-dev.yml" in readme and "force-overwrite" in readme
    assert "festgelegt" in readme or "pinned to a commit SHA" in readme  # third-party actions are pinned to commit SHAs (T8-D1)
    assert "gepinnt" not in readme


def test_the_register_section_gives_the_seed_figures_of_the_spec():
    assert "20 KI-Systeme" in README_DE and "| **Summe** | **20** | **1** | **5** | **3** | **11** |" in README_DE
    assert "20 AI systems" in README_EN and "| **Total** | **20** | **1** | **5** | **3** | **11** |" in README_EN
    assert README_DE.count("| Projektmanagement |") == 7 and README_DE.count("| Energie |") == 7 and README_DE.count("| Klinikum |") == 6
    assert README_EN.count("| Projektmanagement |") == 7 and README_EN.count("| Energie |") == 7 and README_EN.count("| Klinikum |") == 6


def test_the_readmes_state_the_rebuild_order_as_derived_and_not_exercised():
    assert "noch nicht durchgespielt" in README_DE and "nicht auf einer frischen Umgebung erprobt" in README_DE
    assert "not yet exercised on a fresh environment" in README_EN


def test_the_screenshot_list_is_the_same_in_both_readmes_and_asks_for_the_shots_before_the_suspension():
    files_de = re.findall(r"`(\d\d-[a-z-]+\.png)`", README_DE)
    files_en = re.findall(r"`(\d\d-[a-z-]+\.png)`", README_EN)
    assert files_de == files_en and len(files_de) == 12
    assert "vor dem 2026-12-15 aufnehmen" in README_DE and "before 2026-12-15" in README_EN


@pytest.mark.parametrize("adr", sorted((ROOT / "docs" / "decisions").glob("ADR-*.md")), ids=lambda p: p.name[:7])
def test_each_decision_record_has_date_status_context_decision_and_consequences(adr):
    text = adr.read_text(encoding="utf-8")
    day = re.search(rf"^- Datum: ({ISO_DATE})$", text, re.M)
    assert day, "Datum fehlt oder ist kein ISO-Datum"
    datetime.date.fromisoformat(day.group(1))  # a real calendar date
    status = re.search(r"^- Status: (\S+)", text, re.M)
    assert status and status.group(1) in ADR_STATUSES, status and status.group(1)
    for heading in ("## Kontext", "## Entscheidung", "## Folgen"):
        assert heading in text, heading


def test_the_decision_records_of_milestone_1_exist_under_their_names():
    names = {p.name for p in (ROOT / "docs" / "decisions").glob("ADR-*.md")}
    assert ADR_NAMES <= names  # later milestones add records


def test_the_changelog_keeps_the_v0_1_0_section_and_has_a_dated_section_for_the_repository_version():
    changelog = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(rf"^## v(\d+\.\d+\.\d+) \(({ISO_DATE})\) .+$", changelog, re.M)  # the date of a release is set when it is tagged
    for _, day in headings:
        datetime.date.fromisoformat(day)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert version in {v for v, _ in headings}, f"CHANGELOG hat keinen Abschnitt v{version}"
    assert re.search(rf"^## v0\.1\.0 \({ISO_DATE}\) Meilenstein 1 Registerkern$", changelog, re.M)
    for n in range(1, 10):
        assert re.search(rf"^{n}\. \*\*", changelog, re.M), n


def test_the_rebuild_guide_follows_the_manual_order_and_leaves_room_for_milestones_2_to_4():
    guide = (ROOT / "docs" / "nachbau-anleitung.md").read_text(encoding="utf-8")
    order = ["Herausgeber und Lösung", "Auswahlfelder", "Tabellen und Spalten", "Beziehungen", "Unternehmenseinheiten und Besitzerteams",
             "Sicherheitsrollen", "Spaltensicherheitsprofil und Zuweisung", "Ansichten", "Formulare", "Diagramme", "Dashboard",
             "App, Sitemap und Rollen der App", "Seed-Import", "Export", "Auditing der Umgebung und Prüfung"]
    headings = re.findall(r"^### Schritt (\d+): (.+)$", guide, re.M)
    assert [(int(n), title) for n, title in headings] == list(enumerate(order, start=1))
    for line in ("## Meilenstein 2:", "## Meilenstein 3:", "## Meilenstein 4:"):
        assert line in guide
    for definition in ("choices.toml", "tables.toml", "relationships.toml", "security.toml", "app.toml", "config.toml"):
        assert definition in guide
    assert "abgeleitet und noch nicht auf einer frischen Umgebung durchgespielt" in guide
    assert guide.index("kiregister apply --env dev --only security") > guide.index("gh workflow run import-dev.yml")  # import first (T8-D4)


def _text(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def _rebuild_order(readme):
    """The first code span of every step in the numbered rebuild list of a README."""
    block = re.search(r"^1\. .*?(?:\n\n|\Z)", readme, re.M | re.S).group(0)
    return [re.search(r"`([^`]+)`", step).group(1) for step in re.findall(r"^\d+\. (.+)$", block, re.M)]


def test_apply_only_auditing_has_its_place_in_every_listing_of_the_rebuild_order():
    """bootstrap, import, apply --only security, apply --only auditing, seed, verify: in both READMEs (same steps), the guide, ADR-002, CHANGELOG."""
    assert _rebuild_order(README_DE) == _rebuild_order(README_EN) == [
        "bootstrap", "gh workflow run import-dev.yml", "apply --only security", "apply --only auditing", "seed", "verify"]
    sequence = "`apply --only security`, `apply --only auditing`, `seed`, `verify`"
    for text in (README_DE, README_EN, _text("docs", "decisions", "ADR-002-code-first-provisionierung.md"), _text("docs", "CHANGELOG.md")):
        assert sequence in text
    guide = _text("docs", "nachbau-anleitung.md")
    commands = ["kiregister apply --env dev --only security", "kiregister apply --env dev --only auditing", "kiregister seed --env dev",
                "kiregister verify --env dev"]
    positions = [guide.index(command) for command in commands]
    assert positions == sorted(positions)


AUDIT_DOCUMENTS = [("README.md",), ("README.en.md",), ("docs", "CHANGELOG.md"), ("docs", "nachbau-anleitung.md"),
                   ("docs", "decisions", "ADR-001-dataverse-statt-sharepoint.md"), ("docs", "decisions", "ADR-002-code-first-provisionierung.md"),
                   ("docs", "decisions", "ADR-003-alm-ohne-pipelines.md")]


@pytest.mark.parametrize("parts", AUDIT_DOCUMENTS, ids=lambda parts: parts[-1])
def test_the_documents_say_that_apply_only_auditing_switched_environment_auditing_on_and_when(parts):
    text = _text(*parts)
    assert "--only auditing" in text and "2026-10-26" in text
    for stale in ("setzt der Code nicht", "does not switch on auditing", "nicht im Code"):  # wording from before the switch became code
        assert stale not in text, stale


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_the_documents_contain_no_e_mail_address_outside_the_fictional_domain(path):
    assert not re.findall(r"[\w.+-]+@(?!nordstern\.example)[a-z0-9-]+\.[a-z.]{2,}", path.read_text(encoding="utf-8"), re.I), path.name


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_relative_links_resolve(path):
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)", text):
        assert (path.parent / target.split("#")[0]).exists(), f"{path.name}: {target}"


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_every_mermaid_block_is_closed_and_starts_with_a_known_diagram_type(path):
    text = path.read_text(encoding="utf-8")
    assert text.count("```") % 2 == 0, path.name
    for block in re.findall(r"```mermaid\n(.*?)\n```", text, re.S):
        assert block.split("\n", 1)[0] in ("erDiagram", "flowchart LR"), path.name
