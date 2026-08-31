"""Read-only discovery of supported GIGABYTE HID interfaces through sysfs."""

from __future__ import annotations

import glob
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_VENDOR_ID = 0x0414
DEFAULT_PRODUCT_ID = 0x8104
CONTROL_USAGE_PAGE = 0xFF01
_CONTROL_USAGE_PAGE_DESCRIPTOR = b"\x06\x01\xff"


@dataclass(frozen=True, slots=True)
class HidInterface:
    """One HID interface belonging to a matching physical keyboard."""

    device_path: str
    sysfs_path: str
    vendor_id: int
    product_id: int
    interface_number: int | None
    name: str | None
    physical_path: str | None
    usage_page: int | None
    is_control_interface: bool
    device_node_present: bool
    readable: bool
    writable: bool

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible representation."""
        result = asdict(self)
        result["vendor_id"] = f"{self.vendor_id:04x}"
        result["product_id"] = f"{self.product_id:04x}"
        if self.usage_page is not None:
            result["usage_page"] = f"0x{self.usage_page:04x}"
        return result


def _read_properties(path: Path) -> dict[str, str]:
    properties: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return properties

    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    return properties


def _interface_number(hid_path: Path) -> int | None:
    """Read the USB interface number from the resolved HID parent."""
    try:
        interface_path = hid_path.resolve().parent / "bInterfaceNumber"
        return int(interface_path.read_text(encoding="ascii").strip(), 16)
    except (OSError, ValueError):
        return None


def _device_node(hid_path: Path, dev_root: Path) -> Path:
    try:
        names = sorted(entry.name for entry in (hid_path / "hidraw").iterdir())
    except OSError:
        names = []
    return dev_root / names[0] if names else dev_root / "unavailable"


def discover_interfaces(
    vendor_id: int = DEFAULT_VENDOR_ID,
    product_id: int = DEFAULT_PRODUCT_ID,
    *,
    sysfs_root: Path | str = "/sys/bus/hid/devices",
    dev_root: Path | str = "/dev",
) -> list[HidInterface]:
    """Find matching interfaces without opening or writing to a device node."""
    sysfs_root = Path(sysfs_root)
    dev_root = Path(dev_root)
    pattern = str(sysfs_root / f"0003:{vendor_id:04X}:{product_id:04X}.*")
    interfaces: list[HidInterface] = []

    for raw_path in sorted(glob.glob(pattern)):
        hid_path = Path(raw_path)
        try:
            descriptor = (hid_path / "report_descriptor").read_bytes()
        except OSError:
            continue

        properties = _read_properties(hid_path / "uevent")
        is_control = _CONTROL_USAGE_PAGE_DESCRIPTOR in descriptor
        node = _device_node(hid_path, dev_root)
        present = node.exists()
        interfaces.append(
            HidInterface(
                device_path=str(node),
                sysfs_path=str(hid_path),
                vendor_id=vendor_id,
                product_id=product_id,
                interface_number=_interface_number(hid_path),
                name=properties.get("HID_NAME"),
                physical_path=properties.get("HID_PHYS"),
                usage_page=CONTROL_USAGE_PAGE if is_control else None,
                is_control_interface=is_control,
                device_node_present=present,
                readable=present and os.access(node, os.R_OK),
                writable=present and os.access(node, os.W_OK),
            )
        )

    return interfaces


def find_control_interface(**kwargs: object) -> HidInterface | None:
    """Return the unique supported vendor-control interface, when present."""
    matches = [item for item in discover_interfaces(**kwargs) if item.is_control_interface]
    return matches[0] if len(matches) == 1 else None
