import os
import queue
import threading
import json
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .state import State
from .engine import Engine
from .downloader import download
from .browser import resolve_with_browser
from .resolvers import get_resolver
from .links import parse_links, sort_by_part, agrupar
from .format import humano, bar, velocidad_ema

CARPETA_APP = os.path.join(os.path.expanduser("~"), ".descargador")
os.makedirs(CARPETA_APP, exist_ok=True)
ESTADO = os.path.join(CARPETA_APP, "estado.json")
CONFIG = os.path.join(CARPETA_APP, "config.json")


CONEXIONES_OPCIONES = ("1", "2", "4", "8")
CONEXIONES_DEFAULT = 4
GRP_PREFIX = "grp:"


def _cargar_config():
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, ValueError):
            return {}
    return {}


def _guardar_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Descargador")
        self.root.geometry("760x460")

        self.state = State(ESTADO)
        self.state.load()
        cfg = _cargar_config()
        self.carpeta = cfg.get("carpeta", "")
        self.conexiones = cfg.get("conexiones", CONEXIONES_DEFAULT)
        self.cola_ui = queue.Queue()
        self._vel = {}  # url -> {"ts":, "bytes":, "ema":} para velocidad en vivo
        self.pausado = threading.Event()  # set = pausado
        self.pausado.set()  # arranca en pausa hasta que el usuario le da play
        self.worker = None
        self._todo_abierto = True

        self.engine = Engine(
            get_resolver=get_resolver,
            download_fn=download,
            browser_resolve=resolve_with_browser,
            on_update=lambda item: self.cola_ui.put(item),
            should_pause=lambda: self.pausado.is_set(),
            get_conexiones=lambda: self.conexiones,
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

        ttk.Label(top, text="Conexiones por descarga:").grid(row=2, column=0, columnspan=2, pady=4, sticky="w")
        self.cmb_conex = ttk.Combobox(top, width=4, state="readonly", values=CONEXIONES_OPCIONES)
        self.cmb_conex.set(str(self.conexiones))
        self.cmb_conex.grid(row=2, column=1, pady=4, sticky="e")
        self.cmb_conex.bind("<<ComboboxSelected>>", self._cambiar_conexiones)

        cols = ("nombre", "tam", "prog", "estado")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=12)
        for c, t, w in (("nombre", "Nombre", 300), ("tam", "Tamaño", 90),
                        ("prog", "Progreso", 200), ("estado", "Estado", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<Delete>", lambda e: self._quitar_seleccionados())

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.btn_play = ttk.Button(bottom, text="Reanudar", command=self._toggle_pausa)
        self.btn_play.pack(side="left")
        ttk.Button(bottom, text="Reintentar fallidos", command=self._reintentar).pack(side="left", padx=6)
        ttk.Button(bottom, text="Quitar", command=self._quitar_seleccionados).pack(side="left")
        ttk.Button(bottom, text="Abrir carpeta", command=self._abrir_carpeta).pack(side="left", padx=6)

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
            cfg = _cargar_config()
            cfg["carpeta"] = c
            _guardar_config(cfg)
            self.lbl_carpeta.config(text=c)

    def _cambiar_conexiones(self, event=None):
        try:
            self.conexiones = int(self.cmb_conex.get())
        except ValueError:
            self.conexiones = CONEXIONES_DEFAULT
        cfg = _cargar_config()
        cfg["conexiones"] = self.conexiones
        _guardar_config(cfg)

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

    def _quitar_seleccionados(self):
        sel = self.tree.selection()  # los iid son las urls
        if not sel:
            return
        urls = set(sel)
        activos = [it.url for it in self.state.items
                   if it.url in urls and it.estado == "descargando"]
        if activos:
            messagebox.showwarning(
                "Descarga en curso",
                "Pausa la descarga antes de quitar el archivo que se esta bajando.")
            urls -= set(activos)  # quitamos el resto igual
            if not urls:
                return
        # Mutamos la lista in place (no reasignar) para que el worker en curso
        # vea la baja via la referencia que ya tiene.
        self.state.items[:] = [it for it in self.state.items if it.url not in urls]
        self.state.save()
        self._refrescar_tabla()

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
        prog = f"{bar(pct)} {pct}%"
        vel = self._vel.get(it.url, {}).get("ema") if it.estado == "descargando" else None
        if vel:
            prog += f" · {humano(vel)}/s"
        return (it.nombre, humano(it.total) if it.total else "?",
                prog, it.estado)

    def _actualizar_velocidad(self, it):
        if it.estado != "descargando":
            self._vel.pop(it.url, None)
            return None
        ahora = time.time()
        prev = self._vel.get(it.url)
        if prev is None:
            ema = None
        else:
            ema = velocidad_ema(prev["ts"], prev["bytes"], prev["ema"],
                                 ahora, it.bytes_bajados)
        self._vel[it.url] = {"ts": ahora, "bytes": it.bytes_bajados, "ema": ema}
        return ema

    def _refrescar_tabla(self):
        abiertos = {iid: self.tree.item(iid, "open") for iid in self.tree.get_children("")}
        self.tree.delete(*self.tree.get_children())
        for key, items in agrupar(self.state.items):
            gid = GRP_PREFIX + key
            completos = sum(1 for it in items if it.estado == "completo")
            tam_grupo = sum(it.total for it in items if it.total)
            texto = f"{key}  ({completos}/{len(items)} completos)"
            self.tree.insert("", "end", iid=gid,
                              values=(texto, humano(tam_grupo) if tam_grupo else "?", "", ""),
                              open=abiertos.get(gid, self._todo_abierto))
            for it in items:
                self.tree.insert(gid, "end", iid=it.url, values=self._fila(it))

    def _drenar_cola(self):
        cambiado = False
        try:
            while True:
                it = self.cola_ui.get_nowait()
                vel = self._actualizar_velocidad(it)
                if self.tree.exists(it.url):
                    self.tree.item(it.url, values=self._fila(it, vel))
                cambiado = True
        except queue.Empty:
            pass
        if cambiado:
            self.state.save()
        self.root.after(200, self._drenar_cola)
