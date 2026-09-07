import os
import queue
import threading
import json
import time
import tkinter as tk
import webbrowser
from tkinter import ttk, filedialog, messagebox

from .state import State
from .engine import Engine
from .downloader import download
from .browser import resolve_with_browser
from .resolvers import get_resolver
from .links import parse_links, sort_by_part, agrupar
from .format import humano, bar, velocidad_ema
from .system import abrir_ruta
from .updater import aplicar_actualizacion, buscar_actualizacion, descargar_actualizacion
from .version import APP_VERSION

CARPETA_APP = os.path.join(os.path.expanduser("~"), ".descargador")
os.makedirs(CARPETA_APP, exist_ok=True)
ESTADO = os.path.join(CARPETA_APP, "estado.json")
CONFIG = os.path.join(CARPETA_APP, "config.json")


CONEXIONES_OPCIONES = ("1", "2", "4", "8")
CONEXIONES_DEFAULT = 4
GRP_PREFIX = "grp:"


def _tiempo_segundos(texto):
    """Convierte MM:SS, HH:MM:SS o segundos a segundos enteros."""
    partes = texto.strip().split(":")
    try:
        numeros = [int(p) for p in partes]
    except ValueError as exc:
        raise ValueError("Usa segundos, MM:SS o HH:MM:SS") from exc
    if len(numeros) == 1:
        return numeros[0]
    if len(numeros) == 2:
        return numeros[0] * 60 + numeros[1]
    if len(numeros) == 3:
        return numeros[0] * 3600 + numeros[1] * 60 + numeros[2]
    raise ValueError("Usa segundos, MM:SS o HH:MM:SS")


def _tiempo_humano(segundos):
    segundos = max(0, int(segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}" if horas else f"{minutos:02}:{segundos:02}"


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
        self.root.title("ControlApps · Descargador")
        self.root.geometry("760x460")

        self.state = State(ESTADO)
        self.state.load()
        cfg = _cargar_config()
        self.carpeta = cfg.get("carpeta", "")
        self.conexiones = cfg.get("conexiones", CONEXIONES_DEFAULT)
        self.auto_iniciar = cfg.get("auto_iniciar", False)
        self.abrir_al_finalizar = cfg.get("abrir_al_finalizar", False)
        self.actualizar_automaticamente = cfg.get("actualizar_automaticamente", True)
        self._buscando_actualizacion = False
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
        self.root.geometry("960x590")
        self.root.minsize(820, 480)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Brand.TFrame", background="#0f172a")
        style.configure("BrandTitle.TLabel", background="#0f172a", foreground="#f8fafc",
                        font=("Segoe UI", 16, "bold"))
        style.configure("BrandSub.TLabel", background="#0f172a", foreground="#94a3b8",
                        font=("Segoe UI", 9))
        style.configure("Brand.TButton", font=("Segoe UI", 9, "bold"))

        brand = ttk.Frame(self.root, style="Brand.TFrame", padding=(14, 10))
        brand.pack(fill="x")
        ttk.Label(brand, text="ControlApps", style="BrandTitle.TLabel").pack(side="left")
        ttk.Label(brand, text="DESCARGADOR  ·  archivos y redes sociales",
                  style="BrandSub.TLabel").pack(side="left", padx=(12, 0), pady=(5, 0))
        ttk.Button(brand, text="Configuracion", style="Brand.TButton",
                   command=self._abrir_configuracion).pack(side="right")
        ttk.Button(brand, text="Actualizar", style="Brand.TButton",
                   command=lambda: self._buscar_actualizacion(True)).pack(side="right", padx=(0, 6))

        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Pegá uno o varios enlaces para agregarlos a la cola").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 4)
        )
        self.txt = tk.Text(top, height=3, width=70, wrap="word")
        self.txt.grid(row=1, column=0, columnspan=5, sticky="we")
        self.txt.bind("<Control-Return>", self._atajo_agregar)
        ttk.Button(top, text="Agregar a la cola", command=self._agregar_pegados).grid(row=2, column=0, pady=6, sticky="w")
        ttk.Button(top, text="Pegar y agregar", command=self._pegar_y_agregar).grid(row=2, column=1, pady=6, padx=(6, 0), sticky="w")
        ttk.Button(top, text="Recortar video", command=self._abrir_recorte).grid(row=2, column=2, pady=6, padx=(6, 0), sticky="w")
        ttk.Button(top, text="Cargar .txt", command=self._cargar_txt).grid(row=2, column=3, pady=6, padx=(6, 0), sticky="w")
        ttk.Button(top, text="Elegir carpeta", command=self._elegir_carpeta).grid(row=2, column=4, pady=6, padx=(6, 0), sticky="w")
        self.lbl_carpeta = ttk.Label(top, text=self.carpeta or "(sin carpeta)")
        self.lbl_carpeta.grid(row=2, column=5, pady=6, padx=(8, 0), sticky="w")

        ttk.Label(top, text="Conexiones por descarga:").grid(row=3, column=0, columnspan=2, pady=(0, 2), sticky="w")
        self.cmb_conex = ttk.Combobox(top, width=4, state="readonly", values=CONEXIONES_OPCIONES)
        self.cmb_conex.set(str(self.conexiones))
        self.cmb_conex.grid(row=3, column=1, pady=(0, 2), sticky="e")
        self.cmb_conex.bind("<<ComboboxSelected>>", self._cambiar_conexiones)
        ttk.Label(top, text="Atajo: Ctrl + Enter agrega los enlaces escritos.").grid(
            row=3, column=2, columnspan=3, padx=(12, 0), sticky="w"
        )
        top.columnconfigure(4, weight=1)
        self.root.after(1500, self._buscar_actualizacion)

        cols = ("tam", "prog", "estado")
        self.tree = ttk.Treeview(self.root, columns=cols, show="tree headings", height=14)
        self.tree.heading("#0", text="Nombre")
        self.tree.column("#0", width=300)
        for c, t, w in (("tam", "Tamaño", 90),
                        ("prog", "Progreso", 200), ("estado", "Estado", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<Delete>", lambda e: self._quitar_seleccionados())
        self.tree.bind("<Control-a>", self._seleccionar_todo)
        self.tree.bind("<Button-3>", self._mostrar_menu)
        self.tree.tag_configure("pendiente", foreground="#6b7280")
        self.tree.tag_configure("descargando", foreground="#0369a1")
        self.tree.tag_configure("completo", foreground="#15803d")
        self.tree.tag_configure("pausado", foreground="#b45309")
        self.tree.tag_configure("fallido", foreground="#b91c1c")

        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="Abrir archivo", command=self._abrir_seleccionado)
        self.menu.add_command(label="Reintentar seleccionados", command=self._reintentar_seleccionados)
        self.menu.add_command(label="Copiar enlaces", command=self._copiar_enlaces)
        self.menu.add_separator()
        self.menu.add_command(label="Quitar de la cola", command=self._quitar_seleccionados)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.btn_play = ttk.Button(bottom, text="Reanudar", command=self._toggle_pausa)
        self.btn_play.grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Reintentar fallidos", command=self._reintentar).grid(row=0, column=1, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Reintentar selección", command=self._reintentar_seleccionados).grid(row=0, column=2, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Quitar", command=self._quitar_seleccionados).grid(row=0, column=3, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Limpiar completos", command=self._limpiar_completos).grid(row=0, column=4, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Abrir archivo", command=self._abrir_seleccionado).grid(row=0, column=5, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Abrir carpeta", command=self._abrir_carpeta).grid(row=0, column=6, padx=(6, 0), sticky="w")
        self.btn_colapsar = ttk.Button(bottom, text="Colapsar todo", command=self._toggle_colapso)
        self.btn_colapsar.grid(row=0, column=7, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Seleccionar todo", command=self._seleccionar_todo).grid(row=0, column=8, padx=(6, 0), sticky="w")

        self.lbl_resumen = ttk.Label(bottom, text="Sin descargas en cola")
        self.lbl_resumen.grid(row=1, column=0, columnspan=5, pady=(8, 0), sticky="w")
        self.progreso_global = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progreso_global.grid(row=1, column=5, columnspan=4, padx=(10, 0), pady=(8, 0), sticky="ew")
        bottom.columnconfigure(8, weight=1)

    def _agregar_links(self, urls):
        if not self.carpeta:
            messagebox.showwarning("Falta carpeta", "Elegi primero una carpeta destino.")
            return
        agregados = 0
        for url in sort_by_part(urls):
            r = get_resolver(url)
            nombre = r.filename(url) if r else url.rstrip("/").split("/")[-1]
            if self.state.add(url, nombre, self.carpeta):
                agregados += 1
        self.state.save()
        self._refrescar_tabla()
        if agregados and self.auto_iniciar:
            self.pausado.clear()
            self.btn_play.config(text="Pausar")
            self._arrancar_worker()

    def _agregar_pegados(self):
        urls = parse_links(self.txt.get("1.0", "end"))
        self.txt.delete("1.0", "end")
        self._agregar_links(urls)

    def _atajo_agregar(self, event=None):
        self._agregar_pegados()
        return "break"

    def _pegar_y_agregar(self):
        try:
            texto = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Portapapeles vacio", "No hay enlaces para pegar.")
            return
        urls = parse_links(texto)
        if not urls:
            messagebox.showinfo("Sin enlaces", "El portapapeles no contiene enlaces HTTP validos.")
            return
        self._agregar_links(urls)

    def _url_para_recortar(self):
        urls = parse_links(self.txt.get("1.0", "end"))
        if urls:
            return urls[0]
        seleccion = self._items_seleccionados()
        return seleccion[0].url if seleccion else None

    def _abrir_recorte(self):
        if not self.carpeta:
            messagebox.showwarning("Falta carpeta", "Elegi primero una carpeta destino.")
            return
        url = self._url_para_recortar()
        resolver = get_resolver(url) if url else None
        if not url or resolver is None or resolver.__class__.__name__ not in {"YouTubeResolver", "InstagramResolver"}:
            messagebox.showinfo("Video no identificado", "Pega o selecciona un enlace de YouTube o Instagram para recortarlo.")
            return

        ventana = tk.Toplevel(self.root)
        ventana.title("ControlApps · Recortar video")
        ventana.transient(self.root)
        ventana.geometry("560x330")
        ventana.resizable(False, False)
        frame = ttk.Frame(ventana, padding=18)
        frame.pack(fill="both", expand=True)
        titulo = tk.StringVar(value="Analizando video...")
        duracion = tk.IntVar(value=0)
        inicio = tk.IntVar(value=0)
        fin = tk.IntVar(value=0)
        inicio_texto = tk.StringVar(value="00:00")
        fin_texto = tk.StringVar(value="00:00")

        ttk.Label(frame, text="Recortar video", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=titulo, wraplength=510).pack(anchor="w", pady=(4, 14))
        estado = ttk.Label(frame, text="Buscando duracion y titulo...")
        estado.pack(anchor="w")

        controles = ttk.Frame(frame)
        controles.pack(fill="x", pady=(10, 0))
        ttk.Label(controles, text="Inicio").grid(row=0, column=0, sticky="w")
        ttk.Entry(controles, textvariable=inicio_texto, width=10).grid(row=0, column=1, padx=(6, 22), sticky="w")
        ttk.Label(controles, text="Fin").grid(row=0, column=2, sticky="w")
        ttk.Entry(controles, textvariable=fin_texto, width=10).grid(row=0, column=3, padx=(6, 0), sticky="w")
        escala_inicio = ttk.Scale(frame, orient="horizontal", from_=0, to=1, variable=inicio)
        escala_fin = ttk.Scale(frame, orient="horizontal", from_=0, to=1, variable=fin)
        ttk.Label(frame, text="Marcador de inicio").pack(anchor="w", pady=(14, 0))
        escala_inicio.pack(fill="x")
        ttk.Label(frame, text="Marcador de fin").pack(anchor="w", pady=(8, 0))
        escala_fin.pack(fill="x")

        acciones = ttk.Frame(frame)
        acciones.pack(fill="x", pady=(18, 0))

        def sincronizar_desde_escala(*_):
            inicio_texto.set(_tiempo_humano(inicio.get()))
            fin_texto.set(_tiempo_humano(fin.get()))

        inicio.trace_add("write", sincronizar_desde_escala)
        fin.trace_add("write", sincronizar_desde_escala)

        def aplicar_tiempos():
            try:
                inicio.set(_tiempo_segundos(inicio_texto.get()))
                fin.set(_tiempo_segundos(fin_texto.get()))
            except ValueError as exc:
                messagebox.showwarning("Tiempo invalido", str(exc), parent=ventana)

        def preset(segundos):
            inicio.set(0)
            fin.set(min(segundos, duracion.get()))

        def preescuchar():
            aplicar_tiempos()
            separador = "&" if "?" in url else "?"
            webbrowser.open(url + f"{separador}t={inicio.get()}")

        def agregar_recorte():
            aplicar_tiempos()
            if not duracion.get() or inicio.get() < 0 or fin.get() <= inicio.get() or fin.get() > duracion.get():
                messagebox.showwarning("Rango invalido", "El fin debe ser posterior al inicio y estar dentro del video.", parent=ventana)
                return
            nombre = f"{resolver.filename(url)}_{_tiempo_humano(inicio.get()).replace(':', '-')}-{_tiempo_humano(fin.get()).replace(':', '-')}"
            clip = {"inicio": inicio.get(), "fin": fin.get()}
            if self.state.add(url, nombre, self.carpeta, clip=clip):
                self.state.save()
                self._refrescar_tabla()
                if self.auto_iniciar:
                    self.pausado.clear()
                    self.btn_play.config(text="Pausar")
                    self._arrancar_worker()
            ventana.destroy()

        ttk.Button(acciones, text="Primeros 30 s", command=lambda: preset(30)).pack(side="left")
        ttk.Button(acciones, text="Primer minuto", command=lambda: preset(60)).pack(side="left", padx=(6, 0))
        ttk.Button(acciones, text="Preescuchar desde inicio", command=preescuchar).pack(side="left", padx=(14, 0))
        btn_agregar = ttk.Button(acciones, text="Agregar recorte", command=agregar_recorte, state="disabled")
        btn_agregar.pack(side="right")

        def cargar_info():
            try:
                import yt_dlp
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                nombre_video = info.get("title") or "Video sin titulo"
                segundos = int(info.get("duration") or 0)
                if not segundos:
                    raise ValueError("No se pudo conocer la duracion del video")
                self.root.after(0, lambda: listo(nombre_video, segundos))
            except Exception as exc:
                self.root.after(0, lambda: fallo(str(exc)))

        def listo(nombre_video, segundos):
            titulo.set(nombre_video)
            duracion.set(segundos)
            fin.set(segundos)
            escala_inicio.configure(to=segundos)
            escala_fin.configure(to=segundos)
            estado.config(text=f"Duracion: {_tiempo_humano(segundos)}. Elegi el rango que queres descargar.")
            btn_agregar.config(state="normal")

        def fallo(error):
            titulo.set("No se pudo analizar este video")
            estado.config(text="Revisa que el enlace sea publico y volve a intentarlo.")

        threading.Thread(target=cargar_info, daemon=True).start()

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
            self._guardar_preferencias()
            self.lbl_carpeta.config(text=c)

    def _cambiar_conexiones(self, event=None):
        try:
            self.conexiones = int(self.cmb_conex.get())
        except ValueError:
            self.conexiones = CONEXIONES_DEFAULT
        self._guardar_preferencias()

    def _guardar_preferencias(self):
        _guardar_config({
            "carpeta": self.carpeta,
            "conexiones": self.conexiones,
            "auto_iniciar": self.auto_iniciar,
            "abrir_al_finalizar": self.abrir_al_finalizar,
            "actualizar_automaticamente": self.actualizar_automaticamente,
        })

    def _buscar_actualizacion(self, manual=False):
        if self._buscando_actualizacion or (not manual and not self.actualizar_automaticamente):
            return
        self._buscando_actualizacion = True

        def trabajo():
            try:
                update = buscar_actualizacion()
                self.root.after(0, lambda: listo(update))
            except Exception:
                self.root.after(0, lambda: listo(None, True))

        def listo(update, error=False):
            self._buscando_actualizacion = False
            if not update:
                if manual:
                    messagebox.showinfo("Actualizaciones", "No hay una actualizacion disponible." if not error else "No se pudo consultar GitHub.")
                return
            self._descargar_actualizacion(update)

        threading.Thread(target=trabajo, daemon=True).start()

    def _descargar_actualizacion(self, update):
        def trabajo():
            try:
                archivo = descargar_actualizacion(update)
                self.root.after(0, lambda: listo(archivo))
            except Exception:
                self.root.after(0, fallo)

        def listo(archivo):
            messagebox.showinfo("Actualizando", f"Se instalara ControlApps Descargador v{update['version']} al cerrar.")
            aplicar_actualizacion(archivo)
            self.root.destroy()

        def fallo():
            messagebox.showwarning("Actualizacion fallida", "No se pudo descargar o verificar la actualizacion.")

        threading.Thread(target=trabajo, daemon=True).start()

    def _abrir_configuracion(self):
        ventana = tk.Toplevel(self.root)
        ventana.title("ControlApps · Configuracion")
        ventana.transient(self.root)
        ventana.resizable(False, False)
        ventana.grab_set()

        frame = ttk.Frame(ventana, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Preferencias de descarga", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )

        carpeta = tk.StringVar(value=self.carpeta)
        conexiones = tk.StringVar(value=str(self.conexiones))
        auto_iniciar = tk.BooleanVar(value=self.auto_iniciar)
        abrir_al_finalizar = tk.BooleanVar(value=self.abrir_al_finalizar)

        ttk.Label(frame, text="Carpeta predeterminada").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=carpeta, width=48).grid(row=2, column=0, columnspan=2, pady=(3, 10), sticky="we")

        def elegir_en_config():
            seleccion = filedialog.askdirectory(parent=ventana, initialdir=carpeta.get() or None)
            if seleccion:
                carpeta.set(seleccion)

        ttk.Button(frame, text="Elegir...", command=elegir_en_config).grid(row=2, column=2, padx=(6, 0), pady=(3, 10))
        ttk.Label(frame, text="Conexiones por descarga").grid(row=3, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=conexiones, state="readonly", width=5,
                     values=CONEXIONES_OPCIONES).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(frame, text="Iniciar descargas automaticamente al agregar enlaces",
                        variable=auto_iniciar).grid(row=4, column=0, columnspan=3, pady=(14, 2), sticky="w")
        ttk.Checkbutton(frame, text="Abrir la carpeta cuando termina toda la cola",
                        variable=abrir_al_finalizar).grid(row=5, column=0, columnspan=3, pady=2, sticky="w")
        ttk.Label(frame, text="Las preferencias se guardan solo en esta PC.").grid(
            row=6, column=0, columnspan=3, pady=(10, 14), sticky="w"
        )

        def guardar():
            try:
                conexiones_num = int(conexiones.get())
            except ValueError:
                conexiones_num = CONEXIONES_DEFAULT
            self.carpeta = carpeta.get()
            self.conexiones = conexiones_num
            self.auto_iniciar = auto_iniciar.get()
            self.abrir_al_finalizar = abrir_al_finalizar.get()
            self.cmb_conex.set(str(self.conexiones))
            self.lbl_carpeta.config(text=self.carpeta or "(sin carpeta)")
            self._guardar_preferencias()
            ventana.destroy()

        acciones = ttk.Frame(frame)
        acciones.grid(row=7, column=0, columnspan=3, sticky="e")
        ttk.Button(acciones, text="Cancelar", command=ventana.destroy).pack(side="right")
        ttk.Button(acciones, text="Guardar preferencias", command=guardar).pack(side="right", padx=(0, 6))

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
            elif self.abrir_al_finalizar and self.state.items and all(
                it.estado == "completo" for it in self.state.items
            ):
                self.root.after(0, self._abrir_carpeta)

        self.worker = threading.Thread(target=correr, daemon=True)
        self.worker.start()

    def _aviso_disco_lleno(self):
        self.btn_play.config(text="Reanudar")
        messagebox.showwarning("Disco lleno", "No hay espacio en disco. Libera espacio y despues reanuda.")

    def _quitar_seleccionados(self):
        seleccionados = self._items_seleccionados()
        if not seleccionados:
            return
        activos = [it for it in seleccionados if it.estado == "descargando"]
        if activos:
            messagebox.showwarning(
                "Descarga en curso",
                "Pausa la descarga antes de quitar el archivo que se esta bajando.")
            seleccionados = [it for it in seleccionados if it not in activos]
            if not seleccionados:
                return
        # Mutamos la lista in place (no reasignar) para que el worker en curso
        # vea la baja via la referencia que ya tiene.
        seleccion_ids = {id(it) for it in seleccionados}
        self.state.items[:] = [it for it in self.state.items if id(it) not in seleccion_ids]
        self.state.save()
        self._refrescar_tabla()

    def _toggle_colapso(self):
        self._todo_abierto = not self._todo_abierto
        for g in self.tree.get_children(""):
            self.tree.item(g, open=self._todo_abierto)
        self.btn_colapsar.config(text="Colapsar todo" if self._todo_abierto else "Expandir todo")

    def _reintentar(self):
        for it in self.state.items:
            if it.estado == "fallido":
                it.estado = "pendiente"
        self.state.save()
        self._refrescar_tabla()
        if not self.pausado.is_set():
            self._arrancar_worker()

    def _items_seleccionados(self):
        iids = set()
        for iid in self.tree.selection():
            if iid.startswith(GRP_PREFIX):
                iids.update(self.tree.get_children(iid))
            else:
                iids.add(iid)
        return [it for it in self.state.items if self._iid_item(it) in iids]

    def _iid_item(self, item):
        if not item.clip:
            return item.url
        return f"{item.url}::clip::{item.clip['inicio']}-{item.clip['fin']}"

    def _reintentar_seleccionados(self):
        items = self._items_seleccionados()
        for it in items:
            if it.estado in ("fallido", "pausado"):
                it.estado = "pendiente"
        self.state.save()
        self._refrescar_tabla()
        if items and not self.pausado.is_set():
            self._arrancar_worker()

    def _limpiar_completos(self):
        completos = [it for it in self.state.items if it.estado == "completo"]
        if not completos:
            return
        if not messagebox.askyesno(
            "Limpiar completados",
            f"Quitar {len(completos)} descarga(s) completada(s) de la cola? Los archivos no se borran.",
        ):
            return
        self.state.items[:] = [it for it in self.state.items if it.estado != "completo"]
        self.state.save()
        self._refrescar_tabla()

    def _copiar_enlaces(self):
        items = self._items_seleccionados()
        if not items:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(it.url for it in items))

    def _abrir_seleccionado(self):
        items = self._items_seleccionados()
        if not items:
            messagebox.showinfo("Elegí una descarga", "Seleccioná un archivo de la lista.")
            return
        ruta = os.path.join(items[0].carpeta, items[0].nombre)
        if not os.path.isfile(ruta):
            messagebox.showinfo("Archivo no disponible", "El archivo todavia no esta descargado o fue movido.")
            return
        abrir_ruta(ruta)

    def _seleccionar_todo(self, event=None):
        self.tree.selection_set(self.tree.get_children(""))
        return "break" if event else None

    def _mostrar_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    def _abrir_carpeta(self):
        if self.carpeta and os.path.isdir(self.carpeta):
            abrir_ruta(self.carpeta)

    def _fila(self, it):
        pct = int(it.bytes_bajados * 100 / it.total) if it.total else 0
        prog = f"{bar(pct)} {pct}%"
        vel = self._vel.get(it.url, {}).get("ema") if it.estado == "descargando" else None
        if vel:
            prog += f" · {humano(vel)}/s"
        return (humano(it.total) if it.total else "?", prog, it.estado)

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
            self.tree.insert("", "end", iid=gid, text=texto,
                              values=(humano(tam_grupo) if tam_grupo else "?", "", ""),
                              open=abiertos.get(gid, self._todo_abierto))
            for it in items:
                nombre = it.nombre
                if it.clip:
                    nombre += f"  [{_tiempo_humano(it.clip['inicio'])} - {_tiempo_humano(it.clip['fin'])}]"
                self.tree.insert(gid, "end", iid=self._iid_item(it), text=nombre,
                                 values=self._fila(it), tags=(it.estado,))
        self._actualizar_resumen()

    def _actualizar_resumen(self):
        total_items = len(self.state.items)
        if not total_items:
            self.lbl_resumen.config(text="Sin descargas en cola")
            self.progreso_global["value"] = 0
            return
        cantidades = {estado: sum(1 for it in self.state.items if it.estado == estado)
                      for estado in ("pendiente", "descargando", "pausado", "fallido", "completo")}
        partes = []
        etiquetas = (("descargando", "descargando"), ("pendiente", "pendientes"),
                     ("pausado", "pausadas"), ("fallido", "fallidas"), ("completo", "completas"))
        for estado, etiqueta in etiquetas:
            if cantidades[estado]:
                partes.append(f"{cantidades[estado]} {etiqueta}")
        bajado = sum(it.bytes_bajados for it in self.state.items)
        total = sum(it.total for it in self.state.items if it.total)
        texto = " · ".join(partes)
        if total:
            texto += f"  |  {humano(bajado)} de {humano(total)}"
            self.progreso_global["value"] = min(100, bajado * 100 / total)
        else:
            self.progreso_global["value"] = 0
        self.lbl_resumen.config(text=texto)

    def _drenar_cola(self):
        cambiado = False
        try:
            while True:
                it = self.cola_ui.get_nowait()
                self._actualizar_velocidad(it)
                cambiado = True
        except queue.Empty:
            pass
        if cambiado:
            self._refrescar_tabla()
            self.state.save()
        self.root.after(200, self._drenar_cola)
