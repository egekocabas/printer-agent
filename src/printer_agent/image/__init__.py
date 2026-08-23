"""Image decoding and thermal preparation."""

from printer_agent.image.decoder import DecodedImage, decode_image, register_image_openers
from printer_agent.image.processing import (
    add_caption,
    prepare_for_thermal_print,
    simulate_thermal_output,
)

__all__ = [
    "DecodedImage",
    "add_caption",
    "decode_image",
    "prepare_for_thermal_print",
    "register_image_openers",
    "simulate_thermal_output",
]
