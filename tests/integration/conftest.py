import os
from pathlib import Path

import pytest

from kiregister.auth import ClientCredentialTokens
from kiregister.client import DataverseClient
from kiregister.config import load_settings
from kiregister.definitions import load_definitions

pytestmark = pytest.mark.dataverse


@pytest.fixture(scope="session")
def settings():
    if not os.environ.get("DATAVERSE_URL_DEV"):
        pytest.skip("DATAVERSE_URL_DEV nicht gesetzt")
    return load_settings("dev", Path(__file__).resolve().parents[2])


@pytest.fixture(scope="session")
def defs(settings):
    return load_definitions(settings.definitions_dir)


@pytest.fixture(scope="session")
def client(settings):
    return DataverseClient(settings.api, ClientCredentialTokens(settings), solution=settings.solution)
