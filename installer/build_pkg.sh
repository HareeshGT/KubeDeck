#!/bin/bash
set -e

if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERROR: Build this package on macOS."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
INSTALLER="$SCRIPT_DIR/installer.sh"
VERSION="${1:-1.0.0}"
OUTPUT="${2:-$ROOT/dist/KubeDock-$VERSION.pkg}"

if [ ! -f "$INSTALLER" ]; then
  echo "ERROR: installer.sh not found: $INSTALLER"
  exit 1
fi

command -v pkgbuild >/dev/null 2>&1 || {
  echo "ERROR: pkgbuild not found. Install Xcode Command Line Tools."
  exit 1
}

TMP="$(mktemp -d /tmp/kubedeck-pkg.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
SCRIPTS="$TMP/scripts"
mkdir -p "$SCRIPTS" "$(dirname "$OUTPUT")"

cat > "$SCRIPTS/postinstall" <<'POSTINSTALL'
#!/bin/bash
set -e

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
WORK="$(mktemp -d /tmp/kubedeck-install.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

cp "$SCRIPT_DIR/installer.sh" "$WORK/installer.sh"
chmod 755 "$WORK/installer.sh"
cd "$WORK"

export KUBEDECK_PKG_MODE=1
/bin/bash "$WORK/installer.sh"
POSTINSTALL

cp "$INSTALLER" "$SCRIPTS/installer.sh"
chmod 755 "$SCRIPTS/postinstall" "$SCRIPTS/installer.sh"

rm -f "$OUTPUT"

ARGS=(
  pkgbuild
  --nopayload
  --scripts "$SCRIPTS"
  --identifier com.hareeshgt.kubedeck.installer
  --version "$VERSION"
  --compression latest
)

if [ -n "$PKG_SIGN_IDENTITY" ]; then
  ARGS+=(--sign "$PKG_SIGN_IDENTITY")
fi

ARGS+=("$OUTPUT")
"${ARGS[@]}"

echo
echo "Created: $OUTPUT"
