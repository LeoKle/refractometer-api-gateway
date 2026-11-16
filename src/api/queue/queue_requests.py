from pydantic import BaseModel, Field


class SimulationQueueRequest(BaseModel):
    parameters: dict

    callback_url: str | None = Field(default=None)
    name: str | None = Field(default=None)
