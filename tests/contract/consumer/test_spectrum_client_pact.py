import uuid

import pytest
from pact import Pact, match
from refractometer_common.spectrum import (
    CreateSpectrumRequest,
    Spectrum,
    SpectrumClient,
    SpectrumNotFoundException,
)

pytestmark = pytest.mark.pact

SPECTRUM_ID = "4f8c2a1e-6b3d-4e7a-9c5f-2d1b8e3a7c90"
MISSING_SPECTRUM_ID = "00000000-0000-0000-0000-000000000000"
CREATED_ID = "7b1e9d3a-2c4f-4a6b-8e0d-5f7a9c1b3d2e"

WAVELENGTHS = [400.0, 500.0, 600.0]
INTENSITIES = [0.2, 0.9, 0.4]


def spectrum_body(spectrum_id: str = SPECTRUM_ID, name: str = "Test Spectrum PACT") -> dict:
    return {
        "id": match.uuid(spectrum_id),
        "name": match.str(name),
        "wavelengths": match.like(WAVELENGTHS, min=1),
        "intensities": match.like(INTENSITIES, min=1),
    }


def test_get_all_spectrums(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request for all spectrums")
        .given("spectrums exist")
        .with_request("GET", "/api/spectrums")
        .will_respond_with(200)
        .with_body(match.each_like(spectrum_body(), min=1), content_type="application/json")
    )

    with parameter_service_pact.serve() as srv:
        spectrums = SpectrumClient(str(srv.url)).get_all_spectrums()

    assert len(spectrums) == 1
    assert spectrums[0].id == uuid.UUID(SPECTRUM_ID)


def test_get_spectrum(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request for an existing spectrum")
        .given("a spectrum exists", id=SPECTRUM_ID)
        .with_request("GET", f"/api/spectrum/{SPECTRUM_ID}")
        .will_respond_with(200)
        .with_body(spectrum_body(), content_type="application/json")
    )

    with parameter_service_pact.serve() as srv:
        spectrum = SpectrumClient(str(srv.url)).get_spectrum(SPECTRUM_ID)

    assert spectrum.id == uuid.UUID(SPECTRUM_ID)
    assert spectrum.name == "Test Spectrum PACT"


def test_get_missing_spectrum(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request for a spectrum that does not exist")
        .given("no spectrum exists", id=MISSING_SPECTRUM_ID)
        .with_request("GET", f"/api/spectrum/{MISSING_SPECTRUM_ID}")
        .will_respond_with(404)
    )

    with parameter_service_pact.serve() as srv, pytest.raises(SpectrumNotFoundException) as exc:
        SpectrumClient(str(srv.url)).get_spectrum(MISSING_SPECTRUM_ID)

    assert exc.value.status_code == 404


def test_create_spectrum(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request to create a spectrum")
        .given("spectrum can be created")
        .with_request("POST", "/api/spectrum")
        .with_body(
            {
                "name": "Test Spectrum PACT POST",
                "wavelengths": WAVELENGTHS,
                "intensities": INTENSITIES,
            },
            content_type="application/json",
        )
        .will_respond_with(201)
        .with_body(
            spectrum_body(CREATED_ID, "Test Spectrum PACT POST"),
            content_type="application/json",
        )
    )

    with parameter_service_pact.serve() as srv:
        spectrum = SpectrumClient(str(srv.url)).create_spectrum(
            CreateSpectrumRequest(
                name="Test Spectrum PACT POST",
                wavelengths=WAVELENGTHS,
                intensities=INTENSITIES,
            )
        )

    assert spectrum.name == "Test Spectrum PACT POST"


def test_update_spectrum(parameter_service_pact: Pact):
    updated = Spectrum(
        id=uuid.UUID(SPECTRUM_ID),
        name="Updated Spectrum",
        wavelengths=WAVELENGTHS,
        intensities=INTENSITIES,
    )
    (
        parameter_service_pact
        .upon_receiving("a request to update a spectrum")
        .given("a spectrum exists", id=SPECTRUM_ID)
        .with_request("PATCH", "/api/spectrum")
        .with_body(updated.model_dump(mode="json"), content_type="application/json")
        .will_respond_with(200)
        .with_body(spectrum_body(name="Updated Spectrum"), content_type="application/json")
    )

    with parameter_service_pact.serve() as srv:
        spectrum = SpectrumClient(str(srv.url)).update_spectrum(updated)

    assert spectrum.id == updated.id
    assert spectrum.name == "Updated Spectrum"


def test_delete_spectrum(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request to delete a spectrum")
        .given("a spectrum exists", id=SPECTRUM_ID)
        .with_request("DELETE", f"/api/spectrum/{SPECTRUM_ID}")
        .will_respond_with(200)
    )

    with parameter_service_pact.serve() as srv:
        SpectrumClient(str(srv.url)).delete_spectrum(SPECTRUM_ID)


def test_delete_missing_spectrum(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request to delete a spectrum that does not exist")
        .given("no spectrum exists", id=MISSING_SPECTRUM_ID)
        .with_request("DELETE", f"/api/spectrum/{MISSING_SPECTRUM_ID}")
        .will_respond_with(404)
    )

    with parameter_service_pact.serve() as srv, pytest.raises(SpectrumNotFoundException):
        SpectrumClient(str(srv.url)).delete_spectrum(MISSING_SPECTRUM_ID)
