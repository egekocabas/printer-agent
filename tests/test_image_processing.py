import pytest
from PIL import Image

from printer_agent.image.processing import prepare_for_thermal_print, simulate_thermal_output


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


def test_preview_smoothing_blends_dots_without_changing_dimensions() -> None:
    source = Image.new("1", (9, 9), 1)
    source.putpixel((4, 4), 0)

    preview = simulate_thermal_output(source, smoothing_radius=0.65)

    assert preview.mode == "L"
    assert preview.size == source.size
    assert any(value not in {0, 255} for value in preview.get_flattened_data())


def test_zero_preview_smoothing_preserves_raw_dot_values() -> None:
    source = Image.new("1", (3, 1), 1)
    source.putpixel((1, 0), 0)

    preview = simulate_thermal_output(source, smoothing_radius=0)

    assert list(preview.get_flattened_data()) == [255, 0, 255]
