# Aero Keyboard Control

Cross-distribution Linux control for the RGB keyboard in GIGABYTE Aero laptops.

The initial hardware target is the GIGABYTE AERO X16 1WH with the ITE-829X
keyboard controller (`0414:8104`). The first supported distributions will be
Fedora and Arch-based systems, including Omarchy and CachyOS.

## Status

This repository is in the planning and hardware-validation stage. Do not send
arbitrary HID reports to the keyboard. The MVP will expose only validated,
allow-listed commands.

## Design goals

- A dependency-light hardware library using Linux `hidraw`
- A scriptable CLI that works without a desktop environment
- A Wayland-compatible Qt desktop application with optional tray support
- No kernel module and no permanently running privileged daemon
- Secure device access through `udev` and `TAG+="uaccess"`
- Native RPM and Arch packaging
- Mocked protocol tests that do not require real hardware

See [the project plan](docs/PROJECT_PLAN.md) for milestones and architecture.

## Prior work

The protocol implementation will build on and attribute the MIT-licensed
reverse-engineering work in
[misaelzapata/aeroctl-linux-indicator](https://github.com/misaelzapata/aeroctl-linux-indicator).

## License

MIT
