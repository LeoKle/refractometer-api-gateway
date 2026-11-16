import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from refractometer_common.queue import (
    QueueClientConnectionException,
    QueueClientException,
    QueueClientInterface,
    QueueClientInvalidResponseException,
    QueueClientTimeoutException,
    SimulationQueueElement,
    SimulationQueueElementCreate,
)

from auth.guards import get_user
from containers.dependencies import DependencyContainer
from users.user import User

from .queue_requests import SimulationQueueRequest
from .queue_responses import SimulationQueueResponse

queue_router = APIRouter(prefix="", tags=["Queue"])


logger = logging.getLogger(__name__)


@queue_router.get("/queued")
@inject
def get_queued_simulations(
    user: Annotated[User, Depends(get_user)],
    queue_client: Annotated[
        QueueClientInterface, Depends(Provide[DependencyContainer.queue_client])
    ],
):
    try:
        results: list[SimulationQueueElement] = queue_client.get_queued_simulations()
    except QueueClientTimeoutException:
        logger.warning("Timeout fetching queued simulations")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Queue service timed out",
        ) from None
    except QueueClientConnectionException:
        logger.error("Connection error fetching queued simulations", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue service unavailable",
        ) from None
    except QueueClientInvalidResponseException:
        logger.error("Invalid response fetching queued simulations", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Queue service returned an invalid response",
        ) from None
    except QueueClientException:
        logger.exception("Unexpected Queue client error while getting queued simulations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching Queue",
        ) from None
    else:
        responses = []
        for result in results:
            try:
                responses.append(
                    SimulationQueueResponse(
                        id=result.id,
                        parameters=result.parameters,
                        issued_at=result.issued_at,
                        name=result.name,
                        index=result.index,
                        being_processed=result.being_processed,
                        issuer=result.issuer,
                        callback_url=result.callback_url,
                    )
                )
            except ValidationError:
                logger.error("Queue %s failed DTO validation", result.id, exc_info=True)

        return responses


@queue_router.post("/queue")
@inject
def queue_simulation(
    dto: SimulationQueueRequest,
    user: Annotated[User, Depends(get_user)],
    queue_client: Annotated[
        QueueClientInterface, Depends(Provide[DependencyContainer.queue_client])
    ],
):
    try:
        request = SimulationQueueElementCreate(
            parameters=dto.parameters,
            issuer=str(user.id),
            callback_url=dto.callback_url,
            name=dto.name,
        )
        result = queue_client.create_queued_simulation(request)
    except QueueClientTimeoutException:
        logger.warning("Timeout queueing simulation")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Queue service timed out",
        ) from None
    except QueueClientConnectionException:
        logger.error("Connection error queueing simulation", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue service unavailable",
        ) from None
    except QueueClientInvalidResponseException:
        logger.error("Invalid response queueing simulation", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Queue service returned an invalid response",
        ) from None
    except QueueClientException:
        logger.exception("Unexpected Queue client error while queueing simulation", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching Queue",
        ) from None
    else:
        try:
            return SimulationQueueResponse(
                id=result.id,
                parameters=result.parameters,
                index=result.index,
                being_processed=result.being_processed,
                issuer=result.issuer,
                callback_url=result.callback_url,
                name=result.name,
                issued_at=result.issued_at,
            )
        except ValidationError:
            logger.error("Invalid response queueing simulation", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Queue service returned an invalid response",
            ) from None
