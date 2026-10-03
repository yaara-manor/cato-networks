from collections.abc import Iterator

import psycopg
import pytest

from core.config import settings
from tests.approval_desk import Desk


@pytest.fixture
def desk() -> Iterator[Desk]:
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        built = Desk.create(conn)
        yield built
        built.cleanup()


