# Architecture

```text
HTTP client
    |
    v
FastAPI transport
    |
    v
PrintingService (validation, preparation, serialization)
    |
    v
Printer interface
    |-- MockPrinter (development and tests)
    `-- EscposPrinter (USB hardware)
```

The API layer handles transport and typed request validation. `PrintingService` owns job-level
behavior and delegates device operations through the printer interface, keeping hardware concerns
out of routes and tests.

## Concurrency

Every complete print request holds one local asynchronous serialization lock. Printer status
queries hold the same lock because their request and response bytes must not interleave with a print
job. A structured document therefore cannot interleave with another job or status query. Blocking
image and USB work runs in worker threads instead of the HTTP event loop.

The lock is process-local, so the service must run with one Uvicorn worker per physical printer.
Horizontal scaling requires an external queue or lock and explicit printer ownership.

## Image preparation

Encoded input passes through format and size validation, orientation and color normalization,
alpha compositing, aspect-preserving resize, grayscale adjustment, and monochrome dithering. The
prepared raster never exceeds the configured dot width and is not upscaled.

Preview requests produce two representations:

- the exact 1-bit raster accepted by the prepared-image endpoint;
- a screen-friendly preview with optional blur to approximate thermal dot spread.

Preview smoothing does not alter the raster sent to hardware.

## Failure handling

The USB backend keeps an established connection open. Print operations and status queries both
close a stale connection, reconnect, and retry once after a communication error. A status read uses
the standard ESC/POS real-time query and validates the fixed response bits before interpreting
portable paper and error signals. Unsupported status queries leave the connection reachable and
report no hardware status. API exceptions distinguish unavailable hardware, communication failure,
invalid images, oversized uploads, and invalid documents.

Application health is intentionally independent from printer health. Operators should use
`/health` for service liveness, `/printer/status` for reachability, and `/metrics` for bounded-label
Prometheus telemetry.
