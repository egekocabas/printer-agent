from typing import Any

from printer_agent.config import Settings
from printer_agent.printer.escpos import EscPosPrinter


def test_usb_backend_passes_configured_endpoints(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    class FakeUsb:
        def __init__(self, vendor_id: int, product_id: int, **kwargs: Any) -> None:
            captured.update(
                vendor_id=vendor_id,
                product_id=product_id,
                **kwargs,
            )

        def open(self) -> None:
            captured["opened"] = True

        def close(self) -> None:
            pass

        def print_and_feed(self, lines: int) -> None:
            captured["feed_lines"] = lines

    monkeypatch.setattr("escpos.printer.Usb", FakeUsb)
    settings = Settings(
        _env_file=None,
        printer_backend="usb",
        printer_vendor_id=0x0456,
        printer_product_id=0x0808,
        printer_in_endpoint=0x81,
        printer_out_endpoint=0x03,
    )

    printer = EscPosPrinter(settings)
    status = printer.get_status()
    printer.feed(20)

    assert status.reachable is True
    assert captured == {
        "vendor_id": 0x0456,
        "product_id": 0x0808,
        "in_ep": 0x81,
        "out_ep": 0x03,
        "opened": True,
        "feed_lines": 20,
    }
