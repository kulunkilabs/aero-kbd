#!/bin/sh
# Install Aero Keyboard Control for the current user (XDG app menu icon + GUI).
# Works on Arch, CachyOS, Omarchy, and other rolling Arch-based distros with python3.
set -eu

usage() {
  cat <<'EOF'
Usage: install-app.sh [options]

Install the GUI into ~/.local (virtualenv) and register a launcher icon.

Options:
  --skip-udev    Do not install or reload the udev rule (requires sudo).
  --no-editable  Copy the code into the virtualenv instead of linking this checkout.
  --uninstall    Remove the user install (venv, desktop entry, icon).
  -h, --help     Show this help.

After install, open "Aero Keyboard Control" from your application menu.
Log out and back in if the keyboard device stays permission-denied.
EOF
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(dirname -- "$script_dir")

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
state_dir="$data_home/aero-kbd"
venv_dir="$state_dir/venv"
desktop_id=io.github.aero_keyboard_control
desktop_src="$project_dir/packaging/desktop/${desktop_id}.desktop"
icon_src="$project_dir/packaging/icon/${desktop_id}.svg"
applications_dir="$data_home/applications"
icons_dir="$data_home/icons/hicolor/scalable/apps"
desktop_dst="$applications_dir/${desktop_id}.desktop"
icon_dst="$icons_dir/${desktop_id}.svg"

skip_udev=false
uninstall=false
editable=true

for arg in "$@"; do
  case "$arg" in
  --skip-udev) skip_udev=true ;;
  --uninstall) uninstall=true ;;
  --no-editable) editable=false ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    printf 'Unknown option: %s\n' "$arg" >&2
    usage >&2
    exit 2
    ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  printf 'python3 is required; install the python package on your distro.\n' >&2
  exit 1
fi

if "$uninstall"; then
  rm -f "$desktop_dst" "$icon_dst"
  rm -rf "$state_dir"
  printf 'Removed user install under %s\n' "$state_dir"
  exit 0
fi

if [ ! -f "$desktop_src" ] || [ ! -f "$icon_src" ]; then
  printf 'Missing packaging files under %s/packaging\n' "$project_dir" >&2
  exit 1
fi

mkdir -p "$state_dir" "$applications_dir" "$icons_dir"

# A system Python upgrade can leave an existing venv without a working pip; rebuild it then.
if ! "$venv_dir/bin/python" -m pip --version >/dev/null 2>&1; then
  python3 -m venv --clear "$venv_dir"
fi

"$venv_dir/bin/pip" install -q --upgrade pip
if "$editable"; then
  "$venv_dir/bin/pip" install -q -e "$project_dir[gui]"
else
  # A linked install would break as soon as a downloaded checkout is deleted.
  "$venv_dir/bin/pip" install -q --upgrade --force-reinstall --no-deps "$project_dir"
  "$venv_dir/bin/pip" install -q "$project_dir[gui]"
fi

gui_bin="$venv_dir/bin/aero-kbd-gui"
if [ ! -x "$gui_bin" ]; then
  printf 'Install failed: %s not found\n' "$gui_bin" >&2
  exit 1
fi

install -D -m 0644 "$icon_src" "$icon_dst"

# Desktop entries must use an absolute Exec path so session PATH is irrelevant.
python3 - "$desktop_src" "$desktop_dst" "$gui_bin" <<'PY'
import sys
from pathlib import Path

source, destination, executable = sys.argv[1:]
quoted = executable.replace("\\", "\\\\").replace("%", "%%")
for character in ('"', '`', '$'):
    quoted = quoted.replace(character, "\\" + character)
value = ('"' + quoted + '"').replace("\\", "\\\\")
value = value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
desktop = Path(source).read_text(encoding="utf-8")
desktop = "".join(
    f"Exec={value}\n" if line.startswith("Exec=") else line
    for line in desktop.splitlines(keepends=True)
)
Path(destination).write_text(desktop, encoding="utf-8")
PY
chmod 0644 "$desktop_dst"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q "$applications_dir" 2>/dev/null || true
fi

if [ "$skip_udev" = false ]; then
  if [ -w /etc/udev/rules.d ] 2>/dev/null; then
    # Already allowed to write the rule (e.g. as root), so do not depend on sudo.
    rule_target=/etc/udev/rules.d/70-aero-keyboard.rules
    install -D -m 0644 "$project_dir/packaging/udev/70-aero-keyboard.rules" "$rule_target"
    if command -v udevadm >/dev/null 2>&1; then
      udevadm control --reload-rules || true
      udevadm trigger --subsystem-match=hidraw --action=add || true
    fi
    printf '\nInstalled %s\n' "$rule_target"
  elif command -v sudo >/dev/null 2>&1; then
    sh "$project_dir/scripts/install-dev-rule.sh"
  else
    saved_rule="$state_dir/70-aero-keyboard.rules"
    install -m 0644 "$project_dir/packaging/udev/70-aero-keyboard.rules" "$saved_rule"
    printf '\nSkipping udev rule (no sudo). The rule is saved at:\n  %s\n' "$saved_rule"
    printf 'As root, copy it to /etc/udev/rules.d/70-aero-keyboard.rules, then run:\n'
    printf '  udevadm control --reload-rules\n'
    printf '  udevadm trigger --subsystem-match=hidraw --action=add\n\n'
  fi
fi

cat <<EOF

Aero Keyboard Control is installed.

  GUI:        $gui_bin
  Launcher:   $desktop_dst
  Data/venv:  $state_dir

Open "Aero Keyboard Control" from your application menu (Settings or search "Aero").
To remove: run this installer again with --uninstall

EOF
