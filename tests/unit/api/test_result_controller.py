import uuid
from datetime import UTC, datetime
from unittest.mock import create_autospec

import pytest
from dependency_injector import providers
from refractometer_common.result import (
    SimulationResult,
    SimulationResultClientConnectionException,
    SimulationResultClientException,
    SimulationResultClientInterface,
    SimulationResultClientInvalidResponseException,
    SimulationResultClientTimeoutException,
    SimulationResultNotFoundException,
)

from api.app import container
from tests.unit.conftest import LEAK

pytestmark = pytest.mark.unit

RESULT_ID = uuid.uuid4()
IMAGE_ID = "665f1c2b9a1e4b0012345678"
PARAMETERS = {"sample_id": str(uuid.uuid4()), "spectrum_id": str(uuid.uuid4()), "angle": 45.0}
ISSUED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 1, 1, 12, 5, tzinfo=UTC)


def make_result(result_id: uuid.UUID = RESULT_ID, image_id: str = IMAGE_ID) -> SimulationResult:
    return SimulationResult(
        id=result_id,
        parameters=PARAMETERS,
        image_id=image_id,
        issued_at=ISSUED_AT,
        completed_at=COMPLETED_AT,
    )


def make_invalid_result(result_id: uuid.UUID = RESULT_ID) -> SimulationResult:
    return SimulationResult.model_construct(
        id=result_id, parameters=None, image_id=None, issued_at=None, completed_at=None
    )


def as_json(result: SimulationResult) -> dict:
    return result.model_dump(mode="json")


@pytest.fixture
def result_client():
    mock = create_autospec(SimulationResultClientInterface, instance=True)
    with container.result_client.override(providers.Object(mock)):
        yield mock


# (http method, url, json body, client method)
ENDPOINTS = [
    ("GET", "/api/results", None, "get_results"),
    ("GET", f"/api/result/{RESULT_ID}", None, "get_result"),
    ("DELETE", f"/api/result/{RESULT_ID}", None, "delete_result"),
]
ENDPOINT_IDS = [f"{m} {u}" for m, u, _, _ in ENDPOINTS]

CLIENT_ERRORS = [
    (SimulationResultClientTimeoutException, 504, "Result service timed out"),
    (SimulationResultClientConnectionException, 503, "Result service unavailable"),
    (
        SimulationResultClientInvalidResponseException,
        502,
        "Result service returned an invalid response",
    ),
]

INTERNAL_ERROR_DETAILS = {
    "get_results": "Internal error while fetching results",
    "get_result": "Internal error while fetching result",
    "delete_result": "Internal error while fetching result",
}


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    @pytest.mark.parametrize(("error", "status_code", "detail"), CLIENT_ERRORS)
    def test_client_errors_are_mapped(
        self, client, result_client, method, url, body, client_method, error, status_code, detail
    ):
        getattr(result_client, client_method).side_effect = error(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert LEAK not in response.text

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_generic_client_error_is_internal_error(
        self, client, result_client, method, url, body, client_method
    ):
        getattr(result_client, client_method).side_effect = SimulationResultClientException(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == 500
        assert response.json() == {"detail": INTERNAL_ERROR_DETAILS[client_method]}
        assert LEAK not in response.text

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method", "detail"),
        [
            ("GET", *ENDPOINTS[1][1:], f"Result {RESULT_ID} not found"),
            ("DELETE", *ENDPOINTS[2][1:], f"Result {RESULT_ID} not found while deleting"),
        ],
        ids=ENDPOINT_IDS[1:],
    )
    def test_not_found(self, client, result_client, method, url, body, client_method, detail):
        getattr(result_client, client_method).side_effect = SimulationResultNotFoundException(
            LEAK, 404
        )

        response = client.request(method, url, json=body)

        assert response.status_code == 404
        assert response.json() == {"detail": detail}
        assert LEAK not in response.text

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_unexpected_errors_do_not_leak(
        self, client, result_client, method, url, body, client_method
    ):
        getattr(result_client, client_method).side_effect = RuntimeError(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == 500
        assert LEAK not in response.text


class TestAuth:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_requires_authentication(
        self, anonymous_client, result_client, method, url, body, client_method
    ):
        response = anonymous_client.request(method, url, json=body)

        assert response.status_code == 401
        getattr(result_client, client_method).assert_not_called()


class TestGetResults:
    def test_returns_all_results(self, client, result_client):
        results = [make_result(), make_result(uuid.uuid4(), "665f1c2b9a1e4b0087654321")]
        result_client.get_results.return_value = results

        response = client.get("/api/results")

        assert response.status_code == 200
        assert response.json() == [as_json(r) for r in results]
        result_client.get_results.assert_called_once_with()

    def test_empty_list(self, client, result_client):
        result_client.get_results.return_value = []

        response = client.get("/api/results")

        assert response.status_code == 200
        assert response.json() == []

    def test_skips_results_failing_dto_validation(self, client, result_client):
        valid = make_result()
        result_client.get_results.return_value = [make_invalid_result(uuid.uuid4()), valid]

        response = client.get("/api/results")

        assert response.status_code == 200
        assert response.json() == [as_json(valid)]


class TestGetResult:
    def test_returns_result(self, client, result_client):
        result_client.get_result.return_value = make_result()

        response = client.get(f"/api/result/{RESULT_ID}")

        assert response.status_code == 200
        assert response.json() == as_json(make_result())
        result_client.get_result.assert_called_once_with(str(RESULT_ID))

    def test_invalid_upstream_object_is_bad_gateway(self, client, result_client):
        result_client.get_result.return_value = make_invalid_result()

        response = client.get(f"/api/result/{RESULT_ID}")

        assert response.status_code == 502
        assert response.json() == {"detail": "Result service returned an invalid response"}


class TestDeleteResult:
    def test_deletes_result(self, client, result_client):
        result_client.delete_result.return_value = None

        response = client.delete(f"/api/result/{RESULT_ID}")

        assert response.status_code == 200
        assert response.json() is None
        result_client.delete_result.assert_called_once_with(str(RESULT_ID))
