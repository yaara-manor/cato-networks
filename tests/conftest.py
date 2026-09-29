import os
import pytest


@pytest.fixture(autouse=True)
def default_database_url(monkeypatch):
    if "DATABASE_URL" not in os.environ:
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://kb:kb@localhost:5432/kb",
        )
