from fastapi import FastAPI

from api.router import main_router
from auth.api import auth_controller
from containers.dependencies import DependencyContainer

app = FastAPI(title="Refractometer API Gateway")
app.include_router(main_router)


@app.get("/health")
def health():
    return {"status": "ok"}


container = DependencyContainer()
container.wire(
    modules=[
        auth_controller,
    ]
)
