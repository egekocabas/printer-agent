"""USB ESC/POS printer backend."""

import logging
from collections.abc import Callable
from typing import Any

from PIL.Image import Image

from printer_agent.api.models import Align, TextSize
from printer_agent.config import Settings
from printer_agent.exceptions import (
    PrinterCommunicationError,
    PrinterConfigurationError,
    PrinterUnavailableError,
)
from printer_agent.printer.base import Printer, PrinterStatus

logger = logging.getLogger(__name__)


class EscPosPrinter(Printer):
    """A reconnecting USB adapter around python-escpos."""

    def __init__(self, settings: Settings) -> None:
        if settings.printer_vendor_id is None or settings.printer_product_id is None:
            raise PrinterConfigurationError(
                "USB backend requires PRINTER_VENDOR_ID and PRINTER_PRODUCT_ID"
            )
        self._vendor_id = settings.printer_vendor_id
        self._product_id = settings.printer_product_id
        self._in_endpoint = settings.printer_in_endpoint
        self._out_endpoint = settings.printer_out_endpoint
        self._profile = settings.printer_profile
        self._model = settings.printer_model_name
        self._device: Any | None = None

    def _connect(self) -> Any:
        if self._device is not None:
            return self._device
        try:
            from escpos.printer import Usb  # type: ignore[import-untyped]

            kwargs: dict[str, Any] = {}
            if self._profile:
                kwargs["profile"] = self._profile
            device = Usb(
                self._vendor_id,
                self._product_id,
                in_ep=self._in_endpoint,
                out_ep=self._out_endpoint,
                **kwargs,
            )
            device.open()
        except Exception as exc:
            logger.warning("USB printer unavailable", exc_info=True)
            raise PrinterUnavailableError("Configured USB printer is unavailable") from exc
        self._device = device
        logger.info("Printer connection established")
        return device

    def _disconnect_after_failure(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            try:
                device.close()
            except Exception:
                logger.debug("Failed to close printer after communication error", exc_info=True)

    def _execute(self, operation: Callable[[Any], None]) -> None:
        was_connected = self._device is not None
        device = self._connect()
        try:
            operation(device)
        except (PrinterUnavailableError, PrinterConfigurationError):
            raise
        except Exception as exc:
            self._disconnect_after_failure()
            logger.error("ESC/POS communication failed", exc_info=True)
            if was_connected:
                raise PrinterCommunicationError("Printer communication failed") from exc
            raise PrinterUnavailableError("Configured USB printer is unavailable") from exc

    def print_text(
        self,
        text: str,
        *,
        align: Align = Align.LEFT,
        bold: bool = False,
        size: TextSize = TextSize.NORMAL,
    ) -> None:
        double_width = size in {TextSize.DOUBLE_WIDTH, TextSize.DOUBLE}
        double_height = size in {TextSize.DOUBLE_HEIGHT, TextSize.DOUBLE}

        def operation(device: Any) -> None:
            device.set_with_default(
                align=align.value,
                bold=bold,
                double_width=double_width,
                double_height=double_height,
            )
            device.text(text)

        self._execute(operation)

    def print_image(self, image: Image) -> None:
        self._execute(lambda device: device.image(image, impl="bitImageRaster"))

    def print_qr(
        self,
        data: str,
        *,
        align: Align = Align.CENTER,
        size: int = 6,
    ) -> None:
        def operation(device: Any) -> None:
            device.set(align=align.value)
            device.qr(data, size=size, native=False, center=align is Align.CENTER)

        self._execute(operation)

    def feed(self, lines: int = 1) -> None:
        self._execute(lambda device: device.print_and_feed(lines))

    def get_status(self) -> PrinterStatus:
        try:
            self._connect()
        except PrinterUnavailableError as exc:
            return PrinterStatus(
                configured=True,
                reachable=False,
                backend="usb",
                model=self._model,
                hardware_status=None,
                detail=str(exc),
            )
        return PrinterStatus(
            configured=True,
            reachable=True,
            backend="usb",
            model=self._model,
            hardware_status=None,
            detail="Connection opened; detailed hardware status is not queried reliably",
        )

    def close(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            try:
                device.close()
            except Exception:
                logger.warning("Failed to close USB printer cleanly", exc_info=True)
