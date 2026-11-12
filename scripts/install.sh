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

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
trap 'exit 1' INT TERM

if [ -z "$ref" ]; then
  # Only a missing release is allowed to fall back to the development branch.
  if ! http_status=$(curl -sSL -o "$work/release.json" -w '%{http_code}' \
    "https://api.github.com/repos/$repo/releases/latest"); then
    printf 'Could not look up the latest release.\n' >&2
    exit 1
  fi
  case "$http_status" in
  200)
    ref=$(sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' "$work/release.json" | head -n 1)
    if [ -z "$ref" ]; then
      printf 'The release response did not contain a tag name.\n' >&2
      exit 1
    fi
    ;;
  404) ref=main ;;
  *)
    printf 'Could not look up the latest release (HTTP %s).\n' "$http_status" >&2
    exit 1
    ;;
  esac
  rm -f "$work/release.json"
fi

printf 'Downloading %s (%s)...\n' "$repo" "$ref"
curl -fsSL "https://github.com/$repo/archive/$ref.tar.gz" | tar -xz -C "$work" --strip-components=1

# The download is deleted afterwards, so the code must be copied, not linked.
sh "$work/scripts/install-app.sh" --no-editable "$@"
