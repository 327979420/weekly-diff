"""Block real HTTP in every test; responses must come from local fixtures."""
from collections.abc import Iterator

import pytest
import responses


@pytest.fixture(autouse=True)
def offline_http() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock
