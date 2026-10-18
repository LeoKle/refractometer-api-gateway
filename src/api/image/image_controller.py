import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from refractometer_common.image import (
    ImageClientConnectionException,
    ImageClientException,
    ImageClientInterface,
    ImageClientInvalidResponseException,
    ImageClientTimeoutException,
    ImageNotFoundException,
)

from containers.dependencies import DependencyContainer

from .image_dto import ImageDTO

image_router = APIRouter(prefix="/image", tags=["Image"])


logger = logging.getLogger(__name__)


@image_router.get("/{image_id}")
@inject
def get_image(
    image_id: str,
    image_client: Annotated[
        ImageClientInterface, Depends(Provide[DependencyContainer.image_client])
    ],
):
    try:
        result = image_client.get_image(image_id)

        return ImageDTO.model_validate(result.model_dump())
    except ValidationError:
        logger.error("Image %s failed DTO validation", image_id, exc_info=True)
    except ImageNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image {image_id} not found",
        ) from None
    except ImageClientTimeoutException:
        logger.warning("Timeout fetching image %s", image_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Image service timed out",
        ) from None
    except ImageClientConnectionException:
        logger.error("Connection error fetching image %s", image_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image service unavailable",
        ) from None
    except ImageClientInvalidResponseException:
        logger.error("Invalid response fetching image %s", image_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image service returned an invalid response",
        ) from None
    except ImageClientException:
        logger.exception("Unexpected image client error for image %s", image_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching image",
        ) from None
