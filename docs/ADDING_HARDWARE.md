# Adding support for another laptop

Only the GIGABYTE AERO X16 1WH (`0414:8104`, ITE-829X controller) is validated
today. This page describes how another model gets added, and what must never be
skipped: a wrong HID report can leave a keyboard controller in a bad state, so
nothing is sent to hardware that has not been captured from the vendor's own
software first.

## 1. Identify the controller

On the laptop in question:

```bash
lsusb | grep -i -e 0414 -e 1044 -e gigabyte -e ite
aero-kbd detect --json
```

`aero-kbd detect` only reads sysfs; it never writes to the keyboard. The useful
facts are the USB vendor and product ID, which interface carries the vendor
usage page, and the size of its feature report.

There are two cases:

- **Same controller family.** The vendor/product ID differs but the control
  interface has usage page `0xff01` and 9-byte feature reports, like the
  AERO X16. The existing protocol code very likely applies and the work is
  mostly declaring the new ID.
- **A different controller.** Older Aero models use other controllers, some
  with per-key lighting and a different report format. These need their own
  protocol module next to `protocol.py`, written from captures.

## 2. Capture before writing anything

Follow [the Windows capture workflow](WINDOWS_GIMATE_CAPTURE_PROMPT.md): record
what GiMATE / Control Center sends for each setting, and derive the reports
from those captures. An effect stays out of the allow-list until it has been
captured and then replayed successfully on real hardware.

## 3. What has to change in the code

The vendor and product ID are currently fixed in several places, so a second
model touches each of them:

| Where | What |
| --- | --- |
| `devices/<vid>-<pid>.json` | The model's profile: IDs, usage page, report size, tested models, safe and experimental effects |
| `src/aero_keyboard/discovery.py` | `DEFAULT_VENDOR_ID` / `DEFAULT_PRODUCT_ID` select the one supported ID |
| `packaging/udev/70-aero-keyboard.rules` | One `uaccess` line per ID, limited to the control interface |
| `src/aero_keyboard/device.py`, `cli.py` | Error messages that name `0414:8104` |
| `src/aero_keyboard/gui/main_window.py` | The model name in the header, status pill, Device and About pages |

The intended end state, per the project plan, is that the profile files drive
all of this: discovery tries every known ID, the udev rule is generated from
the profiles, and the interface shows the name and effects of whichever
keyboard was found. Once that registry exists, a same-family model is one
profile file plus a hardware report.

## 4. Validate and record

1. Run the mocked tests: `.venv/bin/pytest`.
2. On the real laptop, check `aero-kbd firmware`, `aero-kbd status`, a static
   color, brightness, and `aero-kbd off`.
3. Add the exact model and firmware to `tested_models` in the profile and to
   the supported-hardware table in the README.
4. Open a pull request with a filled-in hardware report.

Owners of other models who cannot do the capture work can still help by filing
a **Hardware report** issue with the output of the commands in step 1.
