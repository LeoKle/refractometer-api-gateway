import uuid

from pydantic import BaseModel


class SpectrumResponse(BaseModel):
    id: uuid.UUID
    name: str
    wavelengths: list[float]
    intensities: list[float]
