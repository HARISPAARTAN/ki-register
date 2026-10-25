"""TOML definitions to dataclasses. The TOML files are the single source of names and labels."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

COLUMN_TYPES = {"string", "memo", "int", "bool", "date", "datetime", "url", "email", "choice", "multichoice", "autonumber", "formula"}
DEPTHS = {"Basic", "Local", "Deep", "Global"}
PRIVILEGES = ("create", "read", "write", "delete", "append", "appendto", "assign", "share")


@dataclass(frozen=True)
class Choice:
    schema: str
    display: str
    values: list[str]


@dataclass(frozen=True)
class Column:
    schema: str
    display: str
    type: str
    length: int = 100
    choice: str | None = None
    format: str | None = None
    formula: str | None = None
    result: str | None = None
    required: bool = False
    secured: bool = False
    display_en: str | None = None


@dataclass(frozen=True)
class Primary:
    schema: str
    display: str
    length: int = 200


@dataclass(frozen=True)
class Table:
    schema: str
    display: str
    plural: str
    primary: Primary
    columns: list[Column]
    audit: bool = False
    display_en: str | None = None
    plural_en: str | None = None


@dataclass(frozen=True)
class Lookup:
    """A lookup column. `schema` is the Pascal-cased schema name sent to Dataverse (nst_KISystem);
    `logical` is the lower-case logical name Dataverse derives from it (nst_kisystem), used in views, forms and queries."""

    schema: str
    display: str
    required: bool = False

    @property
    def logical(self) -> str:
        return self.schema.lower()


@dataclass(frozen=True)
class Relationship:
    schema: str
    referenced: str
    referencing: str
    lookup: Lookup
    delete: str = "RemoveLink"


@dataclass(frozen=True)
class Role:
    name: str
    tables: dict[str, dict[str, str]]


@dataclass(frozen=True)
class ColumnSecurity:
    profile: str
    columns: list[tuple[str, str]]
    roles_with_access: list[str]


@dataclass(frozen=True)
class Security:
    business_units: list[str]
    roles: list[Role]
    column_security: ColumnSecurity


@dataclass(frozen=True)
class ViewFilter:
    column: str
    op: str
    values: list[str]


@dataclass(frozen=True)
class View:
    table: str
    name: str
    columns: list[str]
    filter: list[ViewFilter] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    default: bool = False


@dataclass(frozen=True)
class Subgrid:
    table: str
    view: str
    lookup: str


@dataclass(frozen=True)
class Tab:
    name: str
    sections: list[list[str]] = field(default_factory=list)
    subgrids: list[Subgrid] = field(default_factory=list)


@dataclass(frozen=True)
class Form:
    table: str
    name: str
    tabs: list[Tab]


@dataclass(frozen=True)
class Chart:
    table: str
    name: str
    kind: str
    groupby: str
    series: str | None = None


@dataclass(frozen=True)
class DashboardComponent:
    table: str
    chart: str | None = None
    list: str | None = None
    view: str | None = None


@dataclass(frozen=True)
class Dashboard:
    name: str
    components: list[DashboardComponent]


@dataclass(frozen=True)
class Area:
    id: str
    title: str
    tables: list[str] = field(default_factory=list)
    dashboard: str | None = None


@dataclass(frozen=True)
class AppDef:
    unique_name: str
    display: str
    description: str
    areas: list[Area]
    views: list[View]
    forms: list[Form]
    charts: list[Chart]
    dashboard: Dashboard


@dataclass(frozen=True)
class Definitions:
    choices: list[Choice]
    tables: list[Table]
    relationships: list[Relationship]
    security: Security
    app: AppDef

    def table(self, schema: str) -> Table:
        return next(t for t in self.tables if t.schema == schema)

    def choice(self, schema: str) -> Choice:
        return next(c for c in self.choices if c.schema == schema)

    def lookups_of(self, table: str) -> list[Relationship]:
        return [r for r in self.relationships if r.referencing == table]

    def relationship_for(self, referencing: str, lookup: str) -> Relationship:
        """Find the relationship by referencing table and lookup name (logical or schema casing)."""
        return next(r for r in self.relationships if r.referencing == referencing and r.lookup.logical == lookup.lower())


def _read(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _column(raw: dict) -> Column:
    if raw["type"] not in COLUMN_TYPES:
        raise ValueError(f"Spaltentyp {raw['type']!r} unbekannt ({raw['schema']})")
    if raw["type"] in ("choice", "multichoice") and "choice" not in raw:
        raise ValueError(f"{raw['schema']}: choice fehlt")
    return Column(**{k: v for k, v in raw.items() if k in Column.__dataclass_fields__})


def load_definitions(directory: Path) -> Definitions:
    d = Path(directory)
    choices = [Choice(**c) for c in _read(d / "choices.toml")["choice"]]
    tables = []
    for raw in _read(d / "tables.toml")["table"]:
        prim = raw["primary"]
        tables.append(Table(schema=raw["schema"], display=raw["display"], plural=raw["plural"],
                            primary=Primary(prim["schema"], prim["display"], int(prim.get("length", 200))),
                            columns=[_column(c) for c in raw.get("column", [])], audit=bool(raw.get("audit", False)),
                            display_en=raw.get("display_en"), plural_en=raw.get("plural_en")))
    rels = []
    for raw in _read(d / "relationships.toml")["relationship"]:
        if raw.get("delete", "RemoveLink") not in ("Cascade", "RemoveLink", "Restrict"):
            raise ValueError(f"{raw['schema']}: delete muss Cascade, RemoveLink oder Restrict sein")
        lk = raw["lookup"]
        rels.append(Relationship(raw["schema"], raw["referenced"], raw["referencing"],
                                 Lookup(lk["schema"], lk["display"], bool(lk.get("required", False))), raw.get("delete", "RemoveLink")))
    sec_raw = _read(d / "security.toml")
    roles = []
    for r in sec_raw["role"]:
        for table, privs in r["tables"].items():
            for name, depth in privs.items():
                if name not in PRIVILEGES or depth not in DEPTHS:
                    raise ValueError(f"Rolle {r['name']}: {table}.{name}={depth} ungueltig")
        roles.append(Role(r["name"], r["tables"]))
    cs = sec_raw["column_security"]
    security = Security(sec_raw["business_units"], roles,
                        ColumnSecurity(cs["profile"], [(c["table"], c["column"]) for c in cs["columns"]], cs["roles_with_access"]))
    app_raw = _read(d / "app.toml")
    views = [View(v["table"], v["name"], v["columns"], [ViewFilter(**f) for f in v.get("filter", [])], v.get("order", []), bool(v.get("default", False)))
             for v in app_raw.get("view", [])]
    forms = [Form(f["table"], f["name"], [Tab(t["name"], t.get("sections", []), [Subgrid(**s) for s in t.get("subgrids", [])]) for t in f["tabs"]])
             for f in app_raw.get("form", [])]
    charts = [Chart(**c) for c in app_raw.get("chart", [])]
    dash_raw = app_raw["dashboard"]
    dashboard = Dashboard(dash_raw["name"], [DashboardComponent(**c) for c in dash_raw["components"]])
    areas = [Area(a["id"], a["title"], a.get("tables", []), a.get("dashboard")) for a in app_raw["area"]]
    a = app_raw["app"]
    app = AppDef(a["unique_name"], a["display"], a["description"], areas, views, forms, charts, dashboard)
    return Definitions(choices, tables, rels, security, app)
