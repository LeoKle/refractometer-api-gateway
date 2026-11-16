import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from refractometer_common.spectrum import (
    Spectrum,
    SpectrumClientConnectionException,
    SpectrumClientException,
    SpectrumClientInterface,
    SpectrumClientInvalidResponseException,
    SpectrumClientTimeoutException,
)

from api.spectrum.spectrum_response import SpectrumResponse
from auth.guards import get_user
from containers.dependencies import DependencyContainer

spectrum_router = APIRouter(tags=["Spectrum"], dependencies=[Depends(get_user)])

logger = logging.getLogger(__name__)


@spectrum_router.get("/spectrums")
@inject
def get_spectrums(
    spectrum_client: Annotated[
        SpectrumClientInterface,
        Depends(Provide[DependencyContainer.spectrum_client]),
    ],
):
    try:
        spectrums: list[Spectrum] = spectrum_client.get_all_spectrums()
    except SpectrumClientTimeoutException:
        logger.warning("Timeout fetching spectrums")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Spectrum service timed out",
        ) from None
    except SpectrumClientConnectionException:
        logger.error("Connection error fetching spectrum", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Spectrum service unavailable",
        ) from None
    except SpectrumClientInvalidResponseException:
        logger.error("Invalid response fetching spectrums", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spectrum service returned an invalid response",
        ) from None
    except SpectrumClientException:
        logger.exception("Unexpected spectrum client error while getting spectrums")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching spectrums",
        ) from None
    else:
        responses = []
        for spectrum in spectrums:
            try:
                responses.append(
                    SpectrumResponse(
                        id=spectrum.id,
                        name=spectrum.name,
                        wavelengths=spectrum.wavelengths,
                        intensities=spectrum.intensities,
                    )
                )
            except ValidationError:
                logger.error("Queue %s failed DTO validation", spectrum.id, exc_info=True)

        return responses
