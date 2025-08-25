from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from starlette import status
from starlette.responses import StreamingResponse

from src.api.v1.services import setting_service

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


async def test_get_models(client: AsyncClient, mock_ollama_service: MagicMock):
    """Test the GET /api/v1/models endpoint with a realistic mock."""
    # Arrange
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    mock_response = {
        "models": [
            {
                "model": "test-model:latest",
                "modified_at": now_iso,
                "size": 12345,
            }
        ]
    }
    mock_ollama_service.list_models.return_value = mock_response

    # Act
    response = await client.get("/api/v1/models/")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["models"][0]["model"] == "test-model:latest"
    assert response_data["models"][0]["size"] == 12345
    mock_ollama_service.list_models.assert_called_once()


async def test_pull_model_no_stream(
    client: AsyncClient, mock_ollama_service: MagicMock
):
    """Test the POST /api/v1/models/pull endpoint without streaming."""
    # Arrange
    model_name = "new-model:latest"
    mock_ollama_service.pull_model.return_value = {"status": "success"}

    # Act
    response = await client.post(
        "/api/v1/models/pull", json={"name": model_name}, params={"stream": False}
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "success"}
    mock_ollama_service.pull_model.assert_called_once_with(model_name, False)


async def test_pull_model_streaming(
    client: AsyncClient, mock_ollama_service: MagicMock
):
    """Test the POST /api/v1/models/pull endpoint with SSE streaming."""
    # Arrange
    model_name = "streaming-model:latest"

    async def mock_stream_content():
        yield "mocked streaming response"

    mock_ollama_service.pull_model.return_value = StreamingResponse(
        mock_stream_content(), media_type="text/event-stream"
    )

    # Act
    response = await client.post(
        "/api/v1/models/pull", json={"name": model_name}, params={"stream": True}
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/event-stream")
    mock_ollama_service.pull_model.assert_called_once_with(model_name, True)


async def test_delete_model(client: AsyncClient, mock_ollama_service: MagicMock):
    """Test the DELETE /api/v1/models/{model_name} endpoint."""
    model_name = "test-model:latest"
    await client.delete(f"/api/v1/models/{model_name}")
    mock_ollama_service.delete_model.assert_called_once_with(model_name)


async def test_switch_active_model_success(
    client: AsyncClient, mock_ollama_service: MagicMock, db_session: Session
):
    """Test successfully switching the active model."""
    # Arrange
    model_name = "existing-model:latest"
    mock_ollama_service.list_models.return_value = {
        "models": [
            {
                "model": model_name,
                "modified_at": datetime.now(timezone.utc).isoformat(),
                "size": 12345,
            }
        ]
    }

    # Act
    response = await client.post(f"/api/v1/models/switch/{model_name}")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": f"Switched active model to {model_name}"}

    # Verify that the model check was performed
    mock_ollama_service.list_models.assert_called_once()
    # Verify that the change was persisted in the database
    active_model_from_db = setting_service.get_active_model(db_session)
    assert active_model_from_db == model_name


async def test_switch_active_model_not_found(
    client: AsyncClient, mock_ollama_service: MagicMock
):
    """Test switching to a model that does not exist locally."""
    # Arrange
    model_name = "non-existent-model:latest"
    mock_ollama_service.list_models.return_value = {
        "models": [{"model": "another-model:latest"}]
    }

    # Act
    response = await client.post(f"/api/v1/models/switch/{model_name}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found locally" in response.json()["detail"]
