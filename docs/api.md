# HTTP API

The interactive OpenAPI documentation is available at `/docs` while the service is running.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check application health independently of the printer |
| `GET` | `/metrics` | Read Prometheus print, latency, and queue metrics |
| `GET` | `/printer/status` | Check backend configuration and current reachability |
| `POST` | `/print/text` | Print styled text |
| `POST` | `/print/qr` | Print a QR code and optional label |
| `POST` | `/print/image` | Upload and print an image |
| `POST` | `/preview/image` | Prepare an image without printing it |
| `POST` | `/print/prepared-image` | Print the exact raster returned by preview |
| `POST` | `/print/feed` | Advance paper by an exact number of lines |
| `POST` | `/print` | Print one atomic structured document |

Successful print requests return:

```json
{"status":"printed"}
```

## Service and printer status

Application health remains healthy when a configured USB printer is absent:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/printer/status
```

`/printer/status` actively checks whether the backend is reachable. USB printers that implement
the standard ESC/POS `DLE EOT` replies also return one conservative normalized
`hardware_status`: `ready`, `paper_out`, `error`, or `unknown`. The value is `null` when the
connected printer does not provide a valid real-time response.

```json
{
  "configured": true,
  "reachable": true,
  "backend": "usb",
  "model": "ANJET58",
  "hardware_status": "ready",
  "detail": null
}
```

`unknown` means the printer reports an offline condition that is not portable enough to name. For
example, some models expose a dedicated cover-open bit while others report the same physical state
as paper-out. The API deliberately does not guess model-specific causes. A communication failure
invalidates the cached USB connection, retries once, and reports `reachable: false` if the printer
cannot be reopened.

`/metrics` is deliberately omitted from OpenAPI. It exposes bounded-label Prometheus metrics for
job outcomes, duration, queue wait, queue depth, active work, and the last successful print.

## Text

Supported alignments are `left`, `center`, and `right`. Supported sizes are `normal`,
`double_width`, `double_height`, and `double`.

```bash
curl -X POST http://127.0.0.1:8000/print/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello!","align":"center","bold":true,"size":"double"}'
```

## QR code

The QR size must be between 1 and 16.

```bash
curl -X POST http://127.0.0.1:8000/print/qr \
  -H 'Content-Type: application/json' \
  -d '{"data":"https://example.com","align":"center","label":"Scan me","size":8}'
```

## Images

`/print/image` accepts JPEG, MPO, PNG, WebP, HEIC/HEIF, and AVIF uploads as multipart form data. The
format is detected from the bytes rather than trusted headers or filenames.

```bash
curl -X POST http://127.0.0.1:8000/print/image \
  -F 'image=@photo.heic' \
  -F 'date=27/02/2026' \
  -F 'time=18:34'
```

`date` is optional and uses `DD/MM/YYYY`. `time` is optional, requires `date`, and uses 24-hour
`HH:MM`. The service validates that both values represent a real date or time.

The common image pipeline enforces encoded and decoded size limits, applies EXIF orientation,
converts embedded color information toward sRGB where possible, composites alpha onto white,
preserves aspect ratio, downsizes without upscaling, adjusts brightness and contrast, and produces
a monochrome Floyd-Steinberg dithered raster. MPO inputs use the primary image.

RAW, DNG, and Apple ProRAW formats are intentionally unsupported.

## Preview and approved printing

`/preview/image` accepts the same multipart fields as `/print/image` but does not print. By default
it returns an enhanced `image/png` preview:

```bash
curl -X POST http://127.0.0.1:8000/preview/image \
  -F 'image=@photo.heic' \
  --output printer-preview.png
```

Add `?response=json` to receive both images as Base64-encoded PNG strings:

```json
{
  "exact_print_image": "iVBORw0KGgo...",
  "enhanced_preview_image": "iVBORw0KGgo..."
}
```

Decode `exact_print_image` and upload it to `/print/prepared-image` to print the approved raster
without preparing it a second time:

```bash
curl -X POST http://127.0.0.1:8000/print/prepared-image \
  -F 'image=@exact-print.png'
```

Prepared images must be single-frame, 1-bit monochrome PNGs within the configured printer width.

## Paper feed

This endpoint feeds exactly 1–255 lines and does not add automatic tear-off spacing:

```bash
curl -X POST http://127.0.0.1:8000/print/feed \
  -H 'Content-Type: application/json' \
  -d '{"lines":5}'
```

## Atomic documents

`/print` serializes all items in one document as a single job, preventing interleaving with another
request. Documents without images use JSON:

```bash
curl -X POST http://127.0.0.1:8000/print \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"type":"text","text":"Hello"},{"type":"qr","data":"https://example.com"},{"type":"feed","lines":3}]}'
```

Documents with images use multipart form data. Each image item's `file` must match an uploaded
part's filename:

```bash
curl -X POST http://127.0.0.1:8000/print \
  -F 'document={"items":[{"type":"text","text":"Photo"},{"type":"image","file":"photo1"}]}' \
  -F 'images=@photo.jpg;filename=photo1'
```

Duplicate, missing, and unreferenced filenames are rejected. Clients cannot submit raw ESC/POS,
filesystem paths, Base64 image bodies, or remote image URLs.
