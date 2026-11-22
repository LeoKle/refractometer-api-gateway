import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
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

from api.spectrum.spectrum_request import SpectrumRequest
from api.spectrum.spectrum_response import SpectrumResponse
from auth.guards import get_user
from containers.dependencies import DependencyContainer

spectrum_router = APIRouter(tags=["Spectrum"], dependencies=[Depends(get_user)])

logger = logging.getLogger(__name__)

SpectrumClientDependency = Annotated[
    SpectrumClientInterface,
    Depends(Provide[DependencyContainer.spectrum_client]),
]


@contextmanager
def _map_spectrum_client_errors(action: str) -> Generator[None]:
    try:
        yield
    except SpectrumNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spectrum not found",
        ) from None
    except SpectrumClientTimeoutException:
        logger.warning("Timeout while %s", action)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Spectrum service timed out",
        ) from None
    except SpectrumClientConnectionException:
        logger.error("Connection error while %s", action, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Spectrum service unavailable",
        ) from None
    except SpectrumClientInvalidResponseException:
        logger.error("Invalid response while %s", action, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spectrum service returned an invalid response",
        ) from None
    except SpectrumClientException:
        logger.exception("Unexpected spectrum client error while %s", action)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error in spectrum service",
        ) from None


def _to_response(spectrum: Spectrum) -> SpectrumResponse:
    try:
        return SpectrumResponse.model_validate(spectrum.model_dump())
    except ValidationError:
        logger.error("Spectrum %s failed DTO validation", spectrum.id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spectrum service returned an invalid response",
        ) from None


@spectrum_router.get("/spectrums")
@inject
def get_spectrums(spectrum_client: SpectrumClientDependency) -> list[SpectrumResponse]:
    with _map_spectrum_client_errors("fetching spectrums"):
        spectrums = spectrum_client.get_all_spectrums()

    responses = []
    for spectrum in spectrums:
        try:
            responses.append(SpectrumResponse.model_validate(spectrum.model_dump()))
        except ValidationError:
            logger.error("Spectrum %s failed DTO validation", spectrum.id, exc_info=True)

    return responses


@spectrum_router.get("/spectrum/{spectrum_id}")
@inject
def get_spectrum(
    spectrum_id: uuid.UUID,
    spectrum_client: SpectrumClientDependency,
) -> SpectrumResponse:
    with _map_spectrum_client_errors(f"fetching spectrum {spectrum_id}"):
        spectrum = spectrum_client.get_spectrum(str(spectrum_id))

    return _to_response(spectrum)


@spectrum_router.post("/spectrum", status_code=status.HTTP_201_CREATED)
@inject
def create_spectrum(
    dto: SpectrumRequest,
    spectrum_client: SpectrumClientDependency,
) -> SpectrumResponse:
    request = CreateSpectrumRequest(
        name=dto.name,
        wavelengths=dto.wavelengths,
        intensities=dto.intensities,
    )

    with _map_spectrum_client_errors("creating spectrum"):
        spectrum = spectrum_client.create_spectrum(request)

    return _to_response(spectrum)


@spectrum_router.patch("/spectrum/{spectrum_id}")
@inject
def update_spectrum(
    spectrum_id: uuid.UUID,
    dto: SpectrumRequest,
    spectrum_client: SpectrumClientDependency,
) -> SpectrumResponse:
    spectrum = Spectrum(
        id=spectrum_id,
        name=dto.name,
        wavelengths=dto.wavelengths,
        intensities=dto.intensities,
    )

    with _map_spectrum_client_errors(f"updating spectrum {spectrum_id}"):
        updated = spectrum_client.update_spectrum(spectrum)

    return _to_response(updated)


@spectrum_router.delete("/spectrum/{spectrum_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
def delete_spectrum(spectrum_id: uuid.UUID, spectrum_client: SpectrumClientDependency) -> None:
    with _map_spectrum_client_errors(f"deleting spectrum {spectrum_id}"):
        spectrum_client.delete_spectrum(str(spectrum_id))
