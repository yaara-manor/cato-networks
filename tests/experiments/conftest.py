import pytest

from experiments.llm.common import Query, load_queries


@pytest.fixture(scope="session")
def queries() -> dict[str, Query]:
    return {q["id"]: q for q in load_queries()}
