---
name: Hardware report
about: Report a GIGABYTE laptop that works, or one you would like supported
title: "Hardware: <laptop model>"
labels: hardware
---

**Laptop model** (exact name, for example "AERO X16 1WH"):

**Distribution and kernel** (`uname -r`):

**Keyboard USB devices** — output of `lsusb | grep -i -e 0414 -e 1044 -e gigabyte -e ite`:

```
```

**Detection** — output of `aero-kbd detect --json` (safe: it never writes to the keyboard):

```
```

**If the keyboard is detected** — output of `aero-kbd firmware` and `aero-kbd status`:

```
```

**What works and what does not** (static colors, brightness, off):
