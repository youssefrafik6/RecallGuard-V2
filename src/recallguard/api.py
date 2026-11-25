"""FastAPI service with operator-configured model loading."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from recallguard.analytics import aggregate, configured_dataset
from recallguard.inference import (
    LIMITATION,
    BatchRequest,
    IncidentRequest,
    Prediction,
    configured_model,
    predict,
    predict_batch,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bundle = configured_model()
    app.state.dataset = configured_dataset()
    yield


app = FastAPI(title="RecallGuard V2", version="2.0.0", lifespan=lifespan)


class Health(BaseModel):
    status: Literal["ok"]
    model_available: bool


class ModelInfo(BaseModel):
    model: str
    design: str
    features: list[str]
    limitation: str


def available_model(request: Request) -> dict:
    bundle = request.app.state.bundle
    if bundle is None:
        raise HTTPException(503, "No compatible trained model is configured")
    return bundle


@app.get("/health", response_model=Health)
def health(request: Request):
    return Health(status="ok", model_available=request.app.state.bundle is not None)


@app.get("/model-info", response_model=ModelInfo)
def model_info(request: Request):
    metadata = available_model(request)["metadata"]
    return ModelInfo(
        model=metadata["selected"],
        design=metadata["design"],
        features=metadata["features"],
        limitation=LIMITATION,
    )


@app.post("/predict", response_model=Prediction)
def predict_route(body: IncidentRequest, request: Request):
    return predict(available_model(request), body)


@app.post("/batch-predict", response_model=list[Prediction])
def batch_route(body: BatchRequest, request: Request):
    return predict_batch(available_model(request), body)


@app.get("/analytics/summary")
def analytics_summary(request: Request) -> dict:
    if request.app.state.dataset is None:
        raise HTTPException(503, "No local analytics data is configured")
    return aggregate(request.app.state.dataset, "summary").to_dict("records")[0]


@app.get("/analytics/categories")
def analytics_categories(request: Request) -> list[dict]:
    if request.app.state.dataset is None:
        raise HTTPException(503, "No local analytics data is configured")
    return aggregate(request.app.state.dataset, "categories").to_dict("records")
