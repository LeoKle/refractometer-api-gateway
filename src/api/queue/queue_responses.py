import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SimulationQueueResponse(BaseModel):
    id: uuid.UUID
    parameters: dict

    index: int | None = Field(default=None)
    being_processed: bool | None = Field(default=None)

    issuer: str | None = Field(default=None)
    callback_url: str | None = Field(default=None)
    name: str | None = Field(default=None)
    issued_at: datetime
