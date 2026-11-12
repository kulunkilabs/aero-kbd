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
state_dir="$data_home/aero-keyboard-control"
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

if [ ! -x "$venv_dir/bin/python" ]; then
  python3 -m venv "$venv_dir"
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
sed "s|^Exec=.*|Exec=${gui_bin}|" "$desktop_src" >"$desktop_dst"
chmod 0644 "$desktop_dst"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q "$applications_dir" 2>/dev/null || true
fi

if [ "$skip_udev" = false ]; then
  if [ -w /etc/udev/rules.d ] 2>/dev/null; then
    sh "$project_dir/scripts/install-dev-rule.sh"
  elif command -v sudo >/dev/null 2>&1; then
    sh "$project_dir/scripts/install-dev-rule.sh"
  else
    printf '\nSkipping udev rule (no sudo). Install later with:\n'
    printf '  %s/scripts/install-dev-rule.sh\n\n' "$project_dir"
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
