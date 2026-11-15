import uuid
from datetime import datetime

from pydantic import BaseModel


class SimulationResultDTO(BaseModel):
    id: uuid.UUID
    parameters: dict
    image_id: str
    issued_at: datetime
    completed_at: datetime
