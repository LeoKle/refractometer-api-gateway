import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

from api.sample.sample_request import SampleRequest
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
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

from api.sample.sample_response import SampleResponse
from auth.guards import get_user
from containers.dependencies import DependencyContainer

sample_router = APIRouter(tags=["Sample"], dependencies=[Depends(get_user)])

logger = logging.getLogger(__name__)

SampleClientDependency = Annotated[
    SampleClientInterface,
    Depends(Provide[DependencyContainer.sample_client]),
]


@contextmanager
def _map_sample_client_errors(action: str) -> Generator[None]:
    try:
        yield
    except SampleNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found",
        ) from None
    except SampleClientTimeoutException:
        logger.warning("Timeout while %s", action)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Sample service timed out",
        ) from None
    except SampleClientConnectionException:
        logger.error("Connection error while %s", action, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sample service unavailable",
        ) from None
    except SampleClientInvalidResponseException:
        logger.error("Invalid response while %s", action, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sample service returned an invalid response",
        ) from None
    except SampleClientException:
        logger.exception("Unexpected sample client error while %s", action)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error in sample service",
        ) from None


def _to_response(sample: Sample) -> SampleResponse:
    try:
        return SampleResponse.model_validate(sample.model_dump())
    except ValidationError:
        logger.error("Sample %s failed DTO validation", sample.id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sample service returned an invalid response",
        ) from None


@sample_router.get("/samples")
@inject
def get_samples(sample_client: SampleClientDependency) -> list[SampleResponse]:
    with _map_sample_client_errors("fetching samples"):
        samples = sample_client.get_all_samples()

    responses = []
    for sample in samples:
        try:
            responses.append(SampleResponse.model_validate(sample.model_dump()))
        except ValidationError:
            logger.error("Sample %s failed DTO validation", sample.id, exc_info=True)

    return responses


@sample_router.get("/sample/{sample_id}")
@inject
def get_sample(sample_id: uuid.UUID, sample_client: SampleClientDependency) -> SampleResponse:
    with _map_sample_client_errors(f"fetching sample {sample_id}"):
        sample = sample_client.get_sample(str(sample_id))

    return _to_response(sample)


@sample_router.post("/sample", status_code=status.HTTP_201_CREATED)
@inject
def create_sample(dto: SampleRequest, sample_client: SampleClientDependency) -> SampleResponse:
    request = CreateSampleRequest(
        name=dto.name,
        B=dto.sellmeier_coefficients.B,
        C=dto.sellmeier_coefficients.C,
    )

    with _map_sample_client_errors("creating sample"):
        sample = sample_client.create_sample(request)

    return _to_response(sample)


@sample_router.patch("/sample/{sample_id}")
@inject
def update_sample(
    sample_id: uuid.UUID,
    dto: SampleRequest,
    sample_client: SampleClientDependency,
) -> SampleResponse:
    sample = Sample(
        id=sample_id,
        name=dto.name,
        sellmeier_coefficients=SellmeierCoefficients(
            B=dto.sellmeier_coefficients.B,
            C=dto.sellmeier_coefficients.C,
        ),
    )

    with _map_sample_client_errors(f"updating sample {sample_id}"):
        updated = sample_client.update_sample(sample)

    return _to_response(updated)


@sample_router.delete("/sample/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
def delete_sample(sample_id: uuid.UUID, sample_client: SampleClientDependency) -> None:
    with _map_sample_client_errors(f"deleting sample {sample_id}"):
        sample_client.delete_sample(str(sample_id))
