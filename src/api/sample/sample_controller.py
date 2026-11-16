import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from refractometer_common.sample import (
    Sample,
    SampleClientConnectionException,
    SampleClientException,
    SampleClientInterface,
    SampleClientInvalidResponseException,
    SampleClientTimeoutException,
)

from api.sample.sample_response import SampleResponse, SellmeierCoefficientsResponse
from auth.guards import get_user
from containers.dependencies import DependencyContainer

sample_router = APIRouter(tags=["Sample"], dependencies=[Depends(get_user)])

logger = logging.getLogger(__name__)


@sample_router.get("/samples")
@inject
def get_samples(
    sample_client: Annotated[
        SampleClientInterface,
        Depends(Provide[DependencyContainer.sample_client]),
    ],
):
    try:
        samples: list[Sample] = sample_client.get_all_samples()
    except SampleClientTimeoutException:
        logger.warning("Timeout fetching samples")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Sample service timed out",
        ) from None
    except SampleClientConnectionException:
        logger.error("Connection error fetching sample", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sample service unavailable",
        ) from None
    except SampleClientInvalidResponseException:
        logger.error("Invalid response fetching samples", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sample service returned an invalid response",
        ) from None
    except SampleClientException:
        logger.exception("Unexpected sample client error while getting samples")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching samples",
        ) from None
    else:
        responses = []
        for sample in samples:
            try:
                responses.append(
                    SampleResponse(
                        id=sample.id,
                        name=sample.name,
                        sellmeier_coefficients=SellmeierCoefficientsResponse(
                            B=sample.sellmeier_coefficients.B, C=sample.sellmeier_coefficients.C
                        ),
                    )
                )
            except ValidationError:
                logger.error("Queue %s failed DTO validation", sample.id, exc_info=True)

        return responses
