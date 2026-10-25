"""Shared fixtures of the unit tests."""

from pathlib import Path

import pytest

from kiregister.definitions import load_definitions

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def date_columns():
    """`date_columns(table)`: names of the date and datetime columns of a table, i.e. the cells that the seed shifts to the reference date."""
    defs = load_definitions(ROOT / "provision" / "definitions")
    return lambda table: [c.schema for c in defs.table(table).columns if c.type in ("date", "datetime")]
