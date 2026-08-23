"""Application object construction and FastAPI dependencies."""

from typing import cast

from fastapi import Request

from printer_agent.config import PrinterBackend, Settings
from printer_agent.printer import EscPosPrinter, MockPrinter, Printer
from printer_agent.service.printing import PrintingService


def build_printer(settings: Settings) -> Printer:
    if settings.printer_backend is PrinterBackend.MOCK:
        return MockPrinter(model=settings.printer_model_name or "MockPrinter")
    return EscPosPrinter(settings)


def get_printing_service(request: Request) -> PrintingService:
    return cast(PrintingService, request.app.state.printing_service)
