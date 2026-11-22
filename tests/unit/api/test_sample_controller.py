import uuid
from unittest.mock import create_autospec

import pytest
from dependency_injector import providers
from refractometer_common.sample import (
    CreateSampleRequest,
    Sample,
    SampleClientConnectionException,
    SampleClientException,
    SampleClientInterface,
    SampleClientInvalidResponseException,
    SampleClientTimeoutException,
    SampleNotFoundException,
    SellmeierCoefficients,
)

from api.app import container
from tests.unit.conftest import LEAK

pytestmark = pytest.mark.unit

SAMPLE_ID = uuid.uuid4()
B = [1.03961212, 0.231792344, 1.01046945]
C = [0.00600069867, 0.0200179144, 103.560653]
BODY = {"name": "N-BK7", "sellmeier_coefficients": {"B": B, "C": C}}


def make_sample(sample_id: uuid.UUID = SAMPLE_ID, name: str = "N-BK7") -> Sample:
    return Sample(
        id=sample_id,
        name=name,
        sellmeier_coefficients=SellmeierCoefficients(B=B, C=C),
    )


def as_json(sample: Sample) -> dict:
    return sample.model_dump(mode="json")


@pytest.fixture
def sample_client():
    mock = create_autospec(SampleClientInterface, instance=True)
    with container.sample_client.override(providers.Object(mock)):
        yield mock


# (http method, url, json body, client method)
ENDPOINTS = [
    ("GET", "/api/samples", None, "get_all_samples"),
    ("GET", f"/api/sample/{SAMPLE_ID}", None, "get_sample"),
    ("POST", "/api/sample", BODY, "create_sample"),
    ("PATCH", f"/api/sample/{SAMPLE_ID}", BODY, "update_sample"),
    ("DELETE", f"/api/sample/{SAMPLE_ID}", None, "delete_sample"),
]
ENDPOINT_IDS = [f"{m} {u}" for m, u, _, _ in ENDPOINTS]


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    @pytest.mark.parametrize(
        ("error", "status_code", "detail"),
        [
            (SampleClientTimeoutException, 504, "Sample service timed out"),
            (SampleClientConnectionException, 503, "Sample service unavailable"),
            (
                SampleClientInvalidResponseException,
                502,
                "Sample service returned an invalid response",
            ),
            (SampleClientException, 500, "Internal error in sample service"),
        ],
    )
    def test_client_errors_are_mapped(
        self, client, sample_client, method, url, body, client_method, error, status_code, detail
    ):
        getattr(sample_client, client_method).side_effect = error(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert LEAK not in response.text

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS[1:], ids=ENDPOINT_IDS[1:]
    )
    def test_not_found(self, client, sample_client, method, url, body, client_method):
        getattr(sample_client, client_method).side_effect = SampleNotFoundException(LEAK, 404)

        response = client.request(method, url, json=body)

        assert response.status_code == 404
        assert response.json() == {"detail": "Sample not found"}

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_unexpected_errors_do_not_leak(
        self, client, sample_client, method, url, body, client_method
    ):
        getattr(sample_client, client_method).side_effect = RuntimeError(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == 500
        assert LEAK not in response.text


class TestAuth:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_requires_authentication(
        self, anonymous_client, sample_client, method, url, body, client_method
    ):
        response = anonymous_client.request(method, url, json=body)

        assert response.status_code == 401
        getattr(sample_client, client_method).assert_not_called()


class TestGetSamples:
    def test_returns_all_samples(self, client, sample_client):
        samples = [make_sample(), make_sample(uuid.uuid4(), "F2")]
        sample_client.get_all_samples.return_value = samples

        response = client.get("/api/samples")

        assert response.status_code == 200
        assert response.json() == [as_json(s) for s in samples]

    def test_empty_list(self, client, sample_client):
        sample_client.get_all_samples.return_value = []

        response = client.get("/api/samples")

        assert response.status_code == 200
        assert response.json() == []

    def test_skips_samples_failing_dto_validation(self, client, sample_client):
        valid = make_sample()
        invalid = Sample.model_construct(id=uuid.uuid4(), name=None, sellmeier_coefficients=None)
        sample_client.get_all_samples.return_value = [invalid, valid]

        response = client.get("/api/samples")

        assert response.status_code == 200
        assert response.json() == [as_json(valid)]


class TestGetSample:
    def test_returns_sample(self, client, sample_client):
        sample_client.get_sample.return_value = make_sample()

        response = client.get(f"/api/sample/{SAMPLE_ID}")

        assert response.status_code == 200
        assert response.json() == as_json(make_sample())
        sample_client.get_sample.assert_called_once_with(str(SAMPLE_ID))

    def test_invalid_id_is_rejected(self, client, sample_client):
        response = client.get("/api/sample/not-a-uuid")

        assert response.status_code == 422
        sample_client.get_sample.assert_not_called()

    def test_invalid_upstream_object_is_bad_gateway(self, client, sample_client):
        sample_client.get_sample.return_value = Sample.model_construct(
            id=SAMPLE_ID, name=None, sellmeier_coefficients=None
        )

        response = client.get(f"/api/sample/{SAMPLE_ID}")

        assert response.status_code == 502
        assert response.json() == {"detail": "Sample service returned an invalid response"}


class TestCreateSample:
    def test_creates_sample(self, client, sample_client):
        sample_client.create_sample.return_value = make_sample()

        response = client.post("/api/sample", json=BODY)

        assert response.status_code == 201
        assert response.json() == as_json(make_sample())
        sample_client.create_sample.assert_called_once_with(
            CreateSampleRequest(name="N-BK7", B=B, C=C)
        )

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"name": "x"},
            {"sellmeier_coefficients": {"B": B, "C": C}},
            {"name": "", "sellmeier_coefficients": {"B": B, "C": C}},
            {"name": "x", "sellmeier_coefficients": {"B": B[:2], "C": C}},
            {"name": "x", "sellmeier_coefficients": {"B": B, "C": [*C, 1.0]}},
            {"name": "x", "sellmeier_coefficients": {"B": ["a", "b", "c"], "C": C}},
        ],
    )
    def test_invalid_body_is_rejected(self, client, sample_client, body):
        response = client.post("/api/sample", json=body)

        assert response.status_code == 422
        sample_client.create_sample.assert_not_called()


class TestUpdateSample:
    def test_updates_sample(self, client, sample_client):
        updated = make_sample(name="N-BK7 (updated)")
        sample_client.update_sample.return_value = updated

        response = client.patch(
            f"/api/sample/{SAMPLE_ID}", json={**BODY, "name": "N-BK7 (updated)"}
        )

        assert response.status_code == 200
        assert response.json() == as_json(updated)
        sample_client.update_sample.assert_called_once_with(updated)

    def test_id_is_taken_from_path(self, client, sample_client):
        sample_client.update_sample.return_value = make_sample()

        client.patch(f"/api/sample/{SAMPLE_ID}", json={**BODY, "id": str(uuid.uuid4())})

        (sent,) = sample_client.update_sample.call_args.args
        assert sent.id == SAMPLE_ID

    def test_invalid_id_is_rejected(self, client, sample_client):
        response = client.patch("/api/sample/not-a-uuid", json=BODY)

        assert response.status_code == 422
        sample_client.update_sample.assert_not_called()

    def test_invalid_body_is_rejected(self, client, sample_client):
        body = {"name": "x", "sellmeier_coefficients": {"B": B, "C": C[:1]}}

        response = client.patch(f"/api/sample/{SAMPLE_ID}", json=body)

        assert response.status_code == 422
        sample_client.update_sample.assert_not_called()


class TestDeleteSample:
    def test_deletes_sample(self, client, sample_client):
        sample_client.delete_sample.return_value = None

        response = client.delete(f"/api/sample/{SAMPLE_ID}")

        assert response.status_code == 204
        assert response.content == b""
        sample_client.delete_sample.assert_called_once_with(str(SAMPLE_ID))

    def test_invalid_id_is_rejected(self, client, sample_client):
        response = client.delete("/api/sample/not-a-uuid")

        assert response.status_code == 422
        sample_client.delete_sample.assert_not_called()
