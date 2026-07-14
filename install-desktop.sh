#!/usr/bin/env bash
# Install (or remove) the PasteUp launcher entry + icon for the current user.
# After this, PasteUp shows up in the app grid / launcher search like any
# installed application. Usage:  ./install-desktop.sh [--uninstall]
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
apps="$HOME/.local/share/applications"
icons="$HOME/.local/share/icons/hicolor/scalable/apps"
desktop="$apps/pasteup.desktop"
icon="$icons/pasteup.svg"

refresh_caches() {
    update-desktop-database "$apps" 2>/dev/null || true
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$desktop" "$icon"
    refresh_caches
    echo "PasteUp launcher entry removed."
    exit 0
fi

python="$here/.venv/bin/python"
if [ ! -x "$python" ]; then
    echo "No .venv yet — run ./run.sh once first." >&2
    exit 1
fi

# the launcher starts the app from an arbitrary directory, so the package
# must be properly installed in the venv (editable: still runs live source)
if ! "$python" -c "import pasteup" >/dev/null 2>&1; then
    echo "Installing PasteUp into its virtualenv (one time)…"
    "$python" -m pip install -q -e "$here"
fi

mkdir -p "$apps" "$icons"
cp "$here/pasteup/appicon.svg" "$icon"
cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PasteUp
GenericName=Image Annotator
Comment=Paste in screenshots and mark them up
Exec=$python -m pasteup
Path=$here
Icon=pasteup
Terminal=false
Categories=Graphics;2DGraphics;RasterGraphics;Qt;
Keywords=annotate;annotation;screenshot;markup;arrow;callout;snagit;
StartupNotify=true
StartupWMClass=PasteUp
EOF
refresh_caches
echo "Installed: $desktop"
echo "PasteUp should now appear in your launcher search."
