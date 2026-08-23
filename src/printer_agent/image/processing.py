"""Convert decoded images into high-quality monochrome thermal rasters."""

import logging

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)


def prepare_for_thermal_print(image: Image.Image, *, printable_width: int) -> Image.Image:
    """Resize without cropping or upscaling, then contrast and dither to one bit."""

    working = image
    if working.width > printable_width:
        output_height = max(1, round(working.height * printable_width / working.width))
        working = working.resize((printable_width, output_height), Image.Resampling.LANCZOS)

    grayscale = ImageOps.grayscale(working)
    contrasted = ImageEnhance.Contrast(grayscale).enhance(1.15)
    thermal = contrasted.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    logger.info(
        "Image prepared for thermal printing",
        extra={"input_dimensions": image.size, "processed_dimensions": thermal.size},
    )
    return thermal
