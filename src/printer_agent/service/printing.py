"""Serialized execution of complete print jobs."""

import asyncio
import io
import logging
import time
from collections.abc import Callable

from anyio import to_thread
from PIL.Image import Image

from printer_agent.api.models import (
    FeedItem,
    FeedRequest,
    ImageItem,
    PrintDocument,
    QrItem,
    QrRequest,
    TextItem,
    TextRequest,
)
from printer_agent.config import Settings
from printer_agent.exceptions import InvalidPrintDocumentError
from printer_agent.image import (
    add_caption,
    decode_image,
    decode_prepared_image,
    prepare_for_thermal_print,
    simulate_thermal_output,
)
from printer_agent.metrics import PrinterMetrics
from printer_agent.printer.base import Printer, PrinterStatus

logger = logging.getLogger(__name__)


class PrintingService:
    """Prepare jobs off-loop and serialize all access to one printer."""

    def __init__(self, printer: Printer, settings: Settings) -> None:
        self.printer = printer
        self.settings = settings
        self.metrics = PrinterMetrics()
        self._print_lock = asyncio.Lock()

    def _validate_text(self, value: str, *, name: str = "text") -> None:
        if len(value) > self.settings.max_text_characters:
            raise InvalidPrintDocumentError(
                f"{name} exceeds the {self.settings.max_text_characters} character limit"
            )

    def _validate_qr(self, value: str) -> None:
        if len(value) > self.settings.max_qr_characters:
            raise InvalidPrintDocumentError(
                f"QR data exceeds the {self.settings.max_qr_characters} character limit"
            )

    async def _run_serialized(
        self,
        job: Callable[[], None],
        *,
        request_type: str,
        final_feed_lines: int | None = None,
    ) -> None:
        started = time.monotonic()
        logger.info("Print request received", extra={"request_type": request_type})
        resolved_final_feed_lines = (
            self.settings.printer_final_feed_lines if final_feed_lines is None else final_feed_lines
        )

        def job_with_final_feed() -> None:
            job()
            if resolved_final_feed_lines:
                self.printer.feed(resolved_final_feed_lines)

        self.metrics.queue_depth.inc()
        try:
            await self._print_lock.acquire()
        finally:
            self.metrics.queue_depth.dec()

        self.metrics.queue_wait.labels(request_type=request_type).observe(
            time.monotonic() - started
        )
        self.metrics.in_progress.set(1)
        try:
            try:
                logger.info("Printing started", extra={"request_type": request_type})
                await to_thread.run_sync(job_with_final_feed)
            except Exception:
                self.metrics.jobs.labels(request_type=request_type, outcome="error").inc()
                logger.error(
                    "Printing failed",
                    extra={"request_type": request_type},
                    exc_info=True,
                )
                raise
            else:
                self.metrics.jobs.labels(request_type=request_type, outcome="success").inc()
                self.metrics.last_success.set_to_current_time()
                logger.info(
                    "Printing completed",
                    extra={
                        "request_type": request_type,
                        "duration_seconds": time.monotonic() - started,
                    },
                )
        finally:
            self.metrics.duration.labels(request_type=request_type).observe(
                time.monotonic() - started
            )
            self.metrics.in_progress.set(0)
            self._print_lock.release()

    async def prepare_image(self, data: bytes, *, caption: str | None = None) -> Image:
        def prepare() -> Image:
            decoded = decode_image(data, max_pixels=self.settings.max_image_pixels)
            image = prepare_for_thermal_print(
                decoded.image,
                printable_width=self.settings.printer_dots_width,
                brightness=self.settings.printer_image_brightness,
                contrast=self.settings.printer_image_contrast,
            )
            return add_caption(
                image,
                caption,
                printable_width=self.settings.printer_dots_width,
                gap_lines=self.settings.printer_image_caption_gap_lines,
            )

        return await to_thread.run_sync(prepare)

    async def preview_images(
        self, data: bytes, *, caption: str | None = None
    ) -> tuple[bytes, bytes]:
        image = await self.prepare_image(data, caption=caption)

        def encode_pngs() -> tuple[bytes, bytes]:
            exact_output = io.BytesIO()
            image.save(exact_output, format="PNG")
            preview = simulate_thermal_output(
                image,
                smoothing_radius=self.settings.printer_preview_smoothing_radius,
            )
            enhanced_output = io.BytesIO()
            preview.save(enhanced_output, format="PNG")
            return exact_output.getvalue(), enhanced_output.getvalue()

        return await to_thread.run_sync(encode_pngs)

    async def print_text(self, request: TextRequest) -> None:
        self._validate_text(request.text)
        await self._run_serialized(
            lambda: self.printer.print_text(
                request.text,
                align=request.align,
                bold=request.bold,
                size=request.size,
            ),
            request_type="text",
        )

    async def print_qr(self, request: QrRequest) -> None:
        self._validate_qr(request.data)
        if request.label is not None:
            self._validate_text(request.label, name="label")

        def job() -> None:
            self.printer.print_qr(request.data, align=request.align, size=request.size)
            if request.label:
                self.printer.print_text(request.label, align=request.align)

        await self._run_serialized(job, request_type="qr")

    async def print_image(self, data: bytes, *, caption: str | None = None) -> None:
        image = await self.prepare_image(data, caption=caption)

        await self._run_serialized(
            lambda: self.printer.print_image(image),
            request_type="image",
            final_feed_lines=self.settings.printer_image_final_feed_lines,
        )

    async def print_prepared_image(self, data: bytes) -> None:
        image = await to_thread.run_sync(
            lambda: decode_prepared_image(
                data,
                printable_width=self.settings.printer_dots_width,
                max_pixels=self.settings.max_image_pixels,
            )
        )
        await self._run_serialized(
            lambda: self.printer.print_image(image),
            request_type="prepared_image",
            final_feed_lines=self.settings.printer_image_final_feed_lines,
        )

    async def feed(self, request: FeedRequest) -> None:
        await self._run_serialized(
            lambda: self.printer.feed(request.lines),
            request_type="feed",
            final_feed_lines=0,
        )

    async def print_document(self, document: PrintDocument, images: dict[str, bytes]) -> None:
        if len(document.items) > self.settings.max_document_items:
            raise InvalidPrintDocumentError(
                f"Document exceeds the {self.settings.max_document_items} item limit"
            )

        prepared_images: dict[str, Image] = {}
        referenced_files = {item.file for item in document.items if isinstance(item, ImageItem)}
        missing_files = sorted(referenced_files - images.keys())
        if missing_files:
            raise InvalidPrintDocumentError(
                f"Missing multipart image file(s): {', '.join(missing_files)}"
            )
        unreferenced_files = sorted(images.keys() - referenced_files)
        if unreferenced_files:
            raise InvalidPrintDocumentError(
                f"Unreferenced multipart image file(s): {', '.join(unreferenced_files)}"
            )

        for file_name in referenced_files:
            prepared_images[file_name] = await self.prepare_image(images[file_name])

        for item in document.items:
            if isinstance(item, TextItem):
                self._validate_text(item.text)
            elif isinstance(item, QrItem):
                self._validate_qr(item.data)
                if item.label is not None:
                    self._validate_text(item.label, name="label")

        def job() -> None:
            for item in document.items:
                if isinstance(item, TextItem):
                    self.printer.print_text(
                        item.text,
                        align=item.align,
                        bold=item.bold,
                        size=item.size,
                    )
                elif isinstance(item, QrItem):
                    self.printer.print_qr(item.data, align=item.align, size=item.size)
                    if item.label:
                        self.printer.print_text(item.label, align=item.align)
                elif isinstance(item, FeedItem):
                    self.printer.feed(item.lines)
                elif isinstance(item, ImageItem):
                    self.printer.print_image(prepared_images[item.file])

        contains_image = any(isinstance(item, ImageItem) for item in document.items)
        await self._run_serialized(
            job,
            request_type="document",
            final_feed_lines=(
                self.settings.printer_image_final_feed_lines if contains_image else None
            ),
        )

    async def get_status(self) -> PrinterStatus:
        return await to_thread.run_sync(self.printer.get_status)

    async def close(self) -> None:
        await to_thread.run_sync(self.printer.close)
