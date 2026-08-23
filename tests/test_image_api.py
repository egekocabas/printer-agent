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
