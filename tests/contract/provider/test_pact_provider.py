"""Verify the gateway against the frontend contract in ``tests/contract/pacts``."""

import socket
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any, Literal

import pytest
import uvicorn
from pact import Verifier

from api.app import app, container
from auth.guards import get_user
from tests.contract.provider.provider_states import PACT_USER, STATES, ClientMocks

pytestmark = pytest.mark.pact

PACT_FILE = (
    Path(__file__).parent.parent / "pacts" / "refractometer-frontend-refractometer-api-gateway.json"
)
PROVIDER = "refractometer-api-gateway"
HOST = "127.0.0.1"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def provider_url() -> Generator[str]:
    app.dependency_overrides[get_user] = lambda: PACT_USER
    ClientMocks.create().install(container)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("Gateway did not start")
        time.sleep(0.05)

    yield f"http://{HOST}:{port}"

    server.should_exit = True
    thread.join(timeout=10)
    app.dependency_overrides.pop(get_user, None)
    for name in ("image", "sample", "spectrum", "queue", "result"):
        getattr(container, f"{name}_client").reset_override()


def provider_state(
    state: str,
    action: Literal["setup", "teardown"],
    parameters: dict[str, Any] | None,
) -> None:
    # Fresh mocks for every interaction, so nothing leaks between them.
    mocks = ClientMocks.create()
    mocks.install(container)

    if action == "teardown" or not state:
        return

    try:
        setup = STATES[state]
    except KeyError:
        msg = f"Unknown provider state: {state!r}"
        raise ValueError(msg) from None

    setup(mocks, parameters or {})


def test_gateway_honours_frontend_contract(provider_url: str):
    verifier = (
        Verifier(PROVIDER, host=HOST)
        .add_source(PACT_FILE)
        .add_transport(url=provider_url)
        .state_handler(provider_state, teardown=True)
    )

    verifier.verify()
