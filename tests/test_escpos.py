from typing import Any

import pytest

from printer_agent.config import Settings
from printer_agent.exceptions import PrinterUnavailableError
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


def test_usb_backend_connects_after_printer_becomes_available(monkeypatch: Any) -> None:
    available = False
    printed: list[int] = []

    class FakeUsb:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def open(self) -> None:
            if not available:
                raise OSError("printer is off")

        def close(self) -> None:
            pass

        def print_and_feed(self, lines: int) -> None:
            printed.append(lines)

    monkeypatch.setattr("escpos.printer.Usb", FakeUsb)
    printer = EscPosPrinter(
        Settings(
            _env_file=None,
            printer_backend="usb",
            printer_vendor_id=0x0456,
            printer_product_id=0x0808,
        )
    )

    with pytest.raises(PrinterUnavailableError):
        printer.feed(1)

    available = True
    printer.feed(2)

    assert printed == [2]


def test_usb_backend_reconnects_after_printer_power_cycle(monkeypatch: Any) -> None:
    devices: list[Any] = []

    class FakeUsb:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.connected = True
            self.closed = False
            self.feed_lines: list[int] = []
            devices.append(self)

        def open(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

        def print_and_feed(self, lines: int) -> None:
            if not self.connected:
                raise OSError("stale USB handle")
            self.feed_lines.append(lines)

    monkeypatch.setattr("escpos.printer.Usb", FakeUsb)
    printer = EscPosPrinter(
        Settings(
            _env_file=None,
            printer_backend="usb",
            printer_vendor_id=0x0456,
            printer_product_id=0x0808,
        )
    )

    printer.feed(1)
    devices[0].connected = False
    printer.feed(2)

    assert len(devices) == 2
    assert devices[0].closed is True
    assert devices[0].feed_lines == [1]
    assert devices[1].feed_lines == [2]
