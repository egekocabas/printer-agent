"""USB ESC/POS printer backend."""

import logging
from collections.abc import Callable
from typing import Any

from PIL.Image import Image
from usb.core import USBTimeoutError  # type: ignore[import-untyped]

from printer_agent.api.models import Align, TextSize
from printer_agent.config import Settings
from printer_agent.exceptions import (
    PrinterCommunicationError,
    PrinterConfigurationError,
    PrinterUnavailableError,
)
from printer_agent.printer.base import HardwareStatus, Printer, PrinterStatus

logger = logging.getLogger(__name__)

_REALTIME_STATUS_COMMAND = b"\x10\x04"
_REALTIME_STATUS_PARAMETERS = range(1, 5)
_STATUS_FIXED_BITS_MASK = 0x93
_STATUS_FIXED_BITS_VALUE = 0x12


class _UnsupportedRealtimeStatusError(Exception):
    """A connected printer did not return a valid ESC/POS status byte."""


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
        for attempt in range(2):
            try:
                operation(self._connect())
                return
            except (PrinterUnavailableError, PrinterConfigurationError):
                raise
            except Exception as exc:
                self._disconnect_after_failure()
                if attempt == 0:
                    logger.warning("ESC/POS communication failed; reconnecting", exc_info=True)
                    continue
                logger.error("ESC/POS communication failed after reconnect", exc_info=True)
                raise PrinterCommunicationError("Printer communication failed") from exc

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

    @staticmethod
    def _normalize_hardware_status(statuses: dict[int, int]) -> HardwareStatus:
        printer_status = statuses[1]
        offline_status = statuses[2]
        error_status = statuses[3]
        paper_status = statuses[4]

        if offline_status & 0x20 or paper_status & 0x60 == 0x60:
            return HardwareStatus.PAPER_OUT
        if offline_status & 0x40 or error_status & 0x6C:
            return HardwareStatus.ERROR
        if printer_status & 0x08 or offline_status & 0x04:
            return HardwareStatus.UNKNOWN
        return HardwareStatus.READY

    def _query_hardware_status(self, device: Any) -> HardwareStatus:
        statuses: dict[int, int] = {}
        for parameter in _REALTIME_STATUS_PARAMETERS:
            device._raw(_REALTIME_STATUS_COMMAND + bytes((parameter,)))
            response = device._read()
            if not response:
                raise _UnsupportedRealtimeStatusError("Printer returned an empty status response")
            value = int(response[0])
            if value & _STATUS_FIXED_BITS_MASK != _STATUS_FIXED_BITS_VALUE:
                raise _UnsupportedRealtimeStatusError(
                    f"Printer returned an invalid status byte: 0x{value:02x}"
                )
            statuses[parameter] = value
        return self._normalize_hardware_status(statuses)

    def _unreachable_status(self, detail: str) -> PrinterStatus:
        return PrinterStatus(
            configured=True,
            reachable=False,
            backend="usb",
            model=self._model,
            hardware_status=None,
            detail=detail,
        )

    def get_status(self) -> PrinterStatus:
        for attempt in range(2):
            try:
                hardware_status = self._query_hardware_status(self._connect())
            except PrinterUnavailableError as exc:
                return self._unreachable_status(str(exc))
            except (USBTimeoutError, _UnsupportedRealtimeStatusError):
                return PrinterStatus(
                    configured=True,
                    reachable=True,
                    backend="usb",
                    model=self._model,
                    hardware_status=None,
                    detail="Connected; real-time ESC/POS status is unavailable",
                )
            except Exception:
                self._disconnect_after_failure()
                if attempt == 0:
                    logger.warning("ESC/POS status query failed; reconnecting", exc_info=True)
                    continue
                logger.error("ESC/POS status query failed after reconnect", exc_info=True)
                return self._unreachable_status("Printer communication failed")
            return PrinterStatus(
                configured=True,
                reachable=True,
                backend="usb",
                model=self._model,
                hardware_status=hardware_status,
                detail=None,
            )
        return self._unreachable_status("Printer communication failed")

    def close(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            try:
                device.close()
            except Exception:
                logger.warning("Failed to close USB printer cleanly", exc_info=True)
