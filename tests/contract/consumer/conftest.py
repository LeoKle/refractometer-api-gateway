"""Consumer side of the contracts between the common layer and the microservices.

The gateway reaches the microservices only through the refractometer-common-layer
clients, so these tests run the real clients against a Pact mock server. The
recorded interactions end up in ``tests/contract/pacts`` (one file per provider),
next to the frontend contract. The microservices in refractometer-backend verify
themselves against these files.

A Pact handle is locked once it has been served, so every test builds its own
handle. The first write per provider in a session replaces the file, later
writes merge into it, so removed interactions do not linger.
"""

from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from pact import Pact

PACT_DIR = Path(__file__).parent.parent / "pacts"
CONSUMER = "refractometer-common-layer"

_written_this_session: set[str] = set()


def _pact_for(provider: str) -> Callable[[], Generator[Pact]]:
    def fixture() -> Generator[Pact]:
        pact = Pact(CONSUMER, provider).with_specification("V4")
        yield pact
        pact.write_file(PACT_DIR, overwrite=provider not in _written_this_session)
        _written_this_session.add(provider)

    return fixture


parameter_service_pact = pytest.fixture(
    _pact_for("parameter-service"), name="parameter_service_pact"
)
image_service_pact = pytest.fixture(_pact_for("image-service"), name="image_service_pact")
