from typing import Any

import pytest
from usb.core import USBTimeoutError  # type: ignore[import-untyped]

from printer_agent.config import Settings
from printer_agent.exceptions import PrinterUnavailableError
from printer_agent.printer.base import HardwareStatus
from printer_agent.printer.escpos import EscPosPrinter

READY_STATUS = [0x16, 0x12, 0x12, 0x12]


class FakeStatusUsb:
    def __init__(self, responses: list[int]) -> None:
        self.responses = iter(responses)
        self.commands: list[bytes] = []
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def _raw(self, command: bytes) -> None:
        self.commands.append(command)

    def _read(self) -> bytes:
        return bytes((next(self.responses),))


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

        def _raw(self, command: bytes) -> None:
            captured.setdefault("status_commands", []).append(command)

        def _read(self) -> bytes:
            return bytes((READY_STATUS[len(captured["status_commands"]) - 1],))

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
    assert status.hardware_status is HardwareStatus.READY
    assert captured == {
        "vendor_id": 0x0456,
        "product_id": 0x0808,
        "in_ep": 0x81,
        "out_ep": 0x03,
        "opened": True,
        "status_commands": [
            b"\x10\x04\x01",
            b"\x10\x04\x02",
            b"\x10\x04\x03",
            b"\x10\x04\x04",
        ],
        "feed_lines": 20,
    }


@pytest.mark.parametrize(
    ("responses", "expected"),
    [
        (READY_STATUS, HardwareStatus.READY),
        ([0x1E, 0x32, 0x12, 0x72], HardwareStatus.PAPER_OUT),
        ([0x1E, 0x52, 0x52, 0x12], HardwareStatus.ERROR),
        ([0x1E, 0x16, 0x12, 0x12], HardwareStatus.UNKNOWN),
    ],
)
def test_usb_backend_normalizes_generic_realtime_status(
    monkeypatch: Any, responses: list[int], expected: HardwareStatus
) -> None:
    device = FakeStatusUsb(responses)
    monkeypatch.setattr("escpos.printer.Usb", lambda *_args, **_kwargs: device)

    status = EscPosPrinter(
        Settings(
            _env_file=None,
            printer_backend="usb",
            printer_vendor_id=0x0456,
            printer_product_id=0x0808,
        )
    ).get_status()

    assert status.reachable is True
    assert status.hardware_status is expected
    assert status.detail is None
    assert device.commands == [
        b"\x10\x04\x01",
        b"\x10\x04\x02",
        b"\x10\x04\x03",
        b"\x10\x04\x04",
    ]


@pytest.mark.parametrize("failure", [b"", b"\x00", USBTimeoutError("timed out")])
def test_usb_backend_keeps_reachability_when_realtime_status_is_unsupported(
    monkeypatch: Any, failure: bytes | USBTimeoutError
) -> None:
    class UnsupportedStatusUsb(FakeStatusUsb):
        def _read(self) -> bytes:
            if isinstance(failure, USBTimeoutError):
                raise failure
            return failure

    device = UnsupportedStatusUsb(READY_STATUS)
    monkeypatch.setattr("escpos.printer.Usb", lambda *_args, **_kwargs: device)

    status = EscPosPrinter(
        Settings(
            _env_file=None,
            printer_backend="usb",
            printer_vendor_id=0x0456,
            printer_product_id=0x0808,
        )
    ).get_status()

    assert status.reachable is True
    assert status.hardware_status is None
    assert status.detail == "Connected; real-time ESC/POS status is unavailable"
    assert device.closed is False


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


def test_status_check_discards_stale_handle_and_reports_powered_off(
    monkeypatch: Any,
) -> None:
    available = True
    devices: list[Any] = []

    class FakeUsb(FakeStatusUsb):
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            super().__init__(READY_STATUS)
            self.connected = True
            devices.append(self)

        def open(self) -> None:
            if not available:
                raise OSError("printer is off")
            super().open()

        def _raw(self, command: bytes) -> None:
            if not self.connected:
                raise OSError("stale USB handle")
            super()._raw(command)

    monkeypatch.setattr("escpos.printer.Usb", FakeUsb)
    printer = EscPosPrinter(
        Settings(
            _env_file=None,
            printer_backend="usb",
            printer_vendor_id=0x0456,
            printer_product_id=0x0808,
        )
    )

    assert printer.get_status().hardware_status is HardwareStatus.READY
    devices[0].connected = False
    available = False
    status = printer.get_status()

    assert status.reachable is False
    assert status.hardware_status is None
    assert status.detail == "Configured USB printer is unavailable"
    assert devices[0].closed is True
    assert len(devices) == 2
