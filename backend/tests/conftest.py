from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_repository
from app.core.config import Settings
from app.main import create_app
from app.services import summary as summary_service
from app.services.repository import DataRepository
from tests.fixtures.synthetic import write_synthetic_region


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "raw").mkdir()
    (tmp_path / "processed").mkdir()
    return tmp_path


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, default_page_size=50, max_page_size=100)


@pytest.fixture
def synthetic_region(data_dir: Path) -> Path:
    return write_synthetic_region(data_dir / "processed")


@pytest.fixture
def repo(settings: Settings) -> DataRepository:
    return DataRepository(settings)


def _client(settings: Settings, repo: DataRepository) -> TestClient:
    summary_service._summary_cache.clear()
    app = create_app(settings)
    app.dependency_overrides[get_repository] = lambda: repo
    from app.core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client(settings: Settings, repo: DataRepository, synthetic_region: Path) -> TestClient:
    return _client(settings, repo)


@pytest.fixture
def empty_client(settings: Settings, repo: DataRepository) -> TestClient:
    """Client whose data directory contains no processed datasets."""
    return _client(settings, repo)
