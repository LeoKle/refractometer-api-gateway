from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.image import image_controller
from api.queue import queue_controller
from api.result import result_controller
from api.router import main_router
from api.sample import sample_controller
from api.spectrum import spectrum_controller
from auth.api import auth_controller
from containers.dependencies import DependencyContainer


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    container.init_resources()
    try:
        yield
    finally:
        container.shutdown_resources()


app = FastAPI(title="Refractometer API Gateway", lifespan=lifespan)
app.include_router(main_router)


@app.get("/health")
def health():
    return {"status": "ok"}


container = DependencyContainer()
container.wire(
    modules=[
        auth_controller,
        image_controller,
        result_controller,
        queue_controller,
        sample_controller,
        spectrum_controller,
    ]
)
