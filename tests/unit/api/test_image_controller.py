from unittest.mock import create_autospec

import pytest
from dependency_injector import providers
from refractometer_common.image import (
    Image,
    ImageClientConnectionException,
    ImageClientException,
    ImageClientInterface,
    ImageClientInvalidResponseException,
    ImageClientTimeoutException,
    ImageNotFoundException,
)

from api.app import container
from tests.unit.conftest import LEAK

pytestmark = pytest.mark.unit

# Image ids are opaque strings (the image service is backed by MongoDB).
IMAGE_ID = "665f1c2b9a1e4b0012345678"
VALUES = [[0.0, 0.5, 1.0], [1.0, 0.5, 0.0]]
SHAPE = (2, 3)
URL = f"/api/image/{IMAGE_ID}"


def make_image() -> Image:
    return Image(values=VALUES, shape=SHAPE)


def as_json(image: Image) -> dict:
    return image.model_dump(mode="json")


@pytest.fixture
def image_client():
    mock = create_autospec(ImageClientInterface, instance=True)
    with container.image_client.override(providers.Object(mock)):
        yield mock


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("error", "status_code", "detail"),
        [
            (ImageClientTimeoutException, 504, "Image service timed out"),
            (ImageClientConnectionException, 503, "Image service unavailable"),
            (
                ImageClientInvalidResponseException,
                502,
                "Image service returned an invalid response",
            ),
            (ImageClientException, 500, "Internal error while fetching image"),
        ],
    )
    def test_client_errors_are_mapped(self, client, image_client, error, status_code, detail):
        image_client.get_image.side_effect = error(LEAK)

        response = client.get(URL)

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert LEAK not in response.text

    def test_not_found(self, client, image_client):
        image_client.get_image.side_effect = ImageNotFoundException(LEAK, 404)

        response = client.get(URL)

        assert response.status_code == 404
        assert response.json() == {"detail": f"Image {IMAGE_ID} not found"}
        assert LEAK not in response.text

    def test_unexpected_errors_do_not_leak(self, client, image_client):
        image_client.get_image.side_effect = RuntimeError(LEAK)

        response = client.get(URL)

        assert response.status_code == 500
        assert LEAK not in response.text


class TestAuth:
    def test_requires_authentication(self, anonymous_client, image_client):
        response = anonymous_client.get(URL)

        assert response.status_code == 401
        image_client.get_image.assert_not_called()


class TestGetImage:
    def test_returns_image(self, client, image_client):
        image_client.get_image.return_value = make_image()

        response = client.get(URL)

        assert response.status_code == 200
        assert response.json() == as_json(make_image())
        assert response.json()["shape"] == list(SHAPE)
        image_client.get_image.assert_called_once_with(IMAGE_ID)

    def test_id_is_passed_through_unchanged(self, client, image_client):
        image_client.get_image.return_value = make_image()

        client.get("/api/image/not-a-uuid")

        image_client.get_image.assert_called_once_with("not-a-uuid")

    def test_invalid_upstream_object_is_bad_gateway(self, client, image_client):
        image_client.get_image.return_value = Image.model_construct(values=None, shape=None)

        response = client.get(URL)

        assert response.status_code == 502
        assert response.json() == {"detail": "Image service returned an invalid response"}
