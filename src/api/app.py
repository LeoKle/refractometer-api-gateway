from fastapi import FastAPI

from containers.dependencies import DependencyContainer

app = FastAPI(title="Refractometer API Gateway")


@app.get("/health")
def health():
    return {"status": "ok"}


container = DependencyContainer()
container.wire(modules=[])
