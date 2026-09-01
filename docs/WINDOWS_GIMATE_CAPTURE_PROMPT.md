# Windows GiMATE USB capture agent prompt

Use the following prompt with an agent running on Windows. Keep the resulting
capture files private because raw keyboard USB captures may contain keystrokes.

```text
We are reverse-engineering keyboard RGB control for my:

- Laptop: GIGABYTE AERO X16 1WH
- Keyboard USB VID:PID: 0414:8104
- Controller family: ITE-829X
- Known RGB control interface: USB interface 03
- Windows application: GIGABYTE GiMATE
- Linux project: aero-keyboard-control

Goal:
Passively capture and analyze the USB traffic GiMATE sends when changing the
keyboard from predefined colors to arbitrary custom RGB colors. We need to
discover whether GiMATE uses the device's 64-byte HID output channel and
identify the exact report format for red, green, blue, brightness, command,
framing, and checksum fields.

Critical safety rules:

1. GiMATE must be the only software writing to the keyboard.
2. Do not send crafted, replayed, modified, guessed, or raw HID reports.
3. Do not detach, replace, disable, or modify the keyboard driver.
4. Do not reset or update keyboard firmware.
5. Do not modify fan, power, battery, BIOS, CPU, or GPU settings.
6. USBPcap/Wireshark must be used only for passive capture.
7. Ask me before installing software or making administrator-level changes.
8. Do not upload capture files publicly. Keyboard USB captures may contain
   keystrokes.
9. Return the keyboard to static white at 25% brightness when finished.

Create this workspace:

C:\Users\<current-user>\Documents\aero-rgb-capture\

Store:

- system-info.txt
- device-info.txt
- gimate-version.txt
- manifest.csv
- notes.md
- captures\
- extracted-reports.csv
- analysis.md

Phase 1: Record environment

Collect without changing hardware:

- Windows edition and build
- Laptop manufacturer and complete model
- GiMATE version
- Matching PnP devices for VID_0414&PID_8104
- Device instance IDs
- USB parent/root hub
- Interfaces and endpoints if Windows exposes them
- Current keyboard lighting state

Useful PowerShell starting point:

Get-ComputerInfo |
  Select-Object WindowsProductName, WindowsVersion, OsBuildNumber |
  Format-List

Get-CimInstance Win32_ComputerSystem |
  Select-Object Manufacturer, Model |
  Format-List

Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -match 'VID_0414&PID_8104' } |
  Format-List Status, Class, FriendlyName, InstanceId

Save results to the workspace. Do not include passwords, account tokens,
serial numbers unrelated to the keyboard, or other secrets.

Phase 2: Prepare passive capture

Check whether Wireshark, USBPcap, and tshark are installed.

If they are missing, explain exactly what needs to be installed and ask for
permission. Prefer official Wireshark/USBPcap packages.

Identify which USBPcap root hub contains 0414:8104. Capture the whole relevant
root hub; do not apply an overly narrow capture filter that could discard
control transfers.

Close unrelated applications where practical. Do not type passwords or private
messages during capture.

Phase 3: Controlled capture sequence

Keep these constant unless a step explicitly changes them:

- Effect: Static
- Brightness: 25%
- Direction: default
- Speed: default

Prefer a separate PCAPNG file for every Apply action. Start capture, wait two
seconds, make exactly one change in GiMATE, click Apply, wait three seconds,
then stop capture.

Capture these predefined settings:

1. predefined-red.pcapng
2. predefined-green.pcapng
3. predefined-blue.pcapng
4. predefined-white.pcapng

If GiMATE offers a true custom color picker or RGB/hex input, capture:

5. custom-ff0000.pcapng
6. custom-00ff00.pcapng
7. custom-0000ff.pcapng
8. custom-123456.pcapng
9. custom-112233.pcapng
10. custom-00ffff.pcapng
11. custom-ff00ff.pcapng
12. custom-808080.pcapng

The non-primary colors are important because they help distinguish direct RGB
bytes from color IDs, channel order, RGB565 encoding, palette lookup, or
checksum data.

Then test brightness while keeping custom color #123456:

13. custom-123456-brightness-10.pcapng
14. custom-123456-brightness-25.pcapng
15. custom-123456-brightness-50.pcapng
16. custom-123456-brightness-100.pcapng

If GiMATE does not offer arbitrary RGB input, do not invent a method. Capture
every color it does provide and document that custom RGB is unavailable in the
UI.

Maintain manifest.csv with:

filename, effect, requested_hex, brightness, speed, direction, apply_time,
visible_result, notes

Phase 4: Extract USB reports

Analyze traffic for device 0414:8104, especially interface 03.

Look for:

- HID SET_REPORT control transfers
- bmRequestType 0x21
- bRequest 0x09
- Feature reports
- Output reports
- Interrupt OUT transfers
- 9-byte reports
- 64-byte reports
- usb.capdata or usbhid.data payloads

Export matching transfers to extracted-reports.csv with at least:

capture_file, frame_number, relative_time, device_address, interface, endpoint,
transfer_type, request_type, request, wValue, wIndex, payload_length,
payload_hex, requested_color, brightness

Keep the original PCAPNG files unchanged.

Phase 5: Compare reports

Determine:

1. Which reports are common background traffic.
2. Which report changes when only the color changes.
3. Whether bytes FF 00 00, 00 FF 00, and 00 00 FF appear directly.
4. Whether #123456 produces 12 34 56, another channel order, or encoded values.
5. Which byte changes only with brightness.
6. Whether the final byte is a checksum.
7. Whether reports are sent through feature reports or 64-byte output reports.
8. Whether one Apply operation sends initialization, frame data, and commit
   reports.
9. Whether GiMATE continuously streams frames or sends only when Apply is
   clicked.
10. Whether the protocol addresses one zone or individual LEDs.

Do not infer a format from only one packet. Compare all controlled captures and
clearly separate confirmed observations, strong hypotheses, and unknown fields.

Known Linux feature-report checksum for the existing 9-byte effect command is:

checksum = (0xFF - (sum(bytes[0..7]) & 0xFF)) & 0xFF

Check whether the custom-color traffic uses this checksum, but do not assume it
does.

Phase 6: Deliverables

Write analysis.md containing:

- Exact device and interface used
- GiMATE version
- Capture procedure
- Relevant report types and endpoints
- Side-by-side packet comparison table
- Candidate R/G/B offsets
- Candidate brightness offset
- Candidate checksum/framing
- Confidence level for each finding
- Remaining unknowns
- Recommended next safe experiment

Do not replay any traffic.

At completion:

1. Set keyboard to Static, White, 25%.
2. Verify visually.
3. Confirm all artifacts exist.
4. Give me the full workspace path.
5. Summarize the most important findings.
6. Tell me which files to transfer back to Linux.

If an administrator prompt is required for USBPcap, pause and let me approve it.
Never ask me to paste a password or token into the conversation.
```

After capture, transfer the entire `aero-rgb-capture` directory to
`~/Documents/` for Linux-side analysis.
