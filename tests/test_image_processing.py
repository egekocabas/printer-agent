import pytest
from PIL import Image

from printer_agent.image.processing import prepare_for_thermal_print


@pytest.mark.parametrize(
    ("input_size", "expected_size"),
    [
        ((800, 400), (384, 192)),
        ((400, 800), (384, 768)),
        ((800, 800), (384, 384)),
        ((40, 20), (40, 20)),
    ],
)
def test_aspect_ratio_width_and_no_upscaling(
    input_size: tuple[int, int], expected_size: tuple[int, int]
) -> None:
    prepared = prepare_for_thermal_print(Image.new("RGB", input_size), printable_width=384)
    assert prepared.size == expected_size
    assert prepared.mode == "1"


def test_custom_printer_width_is_respected_without_cropping() -> None:
    prepared = prepare_for_thermal_print(Image.new("RGB", (1000, 333)), printable_width=576)
    assert prepared.size == (576, 192)


def test_higher_brightness_reduces_black_dot_density() -> None:
    source = Image.new("L", (128, 128), 96)
    baseline = prepare_for_thermal_print(
        source,
        printable_width=384,
        brightness=1.0,
        contrast=1.0,
    )
    lightened = prepare_for_thermal_print(
        source,
        printable_width=384,
        brightness=1.5,
        contrast=1.0,
    )

    assert lightened.histogram()[0] < baseline.histogram()[0]
