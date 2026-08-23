from fastapi.testclient import TestClient

from printer_agent.printer.mock import MockPrinter


def test_health_is_independent_of_printer(client: TestClient, mock_printer: MockPrinter) -> None:
    mock_printer.available = False
    assert client.get("/health").json() == {"status": "ok"}


def test_printer_status_reports_known_and_unknown_values(client: TestClient) -> None:
    response = client.get("/printer/status")
    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "reachable": True,
        "backend": "mock",
        "model": "TestPrinter",
        "hardware_status": None,
        "detail": None,
    }


def test_unreachable_printer_does_not_make_status_endpoint_fail(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    mock_printer.available = False
    response = client.get("/printer/status")
    assert response.status_code == 200
    assert response.json()["reachable"] is False


def test_openapi_documents_every_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) >= {
        "/health",
        "/printer/status",
        "/print/text",
        "/print/qr",
        "/print/image",
        "/print/feed",
        "/print",
    }
    content = paths["/print"]["post"]["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}
