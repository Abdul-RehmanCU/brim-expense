from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class PlaceholderResponse(BaseModel):
    status: str
    service: str
    implemented: bool
    message: str
