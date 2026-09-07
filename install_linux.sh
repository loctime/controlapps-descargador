#!/usr/bin/env bash
set -euo pipefail

# Instalador local para Ubuntu/Debian y distribuciones con Python 3, FFmpeg y
# xdg-open. Ejecutar desde la carpeta descomprimida del proyecto:
#   bash install_linux.sh

for comando in python3 ffmpeg xdg-open tar; do
  if ! command -v "$comando" >/dev/null 2>&1; then
    echo "Falta $comando. En Ubuntu/Debian instala: sudo apt install python3 python3-venv ffmpeg xdg-utils"
    exit 1
  fi
done

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$HOME/.local/share/controlapps-descargador"
APP="$BASE/app"
VENV="$BASE/venv"
DESKTOP="$HOME/.local/share/applications/controlapps-descargador.desktop"

mkdir -p "$APP" "$(dirname "$DESKTOP")"
rm -rf "$APP"
mkdir -p "$APP"
tar --exclude=.git --exclude=build --exclude=dist --exclude=release --exclude=.pytest_cache \
  -C "$ORIGEN" -cf - . | tar -C "$APP" -xf -

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$APP/requirements.txt"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=ControlApps Descargador
Comment=Descargas de archivos, YouTube e Instagram
Exec=$VENV/bin/python $APP/run.py
Terminal=false
Categories=Network;Utility;
EOF

echo "ControlApps Descargador se instalo correctamente. Buscalo en el menu de aplicaciones."
