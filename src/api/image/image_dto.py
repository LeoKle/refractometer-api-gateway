from pydantic import BaseModel


class ImageDTO(BaseModel):
    values: list[list[float]]
    shape: tuple[int, int]
