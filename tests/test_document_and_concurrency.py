import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from printer_agent.api.models import PrintDocument
from printer_agent.config import Settings
from printer_agent.exceptions import PrinterUnavailableError
from printer_agent.printer.mock import MockPrinter
from printer_agent.service.printing import PrintingService
from tests.image_helpers import image_bytes


def test_json_document_executes_in_order(client: TestClient, mock_printer: MockPrinter) -> None:
    response = client.post(
        "/print",
        json={
            "items": [
                {"type": "text", "text": "Hello", "bold": True},
                {"type": "qr", "data": "https://example.com"},
                {"type": "feed", "lines": 3},
            ]
        },
    )
    assert response.status_code == 200
    assert [operation.kind for operation in mock_printer.operations] == [
        "text",
        "qr",
        "feed",
        "feed",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"items": []},
        {"items": [{"type": "feed", "lines": 0}]},
        {"items": [{"type": "raw", "data": "1b40"}]},
    ],
)
def test_invalid_documents_are_rejected(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/print", json=payload).status_code == 400


def test_multipart_references_must_match_uploads(client: TestClient) -> None:
    missing = client.post(
        "/print",
        data={"document": json.dumps({"items": [{"type": "image", "file": "missing"}]})},
    )
    assert missing.status_code == 400

    unreferenced = client.post(
        "/print",
        data={"document": json.dumps({"items": [{"type": "text", "text": "hi"}]})},
        files=[("images", ("unused.png", image_bytes(), "image/png"))],
    )
    assert unreferenced.status_code == 400


def test_malformed_multipart_is_rejected(client: TestClient) -> None:
    assert client.post("/print", files={"other": (None, "value")}).status_code == 400


class SlowMockPrinter(MockPrinter):
    def print_text(self, *args: object, **kwargs: object) -> None:
        super().print_text(*args, **kwargs)  # type: ignore[arg-type]
        time.sleep(0.02)


@pytest.mark.asyncio
async def test_complete_documents_cannot_interleave() -> None:
    printer = SlowMockPrinter()
    service = PrintingService(printer, Settings(_env_file=None))
    job_a = PrintDocument.model_validate(
        {"items": [{"type": "text", "text": "A1"}, {"type": "text", "text": "A2"}]}
    )
    job_b = PrintDocument.model_validate(
        {"items": [{"type": "text", "text": "B1"}, {"type": "text", "text": "B2"}]}
    )
    await asyncio.gather(service.print_document(job_a, {}), service.print_document(job_b, {}))
    values = [operation.value for operation in printer.operations if operation.kind == "text"]
    assert values in (["A1", "A2", "B1", "B2"], ["B1", "B2", "A1", "A2"])


@pytest.mark.asyncio
async def test_failed_job_releases_serialization_lock() -> None:
    printer = MockPrinter()
    service = PrintingService(printer, Settings(_env_file=None))
    printer.available = False
    with pytest.raises(PrinterUnavailableError):
        await service.print_document(
            PrintDocument.model_validate({"items": [{"type": "text", "text": "fail"}]}), {}
        )
    printer.available = True
    await service.print_document(
        PrintDocument.model_validate({"items": [{"type": "text", "text": "works"}]}), {}
    )
    assert [operation.value for operation in printer.operations if operation.kind == "text"] == [
        "works"
    ]
