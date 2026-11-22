import uuid
from unittest.mock import create_autospec

import pytest
from dependency_injector import providers
from refractometer_common.spectrum import (
    CreateSpectrumRequest,
    Spectrum,
    SpectrumClientConnectionException,
    SpectrumClientException,
    SpectrumClientInterface,
    SpectrumClientInvalidResponseException,
    SpectrumClientTimeoutException,
    SpectrumNotFoundException,
)

from api.app import container
from tests.unit.conftest import LEAK

pytestmark = pytest.mark.unit

SPECTRUM_ID = uuid.uuid4()
WAVELENGTHS = [450.0, 550.0, 650.0]
INTENSITIES = [0.2, 1.0, 0.4]
BODY = {"name": "LED white", "wavelengths": WAVELENGTHS, "intensities": INTENSITIES}


def make_spectrum(spectrum_id: uuid.UUID = SPECTRUM_ID, name: str = "LED white") -> Spectrum:
    return Spectrum(
        id=spectrum_id,
        name=name,
        wavelengths=WAVELENGTHS,
        intensities=INTENSITIES,
    )


def as_json(spectrum: Spectrum) -> dict:
    return spectrum.model_dump(mode="json")


@pytest.fixture
def spectrum_client():
    mock = create_autospec(SpectrumClientInterface, instance=True)
    with container.spectrum_client.override(providers.Object(mock)):
        yield mock


# (http method, url, json body, client method)
ENDPOINTS = [
    ("GET", "/api/spectrums", None, "get_all_spectrums"),
    ("GET", f"/api/spectrum/{SPECTRUM_ID}", None, "get_spectrum"),
    ("POST", "/api/spectrum", BODY, "create_spectrum"),
    ("PATCH", f"/api/spectrum/{SPECTRUM_ID}", BODY, "update_spectrum"),
    ("DELETE", f"/api/spectrum/{SPECTRUM_ID}", None, "delete_spectrum"),
]
ENDPOINT_IDS = [f"{m} {u}" for m, u, _, _ in ENDPOINTS]


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    @pytest.mark.parametrize(
        ("error", "status_code", "detail"),
        [
            (SpectrumClientTimeoutException, 504, "Spectrum service timed out"),
            (SpectrumClientConnectionException, 503, "Spectrum service unavailable"),
            (
                SpectrumClientInvalidResponseException,
                502,
                "Spectrum service returned an invalid response",
            ),
            (SpectrumClientException, 500, "Internal error in spectrum service"),
        ],
    )
    def test_client_errors_are_mapped(
        self, client, spectrum_client, method, url, body, client_method, error, status_code, detail
    ):
        getattr(spectrum_client, client_method).side_effect = error(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert LEAK not in response.text

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS[1:], ids=ENDPOINT_IDS[1:]
    )
    def test_not_found(self, client, spectrum_client, method, url, body, client_method):
        getattr(spectrum_client, client_method).side_effect = SpectrumNotFoundException(LEAK, 404)

        response = client.request(method, url, json=body)

        assert response.status_code == 404
        assert response.json() == {"detail": "Spectrum not found"}

    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_unexpected_errors_do_not_leak(
        self, client, spectrum_client, method, url, body, client_method
    ):
        getattr(spectrum_client, client_method).side_effect = RuntimeError(LEAK)

        response = client.request(method, url, json=body)

        assert response.status_code == 500
        assert LEAK not in response.text


class TestAuth:
    @pytest.mark.parametrize(
        ("method", "url", "body", "client_method"), ENDPOINTS, ids=ENDPOINT_IDS
    )
    def test_requires_authentication(
        self, anonymous_client, spectrum_client, method, url, body, client_method
    ):
        response = anonymous_client.request(method, url, json=body)

        assert response.status_code == 401
        getattr(spectrum_client, client_method).assert_not_called()


class TestGetSpectrums:
    def test_returns_all_spectrums(self, client, spectrum_client):
        spectrums = [make_spectrum(), make_spectrum(uuid.uuid4(), "Halogen")]
        spectrum_client.get_all_spectrums.return_value = spectrums

        response = client.get("/api/spectrums")

        assert response.status_code == 200
        assert response.json() == [as_json(s) for s in spectrums]

    def test_empty_list(self, client, spectrum_client):
        spectrum_client.get_all_spectrums.return_value = []

        response = client.get("/api/spectrums")

        assert response.status_code == 200
        assert response.json() == []

    def test_skips_spectrums_failing_dto_validation(self, client, spectrum_client):
        valid = make_spectrum()
        invalid = Spectrum.model_construct(
            id=uuid.uuid4(), name=None, wavelengths=None, intensities=None
        )
        spectrum_client.get_all_spectrums.return_value = [invalid, valid]

        response = client.get("/api/spectrums")

        assert response.status_code == 200
        assert response.json() == [as_json(valid)]


class TestGetSpectrum:
    def test_returns_spectrum(self, client, spectrum_client):
        spectrum_client.get_spectrum.return_value = make_spectrum()

        response = client.get(f"/api/spectrum/{SPECTRUM_ID}")

        assert response.status_code == 200
        assert response.json() == as_json(make_spectrum())
        spectrum_client.get_spectrum.assert_called_once_with(str(SPECTRUM_ID))

    def test_invalid_id_is_rejected(self, client, spectrum_client):
        response = client.get("/api/spectrum/not-a-uuid")

        assert response.status_code == 422
        spectrum_client.get_spectrum.assert_not_called()

    def test_invalid_upstream_object_is_bad_gateway(self, client, spectrum_client):
        spectrum_client.get_spectrum.return_value = Spectrum.model_construct(
            id=SPECTRUM_ID, name=None, wavelengths=None, intensities=None
        )

        response = client.get(f"/api/spectrum/{SPECTRUM_ID}")

        assert response.status_code == 502
        assert response.json() == {"detail": "Spectrum service returned an invalid response"}


class TestCreateSpectrum:
    def test_creates_spectrum(self, client, spectrum_client):
        spectrum_client.create_spectrum.return_value = make_spectrum()

        response = client.post("/api/spectrum", json=BODY)

        assert response.status_code == 201
        assert response.json() == as_json(make_spectrum())
        spectrum_client.create_spectrum.assert_called_once_with(
            CreateSpectrumRequest(
                name="LED white", wavelengths=WAVELENGTHS, intensities=INTENSITIES
            )
        )

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"name": "x", "wavelengths": WAVELENGTHS},
            {"wavelengths": WAVELENGTHS, "intensities": INTENSITIES},
            {"name": "", "wavelengths": WAVELENGTHS, "intensities": INTENSITIES},
            {"name": "x", "wavelengths": [], "intensities": []},
            {"name": "x", "wavelengths": WAVELENGTHS, "intensities": INTENSITIES[:2]},
            {"name": "x", "wavelengths": ["a"], "intensities": [1.0]},
        ],
    )
    def test_invalid_body_is_rejected(self, client, spectrum_client, body):
        response = client.post("/api/spectrum", json=body)

        assert response.status_code == 422
        spectrum_client.create_spectrum.assert_not_called()


class TestUpdateSpectrum:
    def test_updates_spectrum(self, client, spectrum_client):
        updated = make_spectrum(name="LED warm")
        spectrum_client.update_spectrum.return_value = updated

        response = client.patch(f"/api/spectrum/{SPECTRUM_ID}", json={**BODY, "name": "LED warm"})

        assert response.status_code == 200
        assert response.json() == as_json(updated)
        spectrum_client.update_spectrum.assert_called_once_with(updated)

    def test_id_is_taken_from_path(self, client, spectrum_client):
        spectrum_client.update_spectrum.return_value = make_spectrum()

        client.patch(f"/api/spectrum/{SPECTRUM_ID}", json={**BODY, "id": str(uuid.uuid4())})

        (sent,) = spectrum_client.update_spectrum.call_args.args
        assert sent.id == SPECTRUM_ID

    def test_invalid_id_is_rejected(self, client, spectrum_client):
        response = client.patch("/api/spectrum/not-a-uuid", json=BODY)

        assert response.status_code == 422
        spectrum_client.update_spectrum.assert_not_called()

    def test_invalid_body_is_rejected(self, client, spectrum_client):
        body = {**BODY, "intensities": [1.0]}

        response = client.patch(f"/api/spectrum/{SPECTRUM_ID}", json=body)

        assert response.status_code == 422
        spectrum_client.update_spectrum.assert_not_called()


class TestDeleteSpectrum:
    def test_deletes_spectrum(self, client, spectrum_client):
        spectrum_client.delete_spectrum.return_value = None

        response = client.delete(f"/api/spectrum/{SPECTRUM_ID}")

        assert response.status_code == 204
        assert response.content == b""
        spectrum_client.delete_spectrum.assert_called_once_with(str(SPECTRUM_ID))

    def test_invalid_id_is_rejected(self, client, spectrum_client):
        response = client.delete("/api/spectrum/not-a-uuid")

        assert response.status_code == 422
        spectrum_client.delete_spectrum.assert_not_called()
