from pathlib import Path

import pytest
from pydantic import ValidationError

from printer_agent.config import PrinterBackend, Settings


def test_usb_ids_accept_hexadecimal_and_decimal() -> None:
    settings = Settings(
        _env_file=None,
        printer_backend="usb",
        printer_vendor_id="0x0483",  # type: ignore[arg-type]
        printer_product_id="1234",  # type: ignore[arg-type]
        printer_in_endpoint="0x81",  # type: ignore[arg-type]
        printer_out_endpoint="0x03",  # type: ignore[arg-type]
    )
    assert settings.printer_vendor_id == 0x0483
    assert settings.printer_product_id == 1234
    assert settings.printer_in_endpoint == 0x81
    assert settings.printer_out_endpoint == 0x03


def test_usb_backend_requires_both_identifiers() -> None:
    with pytest.raises(ValidationError, match="PRINTER_VENDOR_ID"):
        Settings(printer_backend="usb", _env_file=None)


def test_final_feed_defaults_to_three_lines_and_can_be_disabled() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.printer_final_feed_lines == 3
    assert defaults.printer_image_final_feed_lines is None
    assert Settings(printer_final_feed_lines=0, _env_file=None).printer_final_feed_lines == 0
    assert (
        Settings(printer_image_final_feed_lines="8", _env_file=None).printer_image_final_feed_lines
        == 8
    )


def test_settings_load_dotenv_automatically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "PRINTER_BACKEND=usb\nPRINTER_VENDOR_ID=0x0483\nPRINTER_PRODUCT_ID=0x1234\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.printer_backend is PrinterBackend.USB
    assert settings.printer_vendor_id == 0x0483
    assert settings.printer_product_id == 0x1234


def test_environment_variables_override_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("PRINTER_DOTS_WIDTH=384\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRINTER_DOTS_WIDTH", "576")

    assert Settings().printer_dots_width == 576
