import io

import pytest
from PIL import Image

from printer_agent.exceptions import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)
from printer_agent.image.decoder import decode_image, register_image_openers
from tests.image_helpers import image_bytes, mpo_image_bytes


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP", "HEIF", "AVIF"])
def test_supported_formats_decode_by_content(image_format: str) -> None:
    register_image_openers()
    decoded = decode_image(image_bytes(image_format), max_pixels=1_000_000)
    assert decoded.format == image_format
    assert decoded.image.size == (40, 20)
    assert decoded.image.mode in {"RGB", "L"}


def test_mpo_decodes_only_the_primary_jpeg_image() -> None:
    decoded = decode_image(mpo_image_bytes(), max_pixels=1_000_000)

    assert decoded.format == "MPO"
    assert decoded.image.size == (40, 20)
    assert decoded.image.getpixel((0, 0)) == (254, 0, 0)


@pytest.mark.parametrize(
    ("mode", "color"),
    [("RGB", "red"), ("L", 127), ("P", 2), ("RGBA", (0, 0, 0, 0))],
)
def test_common_modes_are_normalized(mode: str, color: object) -> None:
    decoded = decode_image(
        image_bytes("PNG", mode=mode, color=color),
        max_pixels=1_000_000,
    )
    assert decoded.image.mode in {"RGB", "L"}


def test_transparency_is_composited_onto_white() -> None:
    decoded = decode_image(
        image_bytes("PNG", mode="RGBA", color=(0, 0, 0, 0)),
        max_pixels=1_000_000,
    )
    assert decoded.image.getpixel((0, 0)) == (255, 255, 255)


def test_exif_orientation_is_applied() -> None:
    exif = Image.Exif()
    exif[274] = 6
    decoded = decode_image(
        image_bytes("JPEG", size=(40, 20), exif=exif),
        max_pixels=1_000_000,
    )
    assert decoded.original_size == (40, 20)
    assert decoded.image.size == (20, 40)


def test_heif_preserved_exif_orientation_is_applied() -> None:
    register_image_openers()
    exif = Image.Exif()
    exif[274] = 6
    decoded = decode_image(
        image_bytes("HEIF", size=(40, 20), exif=exif),
        max_pixels=1_000_000,
    )
    assert decoded.original_size == (40, 20)
    assert decoded.image.size == (20, 40)


def test_malformed_and_truncated_images_are_rejected() -> None:
    with pytest.raises(InvalidImageError):
        decode_image(b"not an image", max_pixels=1_000_000)
    valid = image_bytes("PNG")
    with pytest.raises(InvalidImageError):
        decode_image(valid[: len(valid) // 2], max_pixels=1_000_000)


def test_decodable_but_unsupported_format_is_rejected() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        decode_image(image_bytes("GIF"), max_pixels=1_000_000)


def test_decoded_pixel_limit_is_enforced() -> None:
    large = Image.new("L", (1100, 1000), 255)
    output = io.BytesIO()
    large.save(output, format="PNG")
    with pytest.raises(ImageTooLargeError):
        decode_image(output.getvalue(), max_pixels=1_000_000)
