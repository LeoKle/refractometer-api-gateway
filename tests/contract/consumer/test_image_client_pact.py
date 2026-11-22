import uuid

import pytest
from pact import Pact, match
from refractometer_common.image import (
    CreateImageRequest,
    Image,
    ImageClient,
    ImageClientException,
    ImageNotFoundException,
)

pytestmark = pytest.mark.pact

IMAGE_ID = "123e4567-e89b-12d3-a456-426614174000"
MISSING_IMAGE_ID = "00000000-0000-0000-0000-000000000000"
CREATED_ID = "7b1e9d3a-2c4f-4a6b-8e0d-5f7a9c1b3d2e"

VALUES = [[0.1, 0.2], [0.3, 0.4]]
SHAPE = (2, 2)


def test_get_image(image_service_pact: Pact):
    (
        image_service_pact
        .upon_receiving("a request for an existing image")
        .given("an image exists", id=IMAGE_ID)
        .with_request("GET", f"/api/image/{IMAGE_ID}")
        .will_respond_with(200)
        .with_body(
            {
                "values": match.like(VALUES, min=1),
                "shape": [match.int(2), match.int(2)],
            },
            content_type="application/json",
        )
    )

    with image_service_pact.serve() as srv:
        image = ImageClient(str(srv.url)).get_image(IMAGE_ID)

    assert isinstance(image, Image)
    assert image.shape == SHAPE
    assert len(image.values) == SHAPE[0]


def test_get_missing_image(image_service_pact: Pact):
    (
        image_service_pact
        .upon_receiving("a request for an image that does not exist")
        .given("no image exists", id=MISSING_IMAGE_ID)
        .with_request("GET", f"/api/image/{MISSING_IMAGE_ID}")
        .will_respond_with(404)
        .with_body({"detail": match.str("Image not found")}, content_type="application/json")
    )

    with image_service_pact.serve() as srv, pytest.raises(ImageNotFoundException) as exc:
        ImageClient(str(srv.url)).get_image(MISSING_IMAGE_ID)

    assert exc.value.status_code == 404


def test_get_image_with_invalid_id(image_service_pact: Pact):
    (
        image_service_pact
        .upon_receiving("a request for an image with an invalid UUID")
        .with_request("GET", "/api/image/not-a-uuid")
        .will_respond_with(400)
        .with_body(
            {"detail": match.str("Invalid UUID: not-a-uuid")}, content_type="application/json"
        )
    )

    with image_service_pact.serve() as srv, pytest.raises(ImageClientException) as exc:
        ImageClient(str(srv.url)).get_image("not-a-uuid")

    assert exc.value.status_code == 400
    assert not isinstance(exc.value, ImageNotFoundException)


def test_create_image(image_service_pact: Pact):
    (
        image_service_pact
        .upon_receiving("a request to create an image")
        .with_request("POST", "/api/image")
        .with_body({"values": VALUES, "shape": list(SHAPE)}, content_type="application/json")
        .will_respond_with(201)
        .with_body({"id": match.uuid(CREATED_ID)}, content_type="application/json")
    )

    with image_service_pact.serve() as srv:
        image_id = ImageClient(str(srv.url)).create_image(
            CreateImageRequest(values=VALUES, shape=SHAPE)
        )

    uuid.UUID(image_id)


def test_create_image_with_idempotency_key(image_service_pact: Pact):
    (
        image_service_pact
        .upon_receiving("a request to create an image with an idempotency key")
        .with_request("POST", "/api/image")
        .with_header("idempotency-key", "pact-idempotency-key")
        .with_body({"values": VALUES, "shape": list(SHAPE)}, content_type="application/json")
        .will_respond_with(201)
        .with_body({"id": match.uuid(CREATED_ID)}, content_type="application/json")
    )

    with image_service_pact.serve() as srv:
        image_id = ImageClient(str(srv.url)).create_image(
            CreateImageRequest(values=VALUES, shape=SHAPE),
            idempotency_key="pact-idempotency-key",
        )

    uuid.UUID(image_id)
