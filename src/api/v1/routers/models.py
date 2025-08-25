from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.v1.services import setting_service
from src.api.v1.services.ollama_service import OllamaService, get_ollama_service
from src.db.database import get_db

# ==============================================================================
# Pydantic Models
# ==============================================================================


class ModelDetails(BaseModel):
    name: str = Field(alias="model")
    modified_at: datetime
    size: int


class ModelList(BaseModel):
    models: List[ModelDetails]


class PullRequest(BaseModel):
    name: str


# ==============================================================================
# Router
# ==============================================================================

router = APIRouter(
    prefix="/api/v1/models",
    tags=["models"],
)


@router.get(
    "/",
    response_model=ModelList,
    summary="List locally available models",
)
async def get_models(
    ollama_service: OllamaService = Depends(get_ollama_service),
):
    """
    Get a list of models that are available locally through Ollama.
    """
    return await ollama_service.list_models()


@router.post("/pull", summary="Pull a model from the Ollama registry")
async def pull_new_model(
    request: PullRequest,
    stream: bool = False,
    ollama_service: OllamaService = Depends(get_ollama_service),
) -> Any:
    """
    Pull a new model from the official Ollama registry.
    Set `stream=True` to receive progress events.
    """
    return await ollama_service.pull_model(request.name, stream)


@router.delete(
    "/{model_name:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a local model",
)
async def remove_model(
    model_name: str,
    ollama_service: OllamaService = Depends(get_ollama_service),
):
    """
    Delete a model from the local Ollama storage.
    """
    await ollama_service.delete_model(model_name)
    return None


@router.post("/switch/{model_name:path}", summary="Switch the active generation model")
async def switch_active_model(
    model_name: str,
    db: Session = Depends(get_db),
    ollama_service: OllamaService = Depends(get_ollama_service),
):
    """
    Switch the model used for the `/api/v1/generate` endpoint.
    The model must be available locally.
    """
    local_models_data = await ollama_service.list_models()
    # Safely access the 'models' key with a default empty list
    local_models = local_models_data.get("models", [])

    if not any(m.get("model") == model_name for m in local_models):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_name}' not found locally. Please pull it first.",
        )

    setting_service.set_active_model(db, model_name)
    return {"message": f"Switched active model to {model_name}"}
