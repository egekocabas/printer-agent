"""In-memory printer backend for development and tests."""

from dataclasses import dataclass
from threading import Lock
from typing import Any

from PIL.Image import Image

from printer_agent.api.models import Align, TextSize
from printer_agent.exceptions import PrinterUnavailableError
from printer_agent.printer.base import Printer, PrinterStatus


@dataclass(frozen=True, slots=True)
class MockOperation:
    kind: str
    value: Any
    options: dict[str, Any]


class MockPrinter(Printer):
    """Record operations without producing ESC/POS output."""

    def __init__(self, *, model: str | None = "MockPrinter") -> None:
        self.model = model
        self.operations: list[MockOperation] = []
        self.available = True
        self._operations_lock = Lock()

    def _record(self, operation: MockOperation) -> None:
        if not self.available:
            raise PrinterUnavailableError("Printer is unavailable")
        with self._operations_lock:
            self.operations.append(operation)

    def print_text(
        self,
        text: str,
        *,
        align: Align = Align.LEFT,
        bold: bool = False,
        size: TextSize = TextSize.NORMAL,
    ) -> None:
        self._record(
            MockOperation(
                "text",
                text,
                {"align": align.value, "bold": bold, "size": size.value},
            )
        )

    def print_image(self, image: Image) -> None:
        self._record(MockOperation("image", image.copy(), {"size": image.size, "mode": image.mode}))

    def print_qr(
        self,
        data: str,
        *,
        align: Align = Align.CENTER,
        size: int = 6,
    ) -> None:
        self._record(MockOperation("qr", data, {"align": align.value, "size": size}))

    def feed(self, lines: int = 1) -> None:
        self._record(MockOperation("feed", lines, {}))

    def get_status(self) -> PrinterStatus:
        return PrinterStatus(
            configured=True,
            reachable=self.available,
            backend="mock",
            model=self.model,
            hardware_status=None,
            detail=None if self.available else "Mock printer is configured as unavailable",
        )

    def close(self) -> None:
        return None

    def clear(self) -> None:
        with self._operations_lock:
            self.operations.clear()
