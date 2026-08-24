from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families

from printer_agent.printer.mock import MockPrinter


def _metric_value(response_text: str, name: str, **labels: str) -> float:
    for family in text_string_to_metric_families(response_text):
        for sample in family.samples:
            if sample.name == name and sample.labels == labels:
                return sample.value
    raise AssertionError(f"Metric sample not found: {name}{labels}")


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
        "/print/prepared-image",
        "/print/feed",
        "/print",
    }
    content = paths["/print"]["post"]["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}
    assert "/metrics" not in paths


def test_metrics_report_successes_and_failures(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    assert client.post("/print/text", json={"text": "works"}).status_code == 200
    mock_printer.available = False
    assert client.post("/print/text", json={"text": "fails"}).status_code == 503

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert (
        _metric_value(
            response.text,
            "printer_agent_print_jobs_total",
            request_type="text",
            outcome="success",
        )
        == 1
    )
    assert (
        _metric_value(
            response.text,
            "printer_agent_print_jobs_total",
            request_type="text",
            outcome="error",
        )
        == 1
    )
    assert (
        _metric_value(
            response.text,
            "printer_agent_print_job_duration_seconds_count",
            request_type="text",
        )
        == 2
    )
    assert (
        _metric_value(
            response.text,
            "printer_agent_print_queue_wait_seconds_count",
            request_type="text",
        )
        == 2
    )
    assert _metric_value(response.text, "printer_agent_print_queue_depth") == 0
    assert _metric_value(response.text, "printer_agent_print_job_in_progress") == 0
    assert _metric_value(response.text, "printer_agent_last_successful_print_timestamp_seconds") > 0
