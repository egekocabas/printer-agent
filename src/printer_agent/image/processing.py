"""Convert decoded images into high-quality monochrome thermal rasters."""

import logging

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

logger = logging.getLogger(__name__)

CAPTION_FONT_SIZE_DOTS = 24
CAPTION_LINE_HEIGHT_DOTS = 24


def prepare_for_thermal_print(
    image: Image.Image,
    *,
    printable_width: int,
    brightness: float = 1.25,
    contrast: float = 1.05,
) -> Image.Image:
    """Resize without cropping or upscaling, then contrast and dither to one bit."""

    working = image
    if working.width > printable_width:
        output_height = max(1, round(working.height * printable_width / working.width))
        working = working.resize((printable_width, output_height), Image.Resampling.LANCZOS)

    grayscale = ImageOps.grayscale(working)
    brightened = ImageEnhance.Brightness(grayscale).enhance(brightness)
    contrasted = ImageEnhance.Contrast(brightened).enhance(contrast)
    thermal = contrasted.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    logger.info(
        "Image prepared for thermal printing",
        extra={"input_dimensions": image.size, "processed_dimensions": thermal.size},
    )
    return thermal


def add_caption(
    image: Image.Image,
    caption: str | None,
    *,
    printable_width: int,
    gap_lines: int,
) -> Image.Image:
    """Add a centered caption to the exact monochrome raster sent to the printer."""

    if caption is None:
        return image

    font = ImageFont.load_default(size=CAPTION_FONT_SIZE_DOTS)
    measurement = ImageDraw.Draw(Image.new("1", (1, 1), 1))
    left, top, right, bottom = measurement.textbbox((0, 0), caption, font=font)
    text_width = round(right - left)
    text_height = round(bottom - top)
    canvas_width = max(printable_width, image.width, text_width)
    gap_dots = gap_lines * CAPTION_LINE_HEIGHT_DOTS
    canvas = Image.new("1", (canvas_width, image.height + gap_dots + text_height), 1)
    canvas.paste(image, (0, 0))

    draw = ImageDraw.Draw(canvas)
    text_x = (canvas_width - text_width) // 2 - left
    text_y = image.height + gap_dots - top
    draw.text((text_x, text_y), caption, font=font, fill=0)
    return canvas


def simulate_thermal_output(image: Image.Image, *, smoothing_radius: float) -> Image.Image:
    """Approximate thermal dot spread for display without changing print data."""

    preview = image.convert("L")
    if smoothing_radius == 0:
        return preview
    return preview.filter(ImageFilter.GaussianBlur(radius=smoothing_radius))
