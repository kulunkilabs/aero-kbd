#!/bin/sh
# Download Aero Keyboard Control and install it for the current user:
#
#   curl -fsSL https://raw.githubusercontent.com/kulunkilabs/aero-kbd/main/scripts/install.sh | sh
#
# Options are passed on to install-app.sh, for example to remove the install:
#
#   curl -fsSL .../scripts/install.sh | sh -s -- --uninstall
#
# AERO_KBD_REF picks a tag or branch instead of the latest release, and
# AERO_KBD_REPO picks a fork (owner/name).
set -eu

repo=${AERO_KBD_REPO:-kulunkilabs/aero-kbd}
ref=${AERO_KBD_REF:-}

for tool in curl tar python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf '%s is required; install it with your package manager.\n' "$tool" >&2
    exit 1
  fi
done

if [ -z "$ref" ]; then
  # Prefer the newest tagged release; a repository without one falls back to main.
  ref=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" 2>/dev/null |
    sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1) || true
  ref=${ref:-main}
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
trap 'exit 1' INT TERM

printf 'Downloading %s (%s)...\n' "$repo" "$ref"
curl -fsSL "https://github.com/$repo/archive/$ref.tar.gz" | tar -xz -C "$work" --strip-components=1

# The download is deleted afterwards, so the code must be copied, not linked.
sh "$work/scripts/install-app.sh" --no-editable "$@"
