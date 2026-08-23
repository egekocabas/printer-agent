"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from printer_agent.api.routes import router
from printer_agent.config import Settings
from printer_agent.dependencies import build_printer
from printer_agent.exceptions import (
    ImageTooLargeError,
    InvalidImageError,
    InvalidPrintDocumentError,
    PrinterCommunicationError,
    PrinterUnavailableError,
    UnsupportedImageFormatError,
)
from printer_agent.image import register_image_openers
from printer_agent.printer.base import Printer
from printer_agent.service import PrintingService

logger = logging.getLogger(__name__)


def create_app(*, settings: Settings | None = None, printer: Printer | None = None) -> FastAPI:
    """Create an isolated application, optionally injecting a printer for tests."""

    resolved_settings = settings or Settings()
    resolved_printer = printer or build_printer(resolved_settings)
    service = PrintingService(resolved_printer, resolved_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        register_image_openers()
        application.state.settings = resolved_settings
        application.state.printing_service = service
        logger.info(
            "Application started",
            extra={"printer_backend": resolved_settings.printer_backend.value},
        )
        try:
            yield
        finally:
            await service.close()
            logger.info("Application stopped")

    application = FastAPI(
        title="printer-agent",
        version="0.1.0",
        description="A generic HTTP interface to ESC/POS thermal printers.",
        lifespan=lifespan,
    )
    application.include_router(router)

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Expose application metrics for an internal Prometheus scraper."""

        return Response(
            content=generate_latest(service.metrics.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    @application.exception_handler(ImageTooLargeError)
    async def image_too_large_handler(_request: Request, exc: ImageTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(exc)})

    @application.exception_handler(UnsupportedImageFormatError)
    async def unsupported_image_handler(
        _request: Request, exc: UnsupportedImageFormatError
    ) -> JSONResponse:
        return JSONResponse(status_code=415, content={"detail": str(exc)})

    @application.exception_handler(InvalidImageError)
    async def invalid_image_handler(_request: Request, exc: InvalidImageError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(InvalidPrintDocumentError)
    async def invalid_document_handler(
        _request: Request, exc: InvalidPrintDocumentError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(PrinterUnavailableError)
    async def unavailable_handler(_request: Request, exc: PrinterUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(PrinterCommunicationError)
    async def communication_handler(
        _request: Request, exc: PrinterCommunicationError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return application


app = create_app()
