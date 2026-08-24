# printer-agent

`printer-agent` is a small HTTP service for ESC/POS thermal printers. It accepts text, QR codes,
structured documents, and common phone image formats without requiring clients to handle USB,
ESC/POS commands, image conversion, or dithering.

The default in-memory backend makes local development and testing hardware-free. The first physical
target is an ANJET58 58 mm USB printer, but the API and image pipeline are not tied to that model.

## Features

- FastAPI endpoints for text, QR, image, feed, and atomic document jobs
- JPEG, MPO, PNG, WebP, HEIC/HEIF, and AVIF image processing
- Exact print-image previews before a job reaches the printer
- USB and in-memory mock backends
- Prometheus metrics and printer reachability checks

## Quick start

Python 3.12 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
uvicorn printer_agent.main:app --reload
```

The example configuration uses the mock backend. Open <http://127.0.0.1:8000/docs> for the
interactive API, or check service health with:

```bash
curl http://127.0.0.1:8000/health
```

## Documentation

- [Configuration and USB setup](docs/configuration.md)
- [HTTP API](docs/api.md)
- [Architecture and operational notes](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

Licensed under the [MIT License](LICENSE).
