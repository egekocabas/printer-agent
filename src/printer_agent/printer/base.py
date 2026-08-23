"""Hardware-independent printer contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL.Image import Image

from printer_agent.api.models import Align, TextSize


@dataclass(frozen=True, slots=True)
class PrinterStatus:
    configured: bool
    reachable: bool
    backend: str
    model: str | None = None
    hardware_status: str | None = None
    detail: str | None = None


class Printer(ABC):
    @abstractmethod
    def print_text(
        self,
        text: str,
        *,
        align: Align = Align.LEFT,
        bold: bool = False,
        size: TextSize = TextSize.NORMAL,
    ) -> None: ...

    @abstractmethod
    def print_image(self, image: Image) -> None: ...

    @abstractmethod
    def print_qr(
        self,
        data: str,
        *,
        align: Align = Align.CENTER,
        size: int = 6,
    ) -> None: ...

    @abstractmethod
    def feed(self, lines: int = 1) -> None: ...

    @abstractmethod
    def get_status(self) -> PrinterStatus: ...

    @abstractmethod
    def close(self) -> None: ...
