import os
import queue
import threading
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .state import State
from .engine import Engine
from .downloader import download
from .browser import resolve_with_browser
from .resolvers import get_resolver
from .links import parse_links, sort_by_part
from .format import humano, bar

CARPETA_APP = os.path.join(os.path.expanduser("~"), ".descargador")
os.makedirs(CARPETA_APP, exist_ok=True)
ESTADO = os.path.join(CARPETA_APP, "estado.json")
CONFIG = os.path.join(CARPETA_APP, "config.json")


def _cargar_carpeta_destino():
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f).get("carpeta", "")
    return ""


def _guardar_carpeta_destino(carpeta):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"carpeta": carpeta}, f, ensure_ascii=False)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Descargador")
        self.root.geometry("760x460")

        self.state = State(ESTADO)
        self.state.load()
        self.carpeta = _cargar_carpeta_destino()
        self.cola_ui = queue.Queue()
        self.pausado = threading.Event()  # set = pausado
        self.pausado.set()  # arranca en pausa hasta que el usuario le da play
        self.worker = None

        self.engine = Engine(
            get_resolver=get_resolver,
            download_fn=download,
            browser_resolve=resolve_with_browser,
            on_update=lambda item: self.cola_ui.put(item),
            should_pause=lambda: self.pausado.is_set(),
        )

        self._construir_ui()
        self._refrescar_tabla()
        self.root.after(200, self._drenar_cola)

    def _construir_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        self.txt = tk.Text(top, height=4, width=70)
        self.txt.grid(row=0, column=0, columnspan=4, sticky="we")
        ttk.Button(top, text="Agregar", command=self._agregar_pegados).grid(row=1, column=0, pady=4, sticky="w")
        ttk.Button(top, text="Cargar .txt", command=self._cargar_txt).grid(row=1, column=1, pady=4, sticky="w")
        ttk.Button(top, text="Elegir carpeta", command=self._elegir_carpeta).grid(row=1, column=2, pady=4, sticky="w")
        self.lbl_carpeta = ttk.Label(top, text=self.carpeta or "(sin carpeta)")
        self.lbl_carpeta.grid(row=1, column=3, pady=4, sticky="w")

        cols = ("nombre", "tam", "prog", "estado")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=12)
        for c, t, w in (("nombre", "Nombre", 300), ("tam", "Tamaño", 90),
                        ("prog", "Progreso", 200), ("estado", "Estado", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=8)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.btn_play = ttk.Button(bottom, text="Reanudar", command=self._toggle_pausa)
        self.btn_play.pack(side="left")
        ttk.Button(bottom, text="Reintentar fallidos", command=self._reintentar).pack(side="left", padx=6)
        ttk.Button(bottom, text="Abrir carpeta", command=self._abrir_carpeta).pack(side="left")

    def _agregar_links(self, urls):
        if not self.carpeta:
            messagebox.showwarning("Falta carpeta", "Elegi primero una carpeta destino.")
            return
        for url in sort_by_part(urls):
            r = get_resolver(url)
            nombre = r.filename(url) if r else url.rstrip("/").split("/")[-1]
            self.state.add(url, nombre, self.carpeta)
        self.state.save()
        self._refrescar_tabla()

    def _agregar_pegados(self):
        urls = parse_links(self.txt.get("1.0", "end"))
        self.txt.delete("1.0", "end")
        self._agregar_links(urls)

    def _cargar_txt(self):
        ruta = filedialog.askopenfilename(filetypes=[("Texto", "*.txt")])
        if not ruta:
            return
        with open(ruta, encoding="utf-8") as f:
            self._agregar_links(parse_links(f.read()))

    def _elegir_carpeta(self):
        c = filedialog.askdirectory()
        if c:
            self.carpeta = c
            _guardar_carpeta_destino(c)
            self.lbl_carpeta.config(text=c)

    def _toggle_pausa(self):
        if self.pausado.is_set():
            self.pausado.clear()
            self.btn_play.config(text="Pausar")
            self._arrancar_worker()
        else:
            self.pausado.set()
            self.btn_play.config(text="Reanudar")

    def _arrancar_worker(self):
        if self.worker and self.worker.is_alive():
            return

        def correr():
            motivo = self.engine.run_queue(self.state.items)
            self.state.save()
            if motivo == "disco_lleno":
                self.pausado.set()
                self.root.after(0, self._aviso_disco_lleno)

        self.worker = threading.Thread(target=correr, daemon=True)
        self.worker.start()

    def _aviso_disco_lleno(self):
        self.btn_play.config(text="Reanudar")
        messagebox.showwarning("Disco lleno", "No hay espacio en disco. Libera espacio y despues reanuda.")

    def _reintentar(self):
        for it in self.state.items:
            if it.estado == "fallido":
                it.estado = "pendiente"
        self.state.save()
        self._refrescar_tabla()
        if not self.pausado.is_set():
            self._arrancar_worker()

    def _abrir_carpeta(self):
        if self.carpeta and os.path.isdir(self.carpeta):
            os.startfile(self.carpeta)  # Windows

    def _fila(self, it):
        pct = int(it.bytes_bajados * 100 / it.total) if it.total else 0
        return (it.nombre, humano(it.total) if it.total else "?",
                f"{bar(pct)} {pct}%", it.estado)

    def _refrescar_tabla(self):
        self.tree.delete(*self.tree.get_children())
        for it in self.state.items:
            self.tree.insert("", "end", iid=it.url, values=self._fila(it))

    def _drenar_cola(self):
        cambiado = False
        try:
            while True:
                it = self.cola_ui.get_nowait()
                if self.tree.exists(it.url):
                    self.tree.item(it.url, values=self._fila(it))
                cambiado = True
        except queue.Empty:
            pass
        if cambiado:
            self.state.save()
        self.root.after(200, self._drenar_cola)
