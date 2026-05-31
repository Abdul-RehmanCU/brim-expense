from pydantic import BaseModel


class AiStatusResponse(BaseModel):
    status: str
    implemented: bool
    message: str
