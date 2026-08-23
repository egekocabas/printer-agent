from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from printer_agent.config import Settings
from printer_agent.main import create_app
from printer_agent.printer.mock import MockPrinter


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        printer_backend="mock",
        printer_model_name="TestPrinter",
        printer_dots_width=384,
        max_image_upload_bytes=2 * 1024 * 1024,
        max_image_pixels=2_000_000,
    )


@pytest.fixture
def mock_printer() -> MockPrinter:
    return MockPrinter(model="TestPrinter")


@pytest.fixture
def client(settings: Settings, mock_printer: MockPrinter) -> Iterator[TestClient]:
    with TestClient(create_app(settings=settings, printer=mock_printer)) as test_client:
        yield test_client
