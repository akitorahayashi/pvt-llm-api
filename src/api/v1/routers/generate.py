from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.v1.schemas import GenerateRequest
from src.api.v1.services import setting_service
from src.api.v1.services.ollama_service import OllamaService, get_ollama_service
from src.db.database import get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["generate"],
)


@router.post("/generate")
async def generate(
    request: GenerateRequest,
    db: Session = Depends(get_db),
    ollama_service: OllamaService = Depends(get_ollama_service),
):
    """
    Endpoint to generate text based on a prompt using the currently active model.

    This endpoint takes a prompt and returns a generated response from the
    Ollama model. It supports both streaming and non-streaming responses.
    The core logic is delegated to the `generate_ollama_response` service.
    """
    # Get the currently active model from the database
    active_model = setting_service.get_active_model(db)
    if not active_model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No generation model is currently configured.",
        )

    return await ollama_service.generate_response(
        prompt=request.prompt,
        model_name=active_model,
        stream=request.stream,
    )
