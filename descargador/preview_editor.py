"""Editor de recortes con una copia temporal de previsualizacion.

Se ejecuta en un proceso propio porque Tkinter y Qt tienen bucles de eventos
incompatibles. Sigue siendo parte de ControlApps y devuelve el rango elegido
en un JSON que la ventana principal lee al instante.
"""

import json
import os
import sys
from pathlib import Path


def _tiempo(ms):
    segundos = max(0, int(ms / 1000))
    minutos, segundos = divmod(segundos, 60)
    horas, minutos = divmod(minutos, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}" if horas else f"{minutos:02}:{segundos:02}"


def _ffmpeg_location():
    carpeta = getattr(sys, "_MEIPASS", None)
    if carpeta:
        nombre = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        if os.path.exists(os.path.join(carpeta, nombre)):
            return carpeta
    return None


def _descargar_previsualizacion(url, destino, progreso):
    import yt_dlp
    opciones = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bv*[height<=480]+ba/b[height<=480]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(destino.with_suffix(".%(ext)s")),
        "progress_hooks": [progreso],
        "windowsfilenames": True,
    }
    ffmpeg = _ffmpeg_location()
    if ffmpeg:
        opciones["ffmpeg_location"] = ffmpeg
    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([url])
    archivos = [p for p in destino.parent.glob(destino.name + ".*") if p.suffix not in {".part", ".ytdl"}]
    if not archivos:
        raise RuntimeError("No se genero la previsualizacion")
    return max(archivos, key=lambda p: p.stat().st_mtime)


def main(config_path):
    from PySide6.QtCore import QUrl, Qt, QThread, Signal
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from PySide6.QtWidgets import (
        QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
        QSlider, QVBoxLayout,
    )

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    class Descarga(QThread):
        listo = Signal(str)
        fallo = Signal(str)
        estado = Signal(str)

        def run(self):
            try:
                carpeta = Path(config_path).parent
                destino = carpeta / "previsualizacion"
                def progreso(data):
                    if data.get("status") == "downloading":
                        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                        pct = int(data.get("downloaded_bytes", 0) * 100 / total) if total else 0
                        self.estado.emit(f"Preparando previsualizacion... {pct}%")
                self.listo.emit(str(_descargar_previsualizacion(config["url"], destino, progreso)))
            except Exception as exc:
                self.fallo.emit(str(exc))

    class Editor(QDialog):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("ControlApps · Editor de recorte")
            self.resize(900, 680)
            self.setMinimumSize(700, 560)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.audio.setVolume(0.8)
            self.inicio = int(config.get("inicio", 0)) * 1000
            self.fin = int(config.get("fin", 0)) * 1000
            self.duracion = int(config.get("duracion", 0)) * 1000
            self.listos = False

            layout = QVBoxLayout(self)
            titulo = QLabel("Editor de recorte")
            titulo.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a;")
            layout.addWidget(titulo)
            subtitulo = QLabel("Previsualizacion temporal · el rango se reproduce en loop")
            subtitulo.setStyleSheet("color: #64748b;")
            layout.addWidget(subtitulo)

            self.video = QVideoWidget()
            self.video.setMinimumHeight(350)
            self.video.setStyleSheet("background: #0f172a;")
            self.player.setVideoOutput(self.video)
            layout.addWidget(self.video, 1)
            self.estado = QLabel("Preparando video para previsualizar...")
            layout.addWidget(self.estado)

            self.reproduccion = QSlider(Qt.Horizontal)
            self.reproduccion.setEnabled(False)
            layout.addWidget(self.reproduccion)
            for nombre in ("Inicio", "Fin"):
                fila = QHBoxLayout()
                etiqueta = QLabel(nombre)
                etiqueta.setFixedWidth(52)
                control = QSlider(Qt.Horizontal)
                valor = QLabel("00:00")
                valor.setFixedWidth(58)
                fila.addWidget(etiqueta); fila.addWidget(control, 1); fila.addWidget(valor)
                layout.addLayout(fila)
                if nombre == "Inicio":
                    self.inicio_control, self.inicio_valor = control, valor
                else:
                    self.fin_control, self.fin_valor = control, valor

            acciones = QHBoxLayout()
            self.play = QPushButton("Reproducir recorte")
            self.play.setEnabled(False)
            self.play.clicked.connect(self.reproducir_rango)
            self.pausa = QPushButton("Pausar")
            self.pausa.setEnabled(False)
            self.pausa.clicked.connect(self.player.pause)
            cancelar = QPushButton("Cancelar")
            cancelar.clicked.connect(self.reject)
            aceptar = QPushButton("Usar este recorte")
            aceptar.setStyleSheet("background: #2563eb; color: white; font-weight: 700; padding: 7px 12px;")
            aceptar.setEnabled(False)
            aceptar.clicked.connect(self.aceptar)
            acciones.addWidget(self.play); acciones.addWidget(self.pausa); acciones.addStretch(); acciones.addWidget(cancelar); acciones.addWidget(aceptar)
            layout.addLayout(acciones)
            self.aceptar_boton = aceptar

            self.inicio_control.valueChanged.connect(self.cambiar_inicio)
            self.fin_control.valueChanged.connect(self.cambiar_fin)
            self.reproduccion.sliderMoved.connect(self.player.setPosition)
            self.player.positionChanged.connect(self.actualizar_posicion)
            self.player.durationChanged.connect(self.cargar_duracion)
            self.descarga = Descarga(self)
            self.descarga.estado.connect(self.estado.setText)
            self.descarga.listo.connect(self.cargar_video)
            self.descarga.fallo.connect(lambda _: self.estado.setText("No se pudo preparar la previsualizacion."))
            self.descarga.start()

        def cargar_video(self, archivo):
            self.player.setSource(QUrl.fromLocalFile(archivo))
            self.estado.setText("Video listo. Ajusta Inicio y Fin, luego reproduce el rango.")

        def cargar_duracion(self, duracion):
            if not duracion:
                return
            self.duracion = duracion
            for control in (self.reproduccion, self.inicio_control, self.fin_control):
                control.setRange(0, duracion)
                control.setEnabled(True)
            self.inicio = min(self.inicio, duracion)
            self.fin = self.fin if self.fin else duracion
            self.fin = min(max(self.fin, self.inicio + 1000), duracion)
            self.inicio_control.setValue(self.inicio)
            self.fin_control.setValue(self.fin)
            self.listos = True
            self.play.setEnabled(True); self.pausa.setEnabled(True); self.aceptar_boton.setEnabled(True)

        def cambiar_inicio(self, valor):
            self.inicio = min(valor, self.fin - 1000) if self.fin else valor
            self.inicio_control.blockSignals(True); self.inicio_control.setValue(self.inicio); self.inicio_control.blockSignals(False)
            self.inicio_valor.setText(_tiempo(self.inicio))

        def cambiar_fin(self, valor):
            self.fin = max(valor, self.inicio + 1000)
            self.fin_control.blockSignals(True); self.fin_control.setValue(self.fin); self.fin_control.blockSignals(False)
            self.fin_valor.setText(_tiempo(self.fin))

        def actualizar_posicion(self, posicion):
            self.reproduccion.blockSignals(True); self.reproduccion.setValue(posicion); self.reproduccion.blockSignals(False)
            if self.listos and self.player.playbackState() == QMediaPlayer.PlayingState and posicion >= self.fin:
                self.player.setPosition(self.inicio)

        def reproducir_rango(self):
            self.player.setPosition(self.inicio)
            self.player.play()

        def aceptar(self):
            Path(config["resultado"]).write_text(json.dumps({"inicio": self.inicio // 1000, "fin": self.fin // 1000}), encoding="utf-8")
            self.accept()

    app = QApplication.instance() or QApplication([])
    editor = Editor()
    editor.exec()
    return 0


if __name__ == "__main__":
    main(sys.argv[1])
