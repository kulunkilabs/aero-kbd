# Project plan

## Initial scope

- Hardware: GIGABYTE AERO X16 1WH
- USB ID: `0414:8104`
- Controller: ITE-829X
- Control channel: HID vendor usage page `0xFF01`
- Platforms: Fedora, Omarchy, and CachyOS

The first release prioritizes reliable static color, brightness, power toggle,
and login restoration. Animated effects remain experimental until verified on
the 1WH.

## Architecture

The CLI and desktop UI share one Python hardware library. The library discovers
the correct `hidraw` node through sysfs, validates the HID report descriptor,
and sends only known 9-byte feature reports. Device-specific capabilities live
in data profiles rather than UI code.

No kernel module is required. A udev rule grants the active local user access to
the matching device. Login restoration is a short-lived systemd user service,
not a daemon.

## Milestones

1. Detect `0414:8104` and identify its `0xFF01` interface without writing data.
2. Implement and test report construction, checksum, validation, and mocked I/O.
3. Validate static white at limited brightness on the AERO X16 1WH.
4. Ship a CLI for detection, status, static color, brightness, on/off, and saved
   profiles.
5. Validate each firmware effect individually and record the support matrix.
6. Add a Qt 6 desktop settings window; tray integration remains optional.
7. Add secure udev access and XDG-compliant state/configuration storage.
8. Add login restoration through a systemd user unit.
9. Package as an Arch `PKGBUILD` and Fedora RPM.
10. Test Fedora GNOME/KDE, Omarchy/Hyprland, and CachyOS/KDE before beta.

## Safety rules

- Reject unknown product IDs, usage pages, commands, effects, and value ranges.
- Do not expose raw report transmission in the normal CLI or GUI.
- Do not issue controller-reset or firmware commands automatically.
- Keep the kernel HID driver attached so normal typing continues to work.
- Save the last confirmed working state before applying a change.
- Hardware tests must be explicit and separate from the default test suite.

## Packaging matrix

| Platform | CLI | GUI | Tray | Restore | Package |
| --- | --- | --- | --- | --- | --- |
| Fedora GNOME | Required | Required | Optional | Required | RPM |
| Fedora KDE | Required | Required | Required | Required | RPM |
| Omarchy/Hyprland | Required | Required | Waybar test | Required | PKGBUILD |
| CachyOS/KDE | Required | Required | Required | Required | PKGBUILD |

## Later expansion

Additional laptops will be added through reviewed device profiles and hardware
validation. OpenRGB integration can be considered once the controller backend
is stable.
