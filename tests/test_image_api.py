import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from printer_agent.config import Settings
from printer_agent.image.decoder import register_image_openers
from printer_agent.main import create_app
from printer_agent.printer.mock import MockPrinter
from tests.image_helpers import image_bytes, mpo_image_bytes


def test_image_upload_uses_decoded_content_not_filename_or_mime(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    response = client.post(
        "/print/image",
        files={"image": ("misleading.txt", image_bytes("PNG", size=(800, 400)), "text/plain")},
    )
    assert response.status_code == 200
    operation = mock_printer.operations[0]
    assert operation.kind == "image"
    assert operation.options == {"size": (384, 192), "mode": "1"}


def test_image_upload_prints_optional_date_and_time_caption(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    response = client.post(
        "/print/image",
        data={"date": "27/02/2026", "time": "18:34"},
        files={"image": ("photo.jpg", image_bytes("JPEG"), "image/jpeg")},
    )

    assert response.status_code == 200
    assert [operation.kind for operation in mock_printer.operations] == [
        "image",
        "feed",
        "text",
        "feed",
    ]
    assert mock_printer.operations[1].value == 1
    caption = mock_printer.operations[2]
    assert caption.value == "27/02/2026 18:34"
    assert caption.options["align"] == "center"


def test_image_upload_prints_date_without_time(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    response = client.post(
        "/print/image",
        data={"date": "27/02/2026"},
        files={"image": ("photo.jpg", image_bytes("JPEG"), "image/jpeg")},
    )

    assert response.status_code == 200
    assert mock_printer.operations[1].kind == "feed"
    assert mock_printer.operations[1].value == 1
    assert mock_printer.operations[2].value == "27/02/2026"


def test_image_caption_gap_can_be_configured() -> None:
    settings = Settings(printer_image_caption_gap_lines=3, _env_file=None)
    printer = MockPrinter()
    with TestClient(create_app(settings=settings, printer=printer)) as client:
        response = client.post(
            "/print/image",
            data={"date": "27/02/2026"},
            files={"image": ("photo.jpg", image_bytes("JPEG"), "image/jpeg")},
        )

    assert response.status_code == 200
    assert [operation.kind for operation in printer.operations] == [
        "image",
        "feed",
        "text",
        "feed",
    ]
    assert printer.operations[1].value == 3


def test_image_caption_rejects_invalid_date_or_time(client: TestClient) -> None:
    image = image_bytes("JPEG")
    invalid_date = client.post(
        "/print/image",
        data={"date": "31/02/2026"},
        files={"image": ("photo.jpg", image, "image/jpeg")},
    )
    time_without_date = client.post(
        "/print/image",
        data={"time": "18:34"},
        files={"image": ("photo.jpg", image, "image/jpeg")},
    )
    invalid_time = client.post(
        "/print/image",
        data={"date": "27/02/2026", "time": "25:00"},
        files={"image": ("photo.jpg", image, "image/jpeg")},
    )

    assert invalid_date.status_code == 400
    assert time_without_date.status_code == 400
    assert invalid_time.status_code == 400


def test_malformed_and_unsupported_uploads(client: TestClient) -> None:
    malformed = client.post("/print/image", files={"image": ("photo.jpg", b"broken", "image/jpeg")})
    assert malformed.status_code == 400
    unsupported = client.post(
        "/print/image",
        files={"image": ("animation.gif", image_bytes("GIF"), "image/gif")},
    )
    assert unsupported.status_code == 415


def test_encoded_upload_limit_is_enforced() -> None:
    settings = Settings(max_image_upload_bytes=1024, _env_file=None)
    printer = MockPrinter()
    with TestClient(create_app(settings=settings, printer=printer)) as client:
        response = client.post(
            "/print/image",
            files={"image": ("huge.jpg", b"x" * 1025, "image/jpeg")},
        )
    assert response.status_code == 413
    assert printer.operations == []


def test_image_specific_final_feed_overrides_general_feed() -> None:
    settings = Settings(
        printer_final_feed_lines=5,
        printer_image_final_feed_lines=8,
        _env_file=None,
    )
    printer = MockPrinter()
    with TestClient(create_app(settings=settings, printer=printer)) as client:
        image_response = client.post(
            "/print/image",
            files={"image": ("photo.png", image_bytes("PNG"), "image/png")},
        )
        document_response = client.post(
            "/print",
            data={"document": json.dumps({"items": [{"type": "image", "file": "photo.png"}]})},
            files=[("images", ("photo.png", image_bytes("PNG"), "image/png"))],
        )

    assert image_response.status_code == 200
    assert document_response.status_code == 200
    assert [operation.value for operation in printer.operations if operation.kind == "feed"] == [
        8,
        8,
    ]


def test_heif_upload_through_actual_api(client: TestClient, mock_printer: MockPrinter) -> None:
    register_image_openers()
    response = client.post(
        "/print/image",
        files={"image": ("IMG_1234.HEIC", image_bytes("HEIF"), "image/heic")},
    )
    assert response.status_code == 200, response.text
    assert mock_printer.operations[0].kind == "image"


def test_mpo_with_jpeg_filename_prints_primary_image(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    response = client.post(
        "/print/image",
        files={"image": ("IMG_0284.jpeg", mpo_image_bytes(size=(80, 40)), "image/jpeg")},
    )

    assert response.status_code == 200, response.text
    operation = mock_printer.operations[0]
    assert operation.kind == "image"
    assert operation.options == {"size": (80, 40), "mode": "1"}


def test_decoded_dimension_limit_maps_to_413() -> None:
    settings = Settings(
        max_image_pixels=1_000_000,
        max_image_upload_bytes=2_000_000,
        _env_file=None,
    )
    printer = MockPrinter()
    image = Image.new("L", (1100, 1000), 255)
    output = io.BytesIO()
    image.save(output, format="PNG")
    with TestClient(create_app(settings=settings, printer=printer)) as client:
        response = client.post(
            "/print/image",
            files={"image": ("large.png", output.getvalue(), "image/png")},
        )
    assert response.status_code == 413


def test_multipart_document_image_pipeline_is_reused(
    client: TestClient, mock_printer: MockPrinter
) -> None:
    document = {
        "items": [
            {"type": "text", "text": "Photo"},
            {"type": "image", "file": "photo1.png"},
            {"type": "feed", "lines": 2},
        ]
    }
    response = client.post(
        "/print",
        data={"document": json.dumps(document)},
        files=[("images", ("photo1.png", image_bytes("PNG"), "image/png"))],
    )
    assert response.status_code == 200, response.text
    assert [item.kind for item in mock_printer.operations] == ["text", "image", "feed", "feed"]
