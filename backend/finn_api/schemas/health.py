from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str


class ReadinessResponse(HealthResponse):
    database: Literal["available", "unavailable"]
