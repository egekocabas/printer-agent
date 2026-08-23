"""Central application configuration."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PrinterBackend(StrEnum):
    MOCK = "mock"
    USB = "usb"


def _parse_optional_int(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return int(value, 0)
    return value


OptionalEnvironmentInt = Annotated[int | None, BeforeValidator(_parse_optional_int)]
EnvironmentInt = Annotated[int, BeforeValidator(_parse_optional_int)]


class Settings(BaseSettings):
    """Settings loaded from environment variables or explicit constructor values."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    printer_backend: PrinterBackend = PrinterBackend.MOCK
    printer_vendor_id: OptionalEnvironmentInt = None
    printer_product_id: OptionalEnvironmentInt = None
    printer_in_endpoint: EnvironmentInt = Field(default=0x82, ge=0x80, le=0x8F)
    printer_out_endpoint: EnvironmentInt = Field(default=0x01, ge=0x01, le=0x0F)
    printer_profile: str | None = None
    printer_dots_width: int = Field(default=384, ge=64, le=4096)
    printer_model_name: str | None = "ANJET58"
    printer_final_feed_lines: int = Field(default=3, ge=0, le=20)
    printer_image_final_feed_lines: OptionalEnvironmentInt = Field(default=None, ge=0, le=20)

    max_image_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    max_image_pixels: int = Field(default=50_000_000, ge=1_000_000)
    max_text_characters: int = Field(default=10_000, ge=1, le=1_000_000)
    max_qr_characters: int = Field(default=4_096, ge=1, le=100_000)
    max_document_items: int = Field(default=100, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_usb_configuration(self) -> "Settings":
        if self.printer_backend is PrinterBackend.USB:
            missing = []
            if self.printer_vendor_id is None:
                missing.append("PRINTER_VENDOR_ID")
            if self.printer_product_id is None:
                missing.append("PRINTER_PRODUCT_ID")
            if missing:
                joined = " and ".join(missing)
                raise ValueError(f"{joined} must be set when PRINTER_BACKEND=usb")
        return self
