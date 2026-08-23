import io

from PIL import Image


def image_bytes(
    image_format: str = "PNG",
    *,
    size: tuple[int, int] = (40, 20),
    mode: str = "RGB",
    color: object = "gray",
    exif: Image.Exif | None = None,
) -> bytes:
    image = Image.new(mode, size, color)
    output = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(output, format=image_format, **kwargs)
    return output.getvalue()


def mpo_image_bytes(*, size: tuple[int, int] = (40, 20)) -> bytes:
    """Create a deterministic multi-picture JPEG with a distinct primary frame."""

    primary = Image.new("RGB", size, "red")
    auxiliary = Image.new("RGB", size, "blue")
    output = io.BytesIO()
    primary.save(output, format="MPO", save_all=True, append_images=[auxiliary])
    return output.getvalue()
