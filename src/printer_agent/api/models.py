"""Typed API request and response models."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Align(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class TextSize(StrEnum):
    NORMAL = "normal"
    DOUBLE_WIDTH = "double_width"
    DOUBLE_HEIGHT = "double_height"
    DOUBLE = "double"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"


class PrintResponse(StrictModel):
    status: Literal["printed"] = "printed"


class ImagePreviewResponse(StrictModel):
    exact_print_image: str = Field(description="Base64-encoded monochrome print PNG.")
    enhanced_preview_image: str = Field(description="Base64-encoded smoothed preview PNG.")


class PrinterStatusResponse(StrictModel):
    configured: bool
    reachable: bool
    backend: str
    model: str | None
    hardware_status: Literal["ready", "paper_out", "error", "unknown"] | None = Field(
        default=None,
        description=(
            "Normalized device status: ready, paper_out, error, unknown, or null when the "
            "printer does not support reliable real-time status."
        ),
    )
    detail: str | None = Field(
        default=None,
        description="Safe configuration or reachability detail, when relevant.",
    )


class TextRequest(StrictModel):
    text: str = Field(min_length=1)
    align: Align = Align.LEFT
    bold: bool = False
    size: TextSize = TextSize.NORMAL


class QrRequest(StrictModel):
    data: str = Field(min_length=1)
    align: Align = Align.CENTER
    label: str | None = None
    size: int = Field(default=6, ge=1, le=16)


class FeedRequest(StrictModel):
    lines: int = Field(
        default=1,
        ge=1,
        le=255,
        description="Number of blank lines to feed through the printer.",
    )


class TextItem(TextRequest):
    type: Literal["text"] = "text"


class QrItem(QrRequest):
    type: Literal["qr"] = "qr"


class FeedItem(StrictModel):
    type: Literal["feed"] = "feed"
    lines: int = Field(default=1, ge=1, le=20)


class ImageItem(StrictModel):
    type: Literal["image"] = "image"
    file: str = Field(
        min_length=1,
        max_length=255,
        description="Filename of a part in the multipart 'images' field.",
    )


PrintItem = Annotated[TextItem | QrItem | FeedItem | ImageItem, Field(discriminator="type")]


class PrintDocument(StrictModel):
    items: list[PrintItem] = Field(min_length=1)
