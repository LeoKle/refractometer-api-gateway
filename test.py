import timeit
import uuid

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    id: uuid.UUID
    name: str
    number: int
    number_f: float
    liste: list[int]


class DomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    number: int
    number_f: float
    liste: list[int]


def convert1(api_model: APIModel) -> DomainModel:
    return DomainModel(**api_model.model_dump())


def convert2(api_model: APIModel) -> DomainModel:
    return DomainModel.model_validate(api_model)


def convert3(api_model: APIModel) -> DomainModel:
    return DomainModel(
        id=api_model.id,
        name=api_model.name,
        number=api_model.number,
        number_f=api_model.number_f,
        liste=api_model.liste,
    )


api_model = APIModel(
    id=uuid.uuid4(),
    name="Test",
    number=1,
    number_f=1.0,
    liste=[1, 2, 3],
)

COUNT = 100_000
result = timeit.timeit(lambda: convert1(api_model), number=COUNT)
print(result)
result = timeit.timeit(lambda: convert2(api_model), number=COUNT)
print(result)
result = timeit.timeit(lambda: convert3(api_model), number=COUNT)
print(result)
