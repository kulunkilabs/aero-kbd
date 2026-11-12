from pathlib import Path

import pytest

from aero_keyboard.discovery import discover_interfaces, find_control_interface


def _fake_interface(
    root: Path,
    dev_root: Path,
    suffix: str,
    *,
    descriptor: bytes,
    interface_number: str,
) -> None:
    hid = root / f"0003:0414:8104.{suffix}"
    hid.mkdir()
    (hid / "report_descriptor").write_bytes(descriptor)
    (hid / "uevent").write_text(
        "HID_NAME=GIGABYTE USB-HID Keyboard\nHID_PHYS=usb-test/input3\n",
        encoding="utf-8",
    )
    (hid / "hidraw").mkdir()
    (hid / "hidraw" / f"hidraw{int(suffix)}").touch()
    # Tests use a non-symlink layout, so place the USB metadata at the resolved parent.
    (root / "bInterfaceNumber").write_text(interface_number, encoding="ascii")
    (dev_root / f"hidraw{int(suffix)}").touch()


def test_discover_interfaces_identifies_only_ff01_control_channel(tmp_path):
    sysfs_root = tmp_path / "sys"
    dev_root = tmp_path / "dev"
    sysfs_root.mkdir()
    dev_root.mkdir()
    _fake_interface(sysfs_root, dev_root, "1", descriptor=b"\x05\x01", interface_number="03")
    _fake_interface(
        sysfs_root,
        dev_root,
        "2",
        descriptor=b"\x06\x01\xff\x09\x01",
        interface_number="03",
    )

    interfaces = discover_interfaces(sysfs_root=sysfs_root, dev_root=dev_root)

    assert len(interfaces) == 2
    assert [item.is_control_interface for item in interfaces] == [False, True]
    assert interfaces[1].usage_page == 0xFF01
    assert interfaces[1].name == "GIGABYTE USB-HID Keyboard"


def test_find_control_interface_rejects_ambiguous_matches(tmp_path):
    sysfs_root = tmp_path / "sys"
    dev_root = tmp_path / "dev"
    sysfs_root.mkdir()
    dev_root.mkdir()
    for suffix in ("1", "2"):
        _fake_interface(
            sysfs_root,
            dev_root,
            suffix,
            descriptor=b"\x06\x01\xff",
            interface_number="03",
        )

    assert find_control_interface(sysfs_root=sysfs_root, dev_root=dev_root) is None


@pytest.mark.parametrize(
    "descriptor",
    [
        b"\x17\xaa\x06\x01\xff",
        b"\x06\x01\xff\x75",
        b"\xfe\x03\x00\x06\x01\xff",
    ],
)
def test_discovery_rejects_embedded_and_incomplete_usage_pages(tmp_path, descriptor):
    sysfs_root = tmp_path / "sys"
    dev_root = tmp_path / "dev"
    sysfs_root.mkdir()
    dev_root.mkdir()
    _fake_interface(sysfs_root, dev_root, "1", descriptor=descriptor, interface_number="03")
    interfaces = discover_interfaces(sysfs_root=sysfs_root, dev_root=dev_root)
    assert not interfaces[0].is_control_interface
    assert interfaces[0].usage_page is None
    assert find_control_interface(sysfs_root=sysfs_root, dev_root=dev_root) is None


def test_discovery_accepts_four_byte_control_usage_page(tmp_path):
    sysfs_root = tmp_path / "sys"
    dev_root = tmp_path / "dev"
    sysfs_root.mkdir()
    dev_root.mkdir()
    _fake_interface(
        sysfs_root,
        dev_root,
        "1",
        descriptor=b"\x07\x01\xff\x00\x00\x09\x01",
        interface_number="03",
    )
    assert find_control_interface(sysfs_root=sysfs_root, dev_root=dev_root).usage_page == 0xFF01
