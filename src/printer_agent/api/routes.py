"""FastAPI routes with transport-only responsibilities."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from printer_agent.api.models import (
    FeedRequest,
    HealthResponse,
    PrintDocument,
    PrinterStatusResponse,
    PrintResponse,
    QrRequest,
    TextRequest,
)
from printer_agent.dependencies import get_printing_service
from printer_agent.exceptions import ImageTooLargeError, InvalidPrintDocumentError
from printer_agent.service.printing import PrintingService

router = APIRouter()

ServiceDependency = Annotated[PrintingService, Depends(get_printing_service)]


def _format_image_caption(date_value: str | None, time_value: str | None) -> str | None:
    if time_value is not None and date_value is None:
        raise InvalidPrintDocumentError("Image time requires an image date")
    if date_value is None:
        return None

    try:
        parsed_date = datetime.strptime(date_value, "%d/%m/%Y")
    except ValueError as exc:
        raise InvalidPrintDocumentError(
            "Image date must be a real date in DD/MM/YYYY format"
        ) from exc
    if parsed_date.strftime("%d/%m/%Y") != date_value:
        raise InvalidPrintDocumentError("Image date must use DD/MM/YYYY format")

    if time_value is None:
        return date_value
    try:
        parsed_time = datetime.strptime(time_value, "%H:%M")
    except ValueError as exc:
        raise InvalidPrintDocumentError("Image time must be a real time in HH:MM format") from exc
    if parsed_time.strftime("%H:%M") != time_value:
        raise InvalidPrintDocumentError("Image time must use 24-hour HH:MM format")
    return f"{date_value} {time_value}"


async def _read_limited_upload(upload: StarletteUploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(min(1024 * 1024, limit + 1 - total)):
        total += len(chunk)
        if total > limit:
            raise ImageTooLargeError(f"Image upload exceeds the {limit} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_document(value: Any) -> PrintDocument:
    try:
        if isinstance(value, str):
            return PrintDocument.model_validate_json(value)
        return PrintDocument.model_validate(value)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidPrintDocumentError("Invalid print document") from exc


@router.get("/health", response_model=HealthResponse, tags=["service"])
async def health() -> HealthResponse:
    """Report application health independently of printer availability."""

    return HealthResponse()


@router.get("/printer/status", response_model=PrinterStatusResponse, tags=["printer"])
async def printer_status(service: ServiceDependency) -> PrinterStatusResponse:
    """Report configuration, connection reachability, and known hardware status."""

    printer_state = await service.get_status()
    return PrinterStatusResponse(**asdict(printer_state))


@router.post("/print/text", response_model=PrintResponse, tags=["printing"])
async def print_text(request: TextRequest, service: ServiceDependency) -> PrintResponse:
    await service.print_text(request)
    return PrintResponse()


@router.post("/print/qr", response_model=PrintResponse, tags=["printing"])
async def print_qr(request: QrRequest, service: ServiceDependency) -> PrintResponse:
    await service.print_qr(request)
    return PrintResponse()


@router.post("/print/image", response_model=PrintResponse, tags=["printing"])
async def print_image(
    image: Annotated[
        UploadFile,
        File(description="JPEG, PNG, WebP, HEIC/HEIF, or AVIF image bytes."),
    ],
    service: ServiceDependency,
    date: Annotated[
        str | None,
        Form(description="Optional image date in DD/MM/YYYY format."),
    ] = None,
    time: Annotated[
        str | None,
        Form(description="Optional 24-hour image time in HH:MM format; requires date."),
    ] = None,
) -> PrintResponse:
    data = await _read_limited_upload(image, service.settings.max_image_upload_bytes)
    caption = _format_image_caption(date, time)
    await service.print_image(data, caption=caption)
    return PrintResponse()


@router.post("/print/feed", response_model=PrintResponse, tags=["printing"])
async def feed_paper(request: FeedRequest, service: ServiceDependency) -> PrintResponse:
    """Advance the paper by exactly the requested number of blank lines."""

    await service.feed(request)
    return PrintResponse()


DOCUMENT_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/PrintDocument"}},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["document"],
                    "properties": {
                        "document": {
                            "type": "string",
                            "description": "JSON-encoded PrintDocument.",
                        },
                        "images": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                            "description": "Files referenced by their uploaded filename.",
                        },
                    },
                }
            },
        },
    }
}


@router.post(
    "/print",
    response_model=PrintResponse,
    tags=["printing"],
    openapi_extra=DOCUMENT_OPENAPI,
    status_code=status.HTTP_200_OK,
)
async def print_document(request: Request, service: ServiceDependency) -> PrintResponse:
    """Print an atomic document from JSON, or multipart JSON plus named images."""

    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    images: dict[str, bytes] = {}

    if media_type == "application/json":
        try:
            document = _parse_document(await request.json())
        except json.JSONDecodeError as exc:
            raise InvalidPrintDocumentError("Invalid print document JSON") from exc
    elif media_type == "multipart/form-data":
        try:
            async with request.form(
                max_files=service.settings.max_document_items,
                max_fields=10,
                max_part_size=service.settings.max_image_upload_bytes + 1,
            ) as form:
                document_value = form.get("document")
                if not isinstance(document_value, str):
                    raise InvalidPrintDocumentError(
                        "Multipart requests require a JSON 'document' field"
                    )
                document = _parse_document(document_value)
                uploads = form.getlist("images")
                for upload in uploads:
                    if not isinstance(upload, StarletteUploadFile) or not upload.filename:
                        raise InvalidPrintDocumentError(
                            "Each 'images' part must be a file with a filename"
                        )
                    if upload.filename in images:
                        raise InvalidPrintDocumentError(
                            f"Duplicate multipart image filename: {upload.filename}"
                        )
                    images[upload.filename] = await _read_limited_upload(
                        upload, service.settings.max_image_upload_bytes
                    )
        except InvalidPrintDocumentError:
            raise
        except Exception as exc:
            raise InvalidPrintDocumentError("Malformed multipart print document") from exc
    else:
        raise InvalidPrintDocumentError(
            "Content-Type must be application/json or multipart/form-data"
        )

    await service.print_document(document, images)
    return PrintResponse()
