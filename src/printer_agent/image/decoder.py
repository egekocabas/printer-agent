"""Decode untrusted image bytes into normalized Pillow images."""

from __future__ import annotations

import io
import logging
import warnings
from dataclasses import dataclass

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener  # type: ignore[import-untyped]

from printer_agent.exceptions import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = frozenset({"JPEG", "MPO", "PNG", "WEBP", "HEIF", "AVIF"})


@dataclass(frozen=True, slots=True)
class DecodedImage:
    image: Image.Image
    format: str
    original_size: tuple[int, int]


def register_image_openers() -> None:
    """Register HEIF/HEIC with Pillow; Pillow itself handles current AVIF files."""

    register_heif_opener(thumbnails=False)


def _apply_embedded_color_profile(image: Image.Image) -> Image.Image:
    profile = image.info.get("icc_profile")
    if not profile or image.mode not in {"RGB", "RGBA"}:
        return image
    try:
        source_profile = ImageCms.ImageCmsProfile(io.BytesIO(profile))
        target_profile = ImageCms.createProfile("sRGB")
        output_mode = image.mode
        converted = ImageCms.profileToProfile(
            image,
            source_profile,
            target_profile,
            outputMode=output_mode,
        )
        if converted is not None:
            return converted
        return image
    except (OSError, ValueError, ImageCms.PyCMSError):
        logger.debug("Could not apply embedded ICC profile; using Pillow conversion", exc_info=True)
        return image


def _normalize_mode(image: Image.Image) -> Image.Image:
    image = _apply_embedded_color_profile(image)
    has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        return Image.alpha_composite(background, rgba).convert("RGB")
    if image.mode == "L":
        return image.copy()
    return image.convert("RGB")


def _apply_orientation(image: Image.Image) -> Image.Image:
    """Apply ordinary EXIF orientation plus pillow-heif's preserved source value."""

    exif = image.getexif()
    original_orientation = image.info.get("original_orientation")
    if exif.get(274, 1) == 1 and original_orientation in range(2, 9):
        # pillow-heif resets EXIF orientation while retaining its original value in
        # ``info``. Restore it temporarily so Pillow remains the single authority
        # for the actual transpose mapping.
        exif[274] = original_orientation
    return ImageOps.exif_transpose(image)


def decode_image(data: bytes, *, max_pixels: int) -> DecodedImage:
    """Detect, fully decode, orient, and mode-normalize an image."""

    if not data:
        raise InvalidImageError("Uploaded image is empty")

    register_image_openers()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as opened:
                detected_format = (opened.format or "").upper()
                if detected_format not in SUPPORTED_FORMATS:
                    raise UnsupportedImageFormatError(
                        f"Unsupported image format: {detected_format or 'unknown'}"
                    )
                original_size = opened.size
                width, height = original_size
                if width < 1 or height < 1 or width * height > max_pixels:
                    raise ImageTooLargeError(f"Decoded image exceeds the {max_pixels} pixel limit")
                opened.load()
                oriented = _apply_orientation(opened)
                normalized = _normalize_mode(oriented)
    except (UnsupportedImageFormatError, ImageTooLargeError):
        raise
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError("Decoded image exceeds Pillow's safety limit") from exc
    except Image.DecompressionBombWarning as exc:
        raise ImageTooLargeError("Decoded image exceeds Pillow's safety limit") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError) as exc:
        raise InvalidImageError("Uploaded data is not a valid, complete image") from exc

    logger.info(
        "Image decoded",
        extra={"image_format": detected_format, "image_dimensions": original_size},
    )
    return DecodedImage(normalized, detected_format, original_size)
