from pydantic import BaseModel, Field, model_validator


class SpectrumRequest(BaseModel):
    name: str = Field(min_length=1)
    wavelengths: list[float] = Field(min_length=1)
    intensities: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_same_length(self):
        if len(self.wavelengths) != len(self.intensities):
            msg = "wavelengths and intensities must have the same length"
            raise ValueError(msg)
        return self
