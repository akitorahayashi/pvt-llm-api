from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str
    stream: bool = False


class GenerateResponse(BaseModel):
    response: str
