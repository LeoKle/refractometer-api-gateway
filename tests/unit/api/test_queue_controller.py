import uuid
from datetime import UTC, datetime
from unittest.mock import create_autospec

import pytest
from dependency_injector import providers
from refractometer_common.queue import (
    QueueClientConnectionException,
    QueueClientException,
    QueueClientInterface,
    QueueClientInvalidResponseException,
    QueueClientTimeoutException,
    SimulationQueueElement,
    SimulationQueueElementCreate,
)

from api.app import container
from tests.unit.conftest import LEAK

pytestmark = pytest.mark.unit

QUEUE_ID = uuid.uuid4()
ISSUED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
PARAMETERS = {"sample_id": str(uuid.uuid4()), "spectrum_id": str(uuid.uuid4()), "angle": 45.0}
CALLBACK_URL = "https://example.com/callback"
BODY = {"parameters": PARAMETERS, "callback_url": CALLBACK_URL, "name": "BK7 @ 45°"}


def make_element(
    element_id: uuid.UUID = QUEUE_ID,
    name: str | None = "BK7 @ 45°",
    index: int | None = 0,
    issuer: str | None = None,
) -> SimulationQueueElement:
    return SimulationQueueElement(
        id=element_id,
        parameters=PARAMETERS,
        issued_at=ISSUED_AT,
        name=name,
        index=index,
        being_processed=False,
        issuer=issuer,
        callback_url=CALLBACK_URL,
    )


def as_json(element: SimulationQueueElement) -> dict:
    return element.model_dump(mode="json")


@pytest.fixture
def queue_client():
    mock = create_autospec(QueueClientInterface, instance=True)
    with container.queue_client.override(providers.Object(mock)):
        yield mock


# (http method, url, json body, client method)
ENDPOINTS = [
    ("GET", "/api/queued", None, "get_queued_simulations"),
    ("POST", "/api/queue", BODY, "create_queued_simulation"),
]
ENDPOINT_IDS = [f"{m} {u}" for m, u, _, _ in ENDPOINTS]


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    @pytest.mark.parametrize(
        ("error", "status_code", "detail"),
        [
            (QueueClientTimeoutException, 504, "Queue service timed out"),
            (QueueClientConnectionException, 503, "Queue service unavailable"),
            (
                QueueClientInvalidResponseException,
                502,
                "Queue service returned an invalid response",
            ),
            (QueueClientException, 500, "Internal error while fetching Queue"),
        ],
    )
    def test_client_errors_are_mapped(
        self, client, queue_client, method, url, body, client_method, error, status_code, detail
    ):
        getattr(queue_client, client_method).side_effect = error(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert LEAK not in response.text

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_unexpected_errors_do_not_leak(
        self, client, queue_client, method, url, body, client_method
    ):
        getattr(queue_client, client_method).side_effect = RuntimeError(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == 500
        assert LEAK not in response.text


class TestAuth:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_requires_authentication(
        self, anonymous_client, queue_client, method, url, body, client_method
    ):
        response = anonymous_client.request(method, url, json=body)

        assert response.status_code == 401
        getattr(queue_client, client_method).assert_not_called()


class TestGetQueuedSimulations:
    def test_returns_all_queued_simulations(self, client, queue_client):
        elements = [make_element(), make_element(uuid.uuid4(), name=None, index=1)]
        queue_client.get_queued_simulations.return_value = elements

        response = client.get("/api/queued")

        assert response.status_code == 200
        assert response.json() == [as_json(e) for e in elements]
        queue_client.get_queued_simulations.assert_called_once_with()

    def test_empty_list(self, client, queue_client):
        queue_client.get_queued_simulations.return_value = []

        response = client.get("/api/queued")

        assert response.status_code == 200
        assert response.json() == []

    def test_skips_elements_failing_dto_validation(self, client, queue_client):
        valid = make_element()
        invalid = SimulationQueueElement.model_construct(
            id=uuid.uuid4(), parameters=None, issued_at=None
        )
        queue_client.get_queued_simulations.return_value = [invalid, valid]

        response = client.get("/api/queued")

        assert response.status_code == 200
        assert response.json() == [as_json(valid)]


class TestQueueSimulation:
    def test_queues_simulation(self, client, queue_client, user):
        created = make_element(issuer=str(user.id))
        queue_client.create_queued_simulation.return_value = created

        response = client.post("/api/queue", json=BODY)

        assert response.status_code == 200
        assert response.json() == as_json(created)
        queue_client.create_queued_simulation.assert_called_once_with(
            SimulationQueueElementCreate(
                parameters=PARAMETERS,
                issuer=str(user.id),
                callback_url=CALLBACK_URL,
                name="BK7 @ 45°",
            )
        )

    def test_optional_fields_default_to_none(self, client, queue_client, user):
        queue_client.create_queued_simulation.return_value = make_element(name=None)

        response = client.post("/api/queue", json={"parameters": PARAMETERS})

        assert response.status_code == 200
        queue_client.create_queued_simulation.assert_called_once_with(
            SimulationQueueElementCreate(
                parameters=PARAMETERS, issuer=str(user.id), callback_url=None, name=None
            )
        )

    def test_issuer_is_taken_from_authenticated_user(self, client, queue_client, user):
        queue_client.create_queued_simulation.return_value = make_element()

        client.post("/api/queue", json={**BODY, "issuer": "someone-else"})

        (sent,) = queue_client.create_queued_simulation.call_args.args
        assert sent.issuer == str(user.id)

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"parameters": None},
            {"parameters": "not-a-dict"},
            {"parameters": [1, 2, 3]},
            {"parameters": PARAMETERS, "name": 1},
            {"parameters": PARAMETERS, "callback_url": ["x"]},
        ],
    )
    def test_invalid_body_is_rejected(self, client, queue_client, body):
        response = client.post("/api/queue", json=body)

        assert response.status_code == 422
        queue_client.create_queued_simulation.assert_not_called()

    def test_invalid_upstream_object_is_bad_gateway(self, client, queue_client):
        queue_client.create_queued_simulation.return_value = SimulationQueueElement.model_construct(
            id=QUEUE_ID, parameters=None, issued_at=None
        )

        response = client.post("/api/queue", json=BODY)

        assert response.status_code == 502
        assert response.json() == {"detail": "Queue service returned an invalid response"}
