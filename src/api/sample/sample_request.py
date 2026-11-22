from pydantic import BaseModel, Field


class SellmeierCoefficientsRequest(BaseModel):
    B: list[float] = Field(min_length=3, max_length=3)
    C: list[float] = Field(min_length=3, max_length=3)


class SampleRequest(BaseModel):
    name: str = Field(min_length=1)
    sellmeier_coefficients: SellmeierCoefficientsRequest
