# printer-agent

`printer-agent` is a small HTTP service that provides a generic interface to ESC/POS thermal
printers. Applications submit text, QR codes, structured documents, or original mobile-phone
images. They do not need to know about USB, ESC/POS commands, printer dot widths, HEIC decoding,
thermal-image conversion, or dithering.

The default backend is an in-memory mock, so development and tests require no printer. The first
physical target is an ANJET58 58 mm USB printer, but the public API and image pipeline are not tied
to that model.

## Architecture

```text
Application
    |
    | HTTP
    v
printer-agent
    |
    | Printer abstraction
    v
ESC/POS backend
    |
    | USB
    v
Thermal printer
```

For development, the same service uses:

```text
Application
    |
    v
printer-agent
    |
    v
MockPrinter (recorded operations in memory)
```

Every complete print request holds one local serialization lock. Blocking image and printer work
runs in worker threads rather than on the HTTP event loop. A complete structured document cannot
interleave with another job.

## Requirements and installation

Python 3.12 or newer is required. Create a virtual environment and install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Runtime, development, and build-tool versions are pinned exactly in `pyproject.toml`, so installs
do not resolve to newer dependency releases on a later date. Dependency upgrades should be made
deliberately by changing those pins and running the complete verification suite.

The application automatically loads a `.env` file from the current working directory. A missing
file is harmless, and real process environment variables take precedence over values in `.env`.
Start by copying the committed example:

```bash
cp .env.example .env
```

For USB operation, edit `.env` with the IDs reported by your device:

```dotenv
PRINTER_BACKEND=usb
PRINTER_VENDOR_ID=0x1234
PRINTER_PRODUCT_ID=0x5678
PRINTER_IN_ENDPOINT=0x82
PRINTER_OUT_ENDPOINT=0x01
PRINTER_DOTS_WIDTH=384
PRINTER_MODEL_NAME=ANJET58
PRINTER_IMAGE_BRIGHTNESS=1.25
PRINTER_IMAGE_CONTRAST=1.05
PRINTER_FINAL_FEED_LINES=3
PRINTER_IMAGE_FINAL_FEED_LINES=
```

The example IDs are placeholders and must be replaced. Because `.env` is gitignored, local USB
configuration will not be committed accidentally. Once configured, starting the service requires
only:

```bash
uvicorn printer_agent.main:app --reload
```

Start a hardware-free development instance:

```bash
PRINTER_BACKEND=mock uvicorn printer_agent.main:app --reload
```

The interactive OpenAPI UI is at <http://127.0.0.1:8000/docs>.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Application health; remains healthy if the printer is absent |
| `GET` | `/printer/status` | Backend configuration, current reachability, and known status |
| `POST` | `/print/text` | Print styled plain text |
| `POST` | `/print/qr` | Print a QR code and optional label |
| `POST` | `/print/image` | Upload and print one image as `multipart/form-data` |
| `POST` | `/preview/image` | Return a screen-friendly simulation of the transformed print raster |
| `POST` | `/print/feed` | Advance the paper by an exact number of blank lines |
| `POST` | `/print` | Print one atomic structured document |

### `GET /health`

Check whether the HTTP application is running. Printer availability does not affect this result.

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "status": "ok"
}
```

### `GET /printer/status`

Check configuration and whether the configured printer connection can currently be opened.

```bash
curl http://127.0.0.1:8000/printer/status
```

```json
{
  "configured": true,
  "reachable": true,
  "backend": "usb",
  "model": "ANJET58",
  "hardware_status": null,
  "detail": "Connection opened; detailed hardware status is not queried reliably"
}
```

`hardware_status` is `null` when the printer cannot provide a reliable generic ESC/POS status.

### `POST /print/text`

Print styled text. Supported alignment values are `left`, `center`, and `right`. Supported sizes
are `normal`, `double_width`, `double_height`, and `double`.

```bash
curl -X POST http://127.0.0.1:8000/print/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from printer-agent!","align":"center","bold":true,"size":"double"}'
```

```json
{
  "status": "printed"
}
```

### `POST /print/qr`

Print a QR code with an optional text label.

```bash
curl -X POST http://127.0.0.1:8000/print/qr \
  -H 'Content-Type: application/json' \
  -d '{"data":"https://example.com","align":"center","label":"Scan me","size":8}'
```

```json
{
  "status": "printed"
}
```

### `POST /print/image`

Upload the original image using multipart form data. The service detects the format from its
contents rather than trusting its filename or MIME header. Optional `date` and `time` fields print
a centered caption below the image.

```bash
curl -X POST http://127.0.0.1:8000/print/image \
  -F 'image=@IMG_1234.HEIC'
```

Print an image with a date:

```bash
curl -X POST http://127.0.0.1:8000/print/image \
  -F 'image=@IMG_1234.HEIC' \
  -F 'date=27/02/2026'
```

Print an image with a date and 24-hour time:

```bash
curl -X POST http://127.0.0.1:8000/print/image \
  -F 'image=@IMG_1234.HEIC' \
  -F 'date=27/02/2026' \
  -F 'time=18:34'
```

`date` must be a real date in `DD/MM/YYYY` format. `time` is optional, requires `date`, and must be
a real time in 24-hour `HH:MM` format. The image and caption are separated by
`PRINTER_IMAGE_CAPTION_GAP_LINES` blank lines.

```json
{
  "status": "printed"
}
```

### `POST /preview/image`

Preview an image without sending anything to the printer. It accepts the same `image`, `date`, and
`time` multipart fields as `/print/image`. The service first produces the exact monochrome print
raster, including the optional caption and configured gap, and then applies preview-only smoothing
to simulate how neighboring thermal dots visually blend on paper. This smoothing never changes the
data sent to the printer. Final tear-off feed lines are not shown because they only move paper.

```bash
curl -X POST http://127.0.0.1:8000/preview/image \
  -F 'image=@IMG_1234.HEIC' \
  -F 'date=27/02/2026' \
  -F 'time=18:34' \
  --output printer-preview.png
```

Set `PRINTER_PREVIEW_SMOOTHING_RADIUS=0` to return the unsmoothed raw dot raster. Increase it slightly
if the preview still looks more dotted than the paper output; values around `0.5`–`1.0` are the
intended range.

### `POST /print/feed`

Advance the paper without printing content. This endpoint feeds exactly the requested number of
lines and does not add automatic final tear-off spacing.

```bash
curl -X POST http://127.0.0.1:8000/print/feed \
  -H 'Content-Type: application/json' \
  -d '{"lines":5}'
```

```json
{
  "status": "printed"
}
```

`lines` must be between 1 and 255.

### `POST /print`

Print a sequence of elements atomically. A document without images can use ordinary JSON:

```bash
curl -X POST http://127.0.0.1:8000/print \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"type":"text","text":"Hello"},{"type":"qr","data":"https://example.com"},{"type":"feed","lines":3}]}'
```

```json
{
  "status": "printed"
}
```

For a document containing images, send multipart form data. The `document` part is JSON, each
binary part uses the repeatable field name `images`, and an image item's `file` value matches that
part's uploaded filename. Duplicate, missing, and unreferenced filenames are rejected.

```bash
curl -X POST http://127.0.0.1:8000/print \
  -F 'document={"items":[{"type":"text","text":"Photo"},{"type":"image","file":"photo1"},{"type":"feed","lines":3}]}' \
  -F 'images=@photo.jpg;filename=photo1'
```

```json
{
  "status": "printed"
}
```

Every successful print request automatically feeds the configured number of final blank lines for
safe tear-off. Image requests and structured documents containing images can use a larger
image-specific override. Feeding uses the explicit ESC/POS print-and-feed command so it also works
after raster images. An explicit `feed` document item adds spacing within the document itself.

Clients cannot submit raw ESC/POS, filesystem paths, base64 image bodies, or remote image URLs.

## Supported images

The service directly decodes and inspects:

- JPEG/JPG
- MPO multi-picture JPEG (primary image; auxiliary frames are ignored)
- PNG
- WebP
- HEIC/HEIF
- AVIF

This covers common current iPhone and Android output without client-side conversion. MPO files are
handled as JPEG-family images: the primary still is printed while auxiliary depth, HDR, or alternate
frames are ignored. RAW camera formats, DNG, and Apple ProRAW are intentionally out of scope.

The common pipeline validates encoded and decoded size, detects the actual format, applies EXIF
orientation, converts embedded color information toward sRGB where possible, composites alpha on
white, preserves aspect ratio, downsizes without upscaling, converts to grayscale, improves
contrast, and applies Floyd-Steinberg monochrome dithering. It never crops by default.

## Configuration

Configuration is read centrally from environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PRINTER_BACKEND` | `mock` | `mock` or `usb` |
| `PRINTER_VENDOR_ID` | unset | Required USB vendor ID; decimal or `0x` hexadecimal |
| `PRINTER_PRODUCT_ID` | unset | Required USB product ID; decimal or `0x` hexadecimal |
| `PRINTER_IN_ENDPOINT` | `0x82` | USB bulk IN endpoint; decimal or hexadecimal |
| `PRINTER_OUT_ENDPOINT` | `0x01` | USB bulk OUT endpoint; decimal or hexadecimal |
| `PRINTER_PROFILE` | unset | Optional python-escpos printer profile |
| `PRINTER_DOTS_WIDTH` | `384` | Maximum output raster width |
| `PRINTER_MODEL_NAME` | `ANJET58` | Informational model name |
| `PRINTER_IMAGE_BRIGHTNESS` | `1.25` | Brightness multiplier; increase for lighter image prints |
| `PRINTER_IMAGE_CONTRAST` | `1.05` | Contrast multiplier applied before dithering |
| `PRINTER_PREVIEW_SMOOTHING_RADIUS` | `0.65` | Preview-only thermal dot blending; `0` shows raw printer dots |
| `PRINTER_IMAGE_CAPTION_GAP_LINES` | `1` | 24-dot blank lines between an image and its optional date/time caption; `0` disables the gap |
| `PRINTER_FINAL_FEED_LINES` | `3` | Blank lines added after every complete print job; `0` disables it |
| `PRINTER_IMAGE_FINAL_FEED_LINES` | unset | Final lines for image jobs; falls back to `PRINTER_FINAL_FEED_LINES` |
| `MAX_IMAGE_UPLOAD_BYTES` | `26214400` | Per-image encoded upload limit (25 MiB) |
| `MAX_IMAGE_PIXELS` | `50000000` | Maximum decoded width × height |
| `MAX_TEXT_CHARACTERS` | `10000` | Text/label input limit |
| `MAX_QR_CHARACTERS` | `4096` | QR payload limit |
| `MAX_DOCUMENT_ITEMS` | `100` | Structured document item limit |

To use a USB printer:

```bash
PRINTER_BACKEND=usb \
PRINTER_VENDOR_ID=0x0000 \
PRINTER_PRODUCT_ID=0x0000 \
PRINTER_MODEL_NAME=ANJET58 \
uvicorn printer_agent.main:app
```

Replace the placeholder IDs with values measured from the actual device. No ANJET58 vendor or
product ID is fabricated here. The USB backend keeps a successful connection open, drops it after
a communication error, and attempts a clean reconnect on the next operation. Detailed printer
paper/error status is returned as `null` because generic ESC/POS status queries are not reliably
supported across devices.

## Testing and quality checks

The suite uses only `MockPrinter`; no USB hardware is required.

```bash
pytest
ruff format --check .
ruff check .
mypy
```

GitHub Actions runs formatting, linting, and strict type checking on Python 3.12, plus the complete
test suite on Python 3.12, 3.13, and 3.14. The workflow does not build or publish packages or
container images.

Tests generate small deterministic JPEG, MPO, PNG, WebP, HEIF, and AVIF fixtures at runtime,
including an actual multipart HEIF API upload. They also cover EXIF orientation, transparency,
malformed and oversized images, aspect-ratio preservation, all endpoints, error translation, and
atomic concurrent documents.
