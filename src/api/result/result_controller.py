import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from refractometer_common.result import (
    SimulationResultClientConnectionException,
    SimulationResultClientException,
    SimulationResultClientInterface,
    SimulationResultClientInvalidResponseException,
    SimulationResultClientTimeoutException,
    SimulationResultNotFoundException,
)

from api.result.result_dto import SimulationResultDTO
from auth.guards import get_user
from containers.dependencies import DependencyContainer

# result_router = APIRouter(tags=["Result"], dependencies=[Depends(get_user)])
result_router = APIRouter(tags=["Result"])

logger = logging.getLogger(__name__)


@result_router.get("/results")
@inject
def get_results(
    result_client: Annotated[
        SimulationResultClientInterface,
        Depends(Provide[DependencyContainer.result_client]),
    ],
):
    try:
        results = result_client.get_results()

        response = []
        for result in results:
            try:
                response.append(SimulationResultDTO(**result.model_dump()))
            except ValidationError:
                logger.error("Result %s failed DTO validation", result.id, exc_info=True)

    except SimulationResultClientTimeoutException:
        logger.warning("Timeout fetching results")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Result service timed out",
        ) from None
    except SimulationResultClientConnectionException:
        logger.error("Connection error fetching result", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Result service unavailable",
        ) from None
    except SimulationResultClientInvalidResponseException:
        logger.error("Invalid response fetching results", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Result service returned an invalid response",
        ) from None
    except SimulationResultClientException:
        logger.exception("Unexpected result client error while getting results")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching results",
        ) from None
    else:
        return response


@result_router.get("/result/{result_id}")
@inject
def get_result(
    result_id: str,
    result_client: Annotated[
        SimulationResultClientInterface,
        Depends(Provide[DependencyContainer.result_client]),
    ],
):
    try:
        result = result_client.get_results()

        try:
            response = SimulationResultDTO(**result.model_dump())
        except ValidationError:
            logger.error("Result %s failed DTO validation", result.id, exc_info=True)
        else:
            return response

    except SimulationResultClientTimeoutException:
        logger.warning("Timeout fetching  %s", result_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Result service timed out",
        ) from None
    except SimulationResultClientConnectionException:
        logger.error("Connection error getting result %s", result_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Result service unavailable",
        ) from None
    except SimulationResultClientInvalidResponseException:
        logger.error("Invalid response getting result %s", result_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Result service returned an invalid response",
        ) from None
    except SimulationResultNotFoundException:
        logger.error("Connection error getting result %s", result_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result {result_id} not found",
        ) from None
    except SimulationResultClientException:
        logger.exception("Unexpected result client error while getting result %s", result_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching result",
        ) from None
    else:
        return response


@result_router.delete("/result/{result_id}")
@inject
def delete_result(
    result_id: str,
    result_client: Annotated[
        SimulationResultClientInterface,
        Depends(Provide[DependencyContainer.result_client]),
    ],
):
    try:
        result_client.delete_result(result_id)
    except SimulationResultClientTimeoutException:
        logger.warning("Timeout deleting result %s", result_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Result service timed out",
        ) from None
    except SimulationResultClientConnectionException:
        logger.error("Connection error deleting result %s", result_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Result service unavailable",
        ) from None
    except SimulationResultNotFoundException:
        logger.error("Connection error deleting result %s", result_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result {result_id} not found while deleting",
        ) from None
    except SimulationResultClientException:
        logger.exception("Unexpected result client error while deleting result %s", result_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching result",
        ) from None
