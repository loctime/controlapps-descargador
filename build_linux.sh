#!/usr/bin/env bash
set -euo pipefail

# Crea un unico archivo universal para Linux x86_64. Debe ejecutarse EN Linux.
for comando in python3 ffmpeg curl; do
  command -v "$comando" >/dev/null 2>&1 || {
    echo "Falta $comando. En Ubuntu/Debian: sudo apt install python3-venv ffmpeg curl"
    exit 1
  }
done

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"
VENV="$RAIZ/.build-venv"
HERRAMIENTAS="$RAIZ/.tools"
APPDIR="$RAIZ/AppDir"
SALIDA="$RAIZ/release/ControlApps-Descargador-x86_64.AppImage"
APPIMAGETOOL="$HERRAMIENTAS/appimagetool-x86_64.AppImage"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements.txt pyinstaller
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --windowed \
  --name "ControlApps Descargador" --collect-all yt_dlp --collect-all PySide6 \
  --add-binary "$(command -v ffmpeg):." run.py

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$HERRAMIENTAS" "$(dirname "$SALIDA")"
cp -a "dist/ControlApps Descargador" "$APPDIR/usr/bin/ControlApps Descargador"
cp "packaging/linux/controlapps-descargador.desktop" "$APPDIR/"
cp "packaging/linux/controlapps-descargador.svg" "$APPDIR/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/usr/bin/ControlApps Descargador/ControlApps Descargador" "$@"
EOF
chmod +x "$APPDIR/AppRun"

if [ ! -x "$APPIMAGETOOL" ]; then
  curl -L --fail -o "$APPIMAGETOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$SALIDA"
echo "AppImage creado: $SALIDA"
