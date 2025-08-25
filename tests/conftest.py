import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from filelock import FileLock
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from alembic import command
from alembic.config import Config
from src.api.v1.services.ollama_service import get_ollama_service
from src.db.database import create_db_session
from src.db.models.log import Log
from src.main import app
from src.middlewares import db_logging_middleware


def is_xdist_worker(request: pytest.FixtureRequest) -> bool:
    """Check if the current pytest session is running under pytest-xdist."""
    return "worker_id" in request.fixturenames


@pytest.fixture(scope="session")
def db_container(
    tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> Generator[PostgresContainer | SimpleNamespace, None, None]:
    """
    Manages a PostgreSQL container for the test session.

    If running with pytest-xdist, it uses file-based locking to ensure only
    one container is created for all workers. Otherwise, it starts a
    container for a normal single-process session.
    """
    if not is_xdist_worker(request):
        # Standard, non-parallel execution
        with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
            yield container
        return

    # Parallel execution with pytest-xdist
    worker_id = request.getfixturevalue("worker_id")
    if worker_id == "master":
        yield None
        return

    root_tmp_dir = tmp_path_factory.getbasetemp().parent
    lock_file = root_tmp_dir / ".db.lock"
    db_conn_file = root_tmp_dir / ".db.json"

    with FileLock(str(lock_file)):
        if not db_conn_file.is_file():
            # Primary worker starts the container
            container = PostgresContainer("postgres:16-alpine", driver="psycopg")
            container.start()
            conn_details = {"url": container.get_connection_url()}
            db_conn_file.write_text(json.dumps(conn_details))
            request.addfinalizer(container.stop)
            request.addfinalizer(db_conn_file.unlink)
            yield container
        else:
            # Secondary workers read connection info
            conn_details = json.loads(db_conn_file.read_text())
            yield SimpleNamespace(get_connection_url=lambda: conn_details["url"])


@pytest.fixture(scope="session")
def db_url(db_container: PostgresContainer | SimpleNamespace) -> str:
    """
    Fixture to get the database connection URL from the container.
    """
    if db_container:
        return db_container.get_connection_url()
    return None


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment_and_db(db_url: str, request: pytest.FixtureRequest) -> None:
    """
    Auto-used session-scoped fixture to set up the test environment and run migrations.
    This is safe for both single-process and parallel execution.
    """
    if not db_url:
        return

    os.environ["BUILT_IN_OLLAMA_MODEL"] = "test-built-in-model"
    os.environ["DEFAULT_GENERATION_MODEL"] = "test-default-model"
    os.environ["DATABASE_URL"] = db_url

    # In parallel mode, ensure migrations are run only once.
    if is_xdist_worker(request):
        # Fallback to a standard temp directory if the xdist-specific one isn't available
        xdist_tmp_str = os.environ.get("PYTEST_XDIST_TESTRUNUID", "test_run_temp")
        root_tmp_dir = Path(request.config.rootpath) / ".pytest_run" / xdist_tmp_str
        root_tmp_dir.mkdir(parents=True, exist_ok=True)

        migration_lock_file = root_tmp_dir / ".migration.lock"
        with FileLock(str(migration_lock_file)):
            alembic_cfg = Config()
            alembic_cfg.set_main_option("script_location", "alembic")
            alembic_cfg.set_main_option("sqlalchemy.url", db_url)
            command.upgrade(alembic_cfg, "head")
    else:
        # In single-process mode, just run the migration.
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "alembic")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")


@pytest.fixture
def db_session(db_url: str, monkeypatch) -> Generator[Session, None, None]:
    """
    Provides a transactional scope for each test function.
    """
    engine = create_engine(db_url)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    monkeypatch.setattr(db_logging_middleware, "create_db_session", lambda: db)
    app.dependency_overrides[create_db_session] = lambda: db

    try:
        yield db
    finally:
        db.rollback()
        db.query(Log).delete()
        db.commit()
        db.close()
        app.dependency_overrides.pop(create_db_session, None)


@pytest.fixture
def mock_ollama_service() -> MagicMock:
    """
    Fixture to mock the OllamaService using FastAPI's dependency overrides.
    """
    mock_service = MagicMock()
    mock_service.generate_response = AsyncMock()
    mock_service.list_models = AsyncMock()
    mock_service.pull_model = AsyncMock()
    mock_service.delete_model = AsyncMock()

    app.dependency_overrides[get_ollama_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides.pop(get_ollama_service, None)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create an httpx.AsyncClient instance for each test function.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
