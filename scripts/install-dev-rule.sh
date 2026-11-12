#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(dirname -- "$script_dir")
rule_source="$project_dir/packaging/udev/70-aero-keyboard.rules"
rule_target="/etc/udev/rules.d/70-aero-keyboard.rules"

sudo install -D -o root -g root -m 0644 "$rule_source" "$rule_target"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw --action=add
udevadm settle

printf '\nInstalled %s\n' "$rule_target"
