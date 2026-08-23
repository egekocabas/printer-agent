from fastapi.testclient import TestClient

from printer_agent.printer.mock import MockPrinter


def test_print_text_records_typed_options(client: TestClient, mock_printer: MockPrinter) -> None:
    response = client.post(
        "/print/text",
        json={"text": "Hello", "align": "center", "bold": True, "size": "double"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "printed"}
    operation = mock_printer.operations[0]
    assert (operation.kind, operation.value) == ("text", "Hello")
    assert operation.options == {"align": "center", "bold": True, "size": "double"}
    assert mock_printer.operations[1].kind == "feed"
    assert mock_printer.operations[1].value == 3


def test_print_text_rejects_invalid_options(client: TestClient) -> None:
    response = client.post("/print/text", json={"text": "Hi", "align": "diagonal"})
    assert response.status_code == 422


def test_print_qr_and_optional_label(client: TestClient, mock_printer: MockPrinter) -> None:
    response = client.post(
        "/print/qr",
        json={"data": "https://example.com", "align": "right", "label": "Scan me"},
    )
    assert response.status_code == 200
    assert [operation.kind for operation in mock_printer.operations] == ["qr", "text", "feed"]
    assert mock_printer.operations[0].options["align"] == "right"
    assert mock_printer.operations[1].value == "Scan me"


def test_printer_unavailable_maps_to_503(client: TestClient, mock_printer: MockPrinter) -> None:
    mock_printer.available = False
    response = client.post("/print/text", json={"text": "No printer"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Printer is unavailable"}


def test_feed_endpoint_advances_exact_number_of_lines(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    response = client.post("/print/feed", json={"lines": 7})

    assert response.status_code == 200
    assert response.json() == {"status": "printed"}
    assert [(operation.kind, operation.value) for operation in mock_printer.operations] == [
        ("feed", 7)
    ]


def test_feed_endpoint_validates_line_count(client: TestClient) -> None:
    assert client.post("/print/feed", json={"lines": 0}).status_code == 422
    assert client.post("/print/feed", json={"lines": 256}).status_code == 422
