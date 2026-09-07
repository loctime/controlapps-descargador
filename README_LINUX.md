# ControlApps Descargador en Linux

La aplicacion funciona en Linux con interfaz grafica Tk, YouTube, Instagram y
recortes por rango. Requiere una sesion grafica de escritorio, Python 3 y
FFmpeg.

## Instalacion sencilla

En Ubuntu/Debian instala una vez los requisitos del sistema:

```bash
sudo apt install python3 python3-venv ffmpeg xdg-utils
```

Desde la carpeta del proyecto ejecuta:

```bash
bash install_linux.sh
```

El instalador crea un acceso en el menu como **ControlApps Descargador** y
guarda la configuracion en `~/.descargador`.

## Archivo universal AppImage

Para generar el unico archivo universal desde una PC Linux x86_64:

```bash
bash build_linux.sh
```

El resultado es `release/ControlApps-Descargador-x86_64.AppImage`. La persona
que lo recibe solo le da permiso de ejecucion una vez y lo abre:

```bash
chmod +x ControlApps-Descargador-x86_64.AppImage
./ControlApps-Descargador-x86_64.AppImage
```

No instala Python ni FFmpeg. En algunas distribuciones recientes puede requerir
el paquete `libfuse2` para abrir AppImages. La compilacion debe hacerse en
Linux: PyInstaller no genera un binario Linux fiable desde Windows.
