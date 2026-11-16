import uuid

from pydantic import BaseModel


class SellmeierCoefficientsResponse(BaseModel):
    B: list[float]
    C: list[float]


class SampleResponse(BaseModel):
    id: uuid.UUID
    name: str
    sellmeier_coefficients: SellmeierCoefficientsResponse
