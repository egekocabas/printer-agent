# Configuration

## Installation

Create a virtual environment and install the project. Runtime, development, and build dependencies
are pinned in `pyproject.toml` so upgrades remain deliberate.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

The service loads `.env` from the current working directory. Process environment variables take
precedence, and a missing file is harmless. Start from the committed example:

```bash
cp .env.example .env
```

## Mock backend

The example configuration selects the in-memory mock backend, so no printer is needed:

```bash
uvicorn printer_agent.main:app --reload
```

You can also select it without a file:

```bash
PRINTER_BACKEND=mock uvicorn printer_agent.main:app --reload
```

## USB backend

Set the vendor and product IDs reported by your printer's USB descriptors:

```dotenv
PRINTER_BACKEND=usb
PRINTER_VENDOR_ID=0x1234
PRINTER_PRODUCT_ID=0x5678
PRINTER_IN_ENDPOINT=0x82
PRINTER_OUT_ENDPOINT=0x01
PRINTER_DOTS_WIDTH=384
PRINTER_MODEL_NAME=ANJET58
```

The IDs above are placeholders. Do not use them without checking the physical device. Decimal and
`0x` hexadecimal values are accepted. The USB backend retains a healthy connection, reconnects
after a communication failure, and retries the failed operation once.

Start the configured service with:

```bash
uvicorn printer_agent.main:app
```

Detailed paper and error status is reported as `null` when the printer cannot provide it reliably
through generic ESC/POS commands.

## Environment variables

| Variable | Application default | Meaning |
| --- | --- | --- |
| `PRINTER_BACKEND` | `mock` | `mock` or `usb` |
| `PRINTER_VENDOR_ID` | unset | Required USB vendor ID; decimal or hexadecimal |
| `PRINTER_PRODUCT_ID` | unset | Required USB product ID; decimal or hexadecimal |
| `PRINTER_IN_ENDPOINT` | `0x82` | USB bulk IN endpoint |
| `PRINTER_OUT_ENDPOINT` | `0x01` | USB bulk OUT endpoint |
| `PRINTER_PROFILE` | unset | Optional python-escpos printer profile |
| `PRINTER_DOTS_WIDTH` | `384` | Maximum output raster width |
| `PRINTER_MODEL_NAME` | `ANJET58` | Informational printer model |
| `PRINTER_IMAGE_BRIGHTNESS` | `1.25` | Brightness multiplier before dithering |
| `PRINTER_IMAGE_CONTRAST` | `1.05` | Contrast multiplier before dithering |
| `PRINTER_PREVIEW_SMOOTHING_RADIUS` | `0.65` | Preview-only thermal dot blending; `0` disables it |
| `PRINTER_IMAGE_CAPTION_GAP_LINES` | `1` | 24-dot lines between an image and its caption |
| `PRINTER_FINAL_FEED_LINES` | `3` | Blank lines after a complete print job |
| `PRINTER_IMAGE_FINAL_FEED_LINES` | unset | Image-job override for final feed lines |
| `MAX_IMAGE_UPLOAD_BYTES` | `26214400` | Maximum encoded bytes per image |
| `MAX_IMAGE_PIXELS` | `50000000` | Maximum decoded width multiplied by height |
| `MAX_TEXT_CHARACTERS` | `10000` | Text and label input limit |
| `MAX_QR_CHARACTERS` | `4096` | QR payload limit |
| `MAX_DOCUMENT_ITEMS` | `100` | Structured document item limit |

See [`.env.example`](../.env.example) for a copyable configuration with explanatory comments.

## Production notes

- Run a single Uvicorn worker. Print serialization and metrics are process-local.
- Restrict `/metrics` to the monitoring network.
- Put authentication, TLS, and network access controls in front of the service when it is reachable
  outside a trusted network.
- Keep `.env` out of version control; it is ignored by this repository.
