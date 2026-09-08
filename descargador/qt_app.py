"""Interfaz Qt de una sola ventana para ControlApps Descargador."""

import json
import os
import queue
import shutil
import sys
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSlider, QSpinBox, QStackedWidget, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .app import CONFIG, ESTADO, _cargar_config, _guardar_config, _tiempo_humano
from .browser import resolve_with_browser
from .downloader import download
from .engine import Engine
from .links import parse_links, sort_by_part
from .resolvers import get_resolver
from .search import buscar_youtube
from .state import State
from .system import abrir_ruta
from .version import APP_VERSION


def _ffmpeg_location():
    folder = getattr(sys, "_MEIPASS", None)
    if folder:
        name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        if os.path.isfile(os.path.join(folder, name)):
            return folder
    return None


def _ffmpeg_command():
    location = _ffmpeg_location()
    if location:
        return os.path.join(location, "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    return "ffmpeg"


class Signals(QObject):
    metadata = Signal(dict)
    preview_ready = Signal(str)
    error = Signal(str)
    search_ready = Signal(list)
    progress = Signal(str)
    thumbnail = Signal(str)


class CropPage(QWidget):
    """Vista interna: nunca abre una segunda ventana."""
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.url = None
        self.info = None
        self.preview_dir = None
        self.ready = False
        self.signals = Signals()
        self.signals.metadata.connect(self._metadata_ready)
        self.signals.preview_ready.connect(self._preview_ready)
        self.signals.error.connect(self._error)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(.8)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self._build()
        self.signals.progress.connect(self.status.setText)
        self.signals.thumbnail.connect(self._thumbnail_ready)

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 4)
        left = QVBoxLayout()
        self.status = QLabel("Preparando previsualizacion...")
        self.status.setObjectName("muted")
        self.video = QVideoWidget()
        self.video.setMinimumSize(280, 158)
        self.video.setMaximumSize(300, 170)
        self.video.setStyleSheet("background:#000; border-radius:8px;")
        self.player.setVideoOutput(self.video)
        self.cover = QLabel("Miniatura del video")
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setMinimumSize(280, 158); self.cover.setMaximumSize(300, 170)
        self.cover.setStyleSheet("background:#e2e8f0; color:#64748b; border-radius:8px;")
        left.addWidget(self.cover)
        self.video.hide()
        left.addWidget(self.video)
        layout.addLayout(left)
        right = QVBoxLayout()
        right.addWidget(self.status)
        self.playhead = QSlider(Qt.Horizontal)
        self.playhead.setEnabled(False)
        self.playhead.sliderMoved.connect(self.player.setPosition)
        right.addWidget(self.playhead)
        self.start, self.start_text = self._range_row(right, "Inicio")
        self.end, self.end_text = self._range_row(right, "Fin")
        self.start.valueChanged.connect(self._start_changed)
        self.end.valueChanged.connect(self._end_changed)
        actions = QHBoxLayout()
        self.play = QPushButton("▶ Reproducir recorte")
        self.play.setObjectName("primary")
        self.play.setEnabled(False); self.play.clicked.connect(self._play_range)
        pause = QPushButton("Pausar"); pause.clicked.connect(self.player.pause)
        add = QPushButton("Usar este recorte")
        add.setObjectName("primary"); add.setEnabled(False); add.clicked.connect(self._accept)
        self.add = add
        actions.addWidget(self.play); actions.addWidget(pause); actions.addStretch(); actions.addWidget(add)
        right.addLayout(actions)
        layout.addLayout(right, 1)

    def _range_row(self, layout, label):
        row = QHBoxLayout()
        text = QLabel(label); text.setFixedWidth(54)
        slider = QSlider(Qt.Horizontal); slider.setEnabled(False)
        value = QLabel("00:00"); value.setMinimumWidth(58)
        row.addWidget(text); row.addWidget(slider, 1); row.addWidget(value)
        layout.addLayout(row)
        return slider, value

    def open_for(self, url):
        self.url, self.info, self.ready = url, None, False
        self.status.setText("Analizando enlace y preparando una copia temporal...")
        self.player.stop(); self.cover.hide(); self.video.show(); self.play.setEnabled(False); self.add.setEnabled(False)
        threading.Thread(target=self._prepare, daemon=True).start()

    def show_thumbnail(self, url):
        self.url = url
        self.player.stop(); self.video.hide(); self.cover.show(); self.show()
        self.status.setText("Video detectado. Presiona Recortar video para elegir un rango.")
        threading.Thread(target=self._load_thumbnail, args=(url,), daemon=True).start()

    def _load_thumbnail(self, url):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            image_url = info.get("thumbnail")
            if not image_url:
                return
            folder = Path(tempfile.mkdtemp(prefix="controlapps-thumb-"))
            target = folder / "thumbnail.jpg"
            urllib.request.urlretrieve(image_url, target)
            self.signals.thumbnail.emit(str(target))
        except Exception:
            pass

    def _thumbnail_ready(self, path):
        if self.cover.isVisible():
            self.cover.setPixmap(QPixmap(path).scaled(300, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _prepare(self):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
            if not info.get("duration"):
                raise RuntimeError("No se pudo conocer la duracion del video")
            self.signals.metadata.emit(info)
            folder = Path(tempfile.mkdtemp(prefix="controlapps-preview-"))
            self.preview_dir = str(folder)
            options = {
                "quiet": True, "no_warnings": True, "noplaylist": True,
                # Priorizamos H.264/AAC. YouTube suele entregar AV1 primero,
                # pero muchas GPUs integradas no pueden mostrarlo desde Qt.
                "format": "bv*[vcodec^=avc1][height<=480]+ba[acodec^=mp4a]/b[vcodec^=avc1][height<=480]/bv*[height<=480]+ba/b",
                "merge_output_format": "mp4", "outtmpl": str(folder / "preview.%(ext)s"),
                "windowsfilenames": True,
            }
            def download_progress(data):
                if data.get("status") == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    pct = int(data.get("downloaded_bytes", 0) * 100 / total) if total else 0
                    self.signals.progress.emit(f"Descargando copia temporal... {pct}%")
            options["progress_hooks"] = [download_progress]
            ffmpeg = _ffmpeg_location()
            if ffmpeg: options["ffmpeg_location"] = ffmpeg
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([self.url])
            files = [p for p in folder.glob("preview.*") if p.suffix not in {".part", ".ytdl"}]
            source = max(files, key=lambda p: p.stat().st_mtime)
            # Aun cuando el sitio no ofrece H.264, normalizamos la copia de
            # trabajo a H.264 por software. Es temporal y nunca afecta la
            # calidad del archivo final descargado por el usuario.
            compatible = folder / "preview-compatible.mp4"
            self.signals.progress.emit("Convirtiendo la copia a formato compatible... 0%")
            process = subprocess.Popen(
                [_ffmpeg_command(), "-y", "-i", str(source), "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                 "-progress", "pipe:1", "-nostats", str(compatible)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            total_us = int(info.get("duration") or 0) * 1_000_000
            for line in process.stdout:
                if line.startswith("out_time_us=") and total_us:
                    pct = min(100, int(int(line.split("=", 1)[1]) * 100 / total_us))
                    self.signals.progress.emit(f"Convirtiendo la copia a formato compatible... {pct}%")
            process.wait()
            if process.returncode != 0 or not compatible.exists():
                raise RuntimeError("No se pudo convertir la previsualizacion a un formato compatible")
            self.signals.preview_ready.emit(str(compatible))
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def _metadata_ready(self, info):
        self.info = info
        self.status.setText("Descargando copia temporal para editar...")

    def _preview_ready(self, path):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.video.show()
        self.status.setText("Listo. Mueve Inicio y Fin; el rango se reproduce en loop.")
        # QVideoWidget no muestra un fotograma mientras el reproductor queda
        # detenido en 00:00. Arrancar aqui hace visible la previsualizacion
        # apenas termina de bajar, sin que el usuario deba descubrir Play.
        self.player.play()

    def _duration_changed(self, duration):
        if not duration: return
        self.ready = True
        for control in (self.playhead, self.start, self.end):
            control.setRange(0, duration); control.setEnabled(True)
        self.start.setValue(0); self.end.setValue(duration)
        self.play.setEnabled(True); self.add.setEnabled(True)

    def _start_changed(self, value):
        if self.ready and value >= self.end.value():
            self.start.blockSignals(True); self.start.setValue(max(0, self.end.value() - 1000)); self.start.blockSignals(False)
        self.start_text.setText(_tiempo_humano(self.start.value() // 1000))

    def _end_changed(self, value):
        if self.ready and value <= self.start.value():
            self.end.blockSignals(True); self.end.setValue(min(self.playhead.maximum(), self.start.value() + 1000)); self.end.blockSignals(False)
        self.end_text.setText(_tiempo_humano(self.end.value() // 1000))

    def _position_changed(self, position):
        self.playhead.blockSignals(True); self.playhead.setValue(position); self.playhead.blockSignals(False)
        if self.ready and self.player.playbackState() == QMediaPlayer.PlayingState and position >= self.end.value():
            self.player.setPosition(self.start.value())

    def _play_range(self):
        self.player.setPosition(self.start.value()); self.player.play()

    def _accept(self):
        self.window.add_clip(self.url, self.start.value() // 1000, self.end.value() // 1000)
        self.player.pause()
        self.status.setText("Recorte agregado a la cola. Puedes ajustar otro enlace.")

    def show_queue(self):
        self.player.stop()
        if self.preview_dir:
            shutil.rmtree(self.preview_dir, ignore_errors=True); self.preview_dir = None
        self.window.show_queue()

    def _error(self, _):
        self.status.setText("No se pudo preparar la previsualizacion. Revisa que el enlace sea publico.")


class DescargadorQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ControlApps · Descargador")
        self.resize(1060, 700); self.setMinimumSize(860, 580)
        self.cfg = _cargar_config()
        self.carpeta = self.cfg.get("carpeta", "")
        self.conexiones = self.cfg.get("conexiones", 4)
        self.auto_iniciar = self.cfg.get("auto_iniciar", False)
        self.abrir_al_finalizar = self.cfg.get("abrir_al_finalizar", False)
        self.modo = self.cfg.get("modo_descarga", "video")
        self.state = State(ESTADO); self.state.load()
        self.events = queue.Queue(); self.pausado = threading.Event(); self.pausado.set(); self.worker = None
        self.engine = Engine(get_resolver, download, resolve_with_browser,
                             on_update=lambda it: self.events.put(it), should_pause=self.pausado.is_set,
                             get_conexiones=lambda: self.conexiones)
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.crop_page = CropPage(self); self.crop_page.hide()
        self.queue_page = self._queue_page()
        self.stack.addWidget(self.queue_page)
        self._preview_url = None
        self.preview_timer = QTimer(self); self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._inspect_link)
        self.urls.textChanged.connect(lambda: self.preview_timer.start(600))
        self.timer = QTimer(self); self.timer.timeout.connect(self._drain); self.timer.start(250)
        self._refresh(); self._style()

    def _style(self):
        self.setStyleSheet("""
          QWidget { font-family: 'Segoe UI'; font-size: 13px; color:#334155; background:#f8fafc; }
          QFrame#header { background:#0f172a; } QFrame#header QLabel { background:#0f172a; color:#f8fafc; }
          QLabel#brand { font-size:20px; font-weight:700; } QLabel#pageTitle { font-size:20px; font-weight:700; color:#0f172a; }
          QLabel#muted { color:#64748b; } QPushButton { background:#e2e8f0; border:0; border-radius:6px; padding:8px 11px; }
          QPushButton:hover { background:#cbd5e1; } QPushButton#primary { background:#2563eb; color:white; font-weight:700; }
          QPushButton#primary:hover { background:#1d4ed8; } QTextEdit, QLineEdit, QTreeWidget, QComboBox { background:white; border:1px solid #cbd5e1; border-radius:6px; padding:5px; }
          QTreeWidget::item { height:30px; } QHeaderView::section { background:#e2e8f0; border:0; padding:7px; font-weight:700; }
        """)

    def _queue_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 14)
        header = QFrame(); header.setObjectName("header"); h = QHBoxLayout(header); h.setContentsMargins(18, 11, 18, 11)
        brand = QLabel("ControlApps"); brand.setObjectName("brand")
        h.addWidget(brand); h.addWidget(QLabel("  DESCARGADOR")); h.addStretch()
        search = QPushButton("Buscar YouTube"); search.clicked.connect(self._search_dialog); h.addWidget(search)
        settings = QPushButton("Configuracion"); settings.clicked.connect(self._settings); h.addWidget(settings)
        layout.addWidget(header)
        body = QVBoxLayout(); body.setContentsMargins(16, 14, 16, 0)
        title = QLabel("Nueva descarga"); title.setObjectName("pageTitle"); body.addWidget(title)
        hint = QLabel("Pega uno o varios enlaces. Elige video o audio y agrega a la cola."); hint.setObjectName("muted"); body.addWidget(hint)
        self.urls = QTextEdit(); self.urls.setPlaceholderText("https://youtube.com/...\nhttps://instagram.com/reel/..."); self.urls.setFixedHeight(85); body.addWidget(self.urls)
        body.addWidget(self.crop_page)
        row = QHBoxLayout(); self.mode = QComboBox(); self.mode.addItems(["Video completo", "Audio original (recomendado)", "MP3 320 kbps"])
        self.mode.setCurrentIndex({"video":0,"original":1,"mp3":2}.get(self.modo,0)); self.mode.currentIndexChanged.connect(self._mode_changed)
        paste = QPushButton("Pegar enlace"); paste.clicked.connect(self._paste)
        folder = QPushButton("Carpeta destino"); folder.clicked.connect(self._folder)
        self.download_btn = QPushButton("Agregar a la cola"); self.download_btn.setObjectName("primary"); self.download_btn.clicked.connect(self._add_urls)
        row.addWidget(self.mode); row.addWidget(paste); row.addWidget(folder); row.addStretch(); row.addWidget(self.download_btn); body.addLayout(row)
        self.folder_label = QLabel(self.carpeta or "Elegí una carpeta destino antes de descargar"); self.folder_label.setObjectName("muted"); body.addWidget(self.folder_label)
        qtitle = QLabel("Cola de descargas"); qtitle.setObjectName("pageTitle"); body.addWidget(qtitle)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Nombre", "Tamaño", "Progreso", "Estado"]); self.tree.setColumnWidth(0, 430); body.addWidget(self.tree, 1)
        actions = QHBoxLayout(); self.play_button = QPushButton("Reanudar descargas"); self.play_button.setObjectName("primary"); self.play_button.clicked.connect(self._toggle)
        retry = QPushButton("Reintentar fallidas"); retry.clicked.connect(self._retry)
        remove = QPushButton("Quitar seleccion"); remove.clicked.connect(self._remove)
        crop = QPushButton("Recortar video"); crop.clicked.connect(self._crop)
        open_folder = QPushButton("Abrir carpeta"); open_folder.clicked.connect(self._open_folder)
        for x in (self.play_button,retry,remove,crop,open_folder): actions.addWidget(x)
        actions.addStretch(); body.addLayout(actions)
        self.summary = QLabel("Sin descargas en cola"); self.summary.setObjectName("muted"); body.addWidget(self.summary)
        layout.addLayout(body, 1); return page

    def _mode_changed(self, index):
        self.modo = ("video", "original", "mp3")[index]; self._save()

    def _save(self):
        _guardar_config({"carpeta":self.carpeta,"conexiones":self.conexiones,"auto_iniciar":self.auto_iniciar,
                          "abrir_al_finalizar":self.abrir_al_finalizar,"modo_descarga":self.modo,
                          "actualizar_automaticamente":self.cfg.get("actualizar_automaticamente",True)})

    def _paste(self):
        self.urls.setPlainText(QApplication.clipboard().text())

    def _inspect_link(self):
        links = parse_links(self.urls.toPlainText())
        url = links[0] if links else None
        if not url or url == self._preview_url:
            return
        self._preview_url = url
        self.crop_page.show_thumbnail(url)

    def _folder(self):
        path = QFileDialog.getExistingDirectory(self, "Carpeta destino", self.carpeta or "")
        if path: self.carpeta=path; self.folder_label.setText(path); self._save()

    def _add_urls(self):
        if not self.carpeta: QMessageBox.warning(self,"Falta carpeta","Elegí primero una carpeta destino."); return
        added=0
        for url in sort_by_part(parse_links(self.urls.toPlainText())):
            resolver=get_resolver(url); name=resolver.filename(url) if resolver else url.rsplit("/",1)[-1]
            if self.state.add(url,name,self.carpeta,audio_format="" if self.modo=="video" else self.modo): added += 1
        self.urls.clear(); self.state.save(); self._refresh()
        if added and self.auto_iniciar: self.pausado.clear(); self._start()

    def add_clip(self,url,start,end):
        resolver=get_resolver(url); name=f"{resolver.filename(url)}_{_tiempo_humano(start).replace(':','-')}-{_tiempo_humano(end).replace(':','-')}"
        if self.state.add(url,name,self.carpeta,clip={"inicio":start,"fin":end}): self.state.save(); self._refresh()

    def _crop(self):
        if not self.carpeta: QMessageBox.warning(self,"Falta carpeta","Elegí primero una carpeta destino."); return
        urls=parse_links(self.urls.toPlainText()); url=urls[0] if urls else (self.tree.currentItem().data(0,Qt.UserRole) if self.tree.currentItem() else None)
        if not url: QMessageBox.information(self,"Elegí un video","Pega o selecciona un enlace de YouTube o Instagram."); return
        self.crop_page.show()
        self.crop_page.open_for(url)

    def show_queue(self): self.stack.setCurrentWidget(self.queue_page); self._refresh()

    def _refresh(self):
        self.tree.clear()
        for it in self.state.items:
            name=it.nombre + (f"  [{_tiempo_humano(it.clip['inicio'])} - {_tiempo_humano(it.clip['fin'])}]" if it.clip else "")
            pct=int(it.bytes_bajados*100/it.total) if it.total else 0
            item=QTreeWidgetItem([name, str(it.total or "?"), f"{pct}%", it.estado]); item.setData(0,Qt.UserRole,it.url); self.tree.addTopLevelItem(item)
        counts={s:sum(i.estado==s for i in self.state.items) for s in ("pendiente","descargando","completo","fallido")}
        self.summary.setText(" · ".join(f"{n} {s}" for s,n in counts.items() if n) or "Sin descargas en cola")

    def _drain(self):
        changed=False
        try:
            while True: self.events.get_nowait(); changed=True
        except queue.Empty: pass
        if changed: self.state.save(); self._refresh()

    def _toggle(self):
        if self.pausado.is_set(): self.pausado.clear(); self.play_button.setText("Pausar descargas"); self._start()
        else: self.pausado.set(); self.play_button.setText("Reanudar descargas")

    def _start(self):
        if self.worker and self.worker.is_alive(): return
        self.worker=threading.Thread(target=lambda:self.engine.run_queue(self.state.items),daemon=True); self.worker.start()

    def _retry(self):
        for it in self.state.items:
            if it.estado=="fallido": it.estado="pendiente"
        self.state.save(); self._refresh()

    def _remove(self):
        selected={x.data(0,Qt.UserRole) for x in self.tree.selectedItems()}; self.state.items[:]=[i for i in self.state.items if i.url not in selected]; self.state.save(); self._refresh()

    def _open_folder(self):
        if self.carpeta and os.path.isdir(self.carpeta): abrir_ruta(self.carpeta)

    def _settings(self):
        dialog=QDialog(self); dialog.setWindowTitle("Configuracion"); form=QFormLayout(dialog)
        con=QSpinBox(); con.setRange(1,8); con.setValue(self.conexiones)
        auto=QComboBox(); auto.addItems(["Manual", "Iniciar automaticamente"]); auto.setCurrentIndex(1 if self.auto_iniciar else 0)
        form.addRow("Conexiones por descarga",con); form.addRow("Al agregar enlaces",auto)
        save=QPushButton("Guardar"); form.addRow(save)
        def done(): self.conexiones=con.value(); self.auto_iniciar=auto.currentIndex()==1; self._save(); dialog.accept()
        save.clicked.connect(done); dialog.exec()

    def _search_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle("Buscar en YouTube"); layout=QVBoxLayout(dialog)
        query=QLineEdit(); query.setPlaceholderText("Que querés descargar?"); layout.addWidget(query)
        results=QTreeWidget(); results.setHeaderLabels(["Titulo","Canal","Duracion"]); layout.addWidget(results)
        status=QLabel("Escribe una busqueda y presiona Buscar."); layout.addWidget(status)
        buttons=QHBoxLayout(); find=QPushButton("Buscar"); add=QPushButton("Agregar a la cola"); buttons.addWidget(find); buttons.addWidget(add); layout.addLayout(buttons)
        data=[]
        def search():
            status.setText("Buscando...")
            def job():
                try: self.crop_page.signals.search_ready.emit(buscar_youtube(query.text()))
                except Exception: self.crop_page.signals.search_ready.emit([])
            threading.Thread(target=job,daemon=True).start()
        def show(items):
            nonlocal data; data=items; results.clear()
            for x in data: results.addTopLevelItem(QTreeWidgetItem([x['title'],x['channel'],_tiempo_humano(x['duration'])]))
            status.setText(f"{len(data)} resultados")
        self.crop_page.signals.search_ready.connect(show)
        def choose():
            if results.currentIndex().row() >= 0:
                self.urls.setPlainText(data[results.currentIndex().row()]["url"]); dialog.accept()
        find.clicked.connect(search); query.returnPressed.connect(search); add.clicked.connect(choose); dialog.exec()


def main():
    app=QApplication(sys.argv)
    window=DescargadorQt(); window.show()
    return app.exec()
