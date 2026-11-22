import uuid

import pytest
from pact import Pact, match
from refractometer_common.sample import (
    CreateSampleRequest,
    Sample,
    SampleClient,
    SampleNotFoundException,
    SellmeierCoefficients,
)

pytestmark = pytest.mark.pact

SAMPLE_ID = "93162ee4-5716-4059-a8a8-fc02e125543f"
MISSING_SAMPLE_ID = "00000000-0000-0000-0000-000000000000"
CREATED_ID = "7b1e9d3a-2c4f-4a6b-8e0d-5f7a9c1b3d2e"

B = [1.0, 2.0, 3.0]
C = [1.0, 2.0, 3.0]


def sample_body(sample_id: str = SAMPLE_ID, name: str = "Test Sample PACT") -> dict:
    return {
        "id": match.uuid(sample_id),
        "name": match.str(name),
        "sellmeier_coefficients": {
            "B": match.like(B, min=3, max=3),
            "C": match.like(C, min=3, max=3),
        },
    }


def test_get_all_samples(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request for all samples")
        .given("samples exist")
        .with_request("GET", "/api/samples")
        .will_respond_with(200)
        .with_body(match.each_like(sample_body(), min=1), content_type="application/json")
    )

    with parameter_service_pact.serve() as srv:
        samples = SampleClient(str(srv.url)).get_all_samples()

    assert len(samples) == 1
    assert samples[0].id == uuid.UUID(SAMPLE_ID)


def test_get_sample(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request for an existing sample")
        .given("a sample exists", id=SAMPLE_ID)
        .with_request("GET", f"/api/sample/{SAMPLE_ID}")
        .will_respond_with(200)
        .with_body(sample_body(), content_type="application/json")
    )

    with parameter_service_pact.serve() as srv:
        sample = SampleClient(str(srv.url)).get_sample(SAMPLE_ID)

    assert sample == Sample(
        id=uuid.UUID(SAMPLE_ID),
        name="Test Sample PACT",
        sellmeier_coefficients=SellmeierCoefficients(B=B, C=C),
    )


def test_get_missing_sample(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request for a sample that does not exist")
        .given("no sample exists", id=MISSING_SAMPLE_ID)
        .with_request("GET", f"/api/sample/{MISSING_SAMPLE_ID}")
        .will_respond_with(404)
    )

    with parameter_service_pact.serve() as srv, pytest.raises(SampleNotFoundException) as exc:
        SampleClient(str(srv.url)).get_sample(MISSING_SAMPLE_ID)

    assert exc.value.status_code == 404


def test_create_sample(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request to create a sample")
        .given("sample can be created")
        .with_request("POST", "/api/sample")
        .with_body(
            {
                "name": "Test Sample PACT POST",
                "sellmeier_coefficients": {"B": B, "C": C},
            },
            content_type="application/json",
        )
        .will_respond_with(200)
        .with_body(
            sample_body(CREATED_ID, "Test Sample PACT POST"),
            content_type="application/json",
        )
    )

    with parameter_service_pact.serve() as srv:
        sample = SampleClient(str(srv.url)).create_sample(
            CreateSampleRequest(name="Test Sample PACT POST", B=B, C=C)
        )

    assert sample.name == "Test Sample PACT POST"


def test_update_sample(parameter_service_pact: Pact):
    updated = Sample(
        id=uuid.UUID(SAMPLE_ID),
        name="Updated Sample",
        sellmeier_coefficients=SellmeierCoefficients(B=[2.0, 3.0, 4.0], C=C),
    )
    (
        parameter_service_pact
        .upon_receiving("a request to update a sample")
        .given("a sample exists", id=SAMPLE_ID)
        .with_request("PATCH", "/api/sample")
        .with_body(updated.model_dump(mode="json"), content_type="application/json")
        .will_respond_with(200)
        .with_body(sample_body(name="Updated Sample"), content_type="application/json")
    )

    with parameter_service_pact.serve() as srv:
        sample = SampleClient(str(srv.url)).update_sample(updated)

    assert sample.id == updated.id
    assert sample.name == "Updated Sample"


def test_delete_sample(parameter_service_pact: Pact):
    (
        parameter_service_pact
        .upon_receiving("a request to delete a sample")
        .given("a sample exists", id=SAMPLE_ID)
        .with_request("DELETE", f"/api/sample/{SAMPLE_ID}")
        .will_respond_with(200)
    )

    with parameter_service_pact.serve() as srv:
        SampleClient(str(srv.url)).delete_sample(SAMPLE_ID)
