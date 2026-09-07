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
from .search import buscar_youtube

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
        self.modo_descarga = cfg.get("modo_descarga", "video")
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
        self.root.geometry("980x640")
        self.root.minsize(820, 540)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#f8fafc")
        style.configure("TLabel", background="#f8fafc", foreground="#334155", font=("Segoe UI", 9))
        style.configure("Brand.TFrame", background="#0f172a")
        style.configure("BrandTitle.TLabel", background="#0f172a", foreground="#f8fafc",
                        font=("Segoe UI", 16, "bold"))
        style.configure("BrandSub.TLabel", background="#0f172a", foreground="#94a3b8",
                        font=("Segoe UI", 9))
        style.configure("Brand.TButton", font=("Segoe UI", 9, "bold"), padding=(9, 5))
        style.configure("Primary.TButton", background="#2563eb", foreground="#ffffff",
                        font=("Segoe UI", 10, "bold"), padding=(14, 8))
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(8, 5))
        style.configure("Section.TLabel", foreground="#0f172a", font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("Treeview", rowheight=30, background="#ffffff", fieldbackground="#ffffff",
                        foreground="#334155", font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#e2e8f0", foreground="#475569",
                        font=("Segoe UI", 9, "bold"), relief="flat")

        brand = ttk.Frame(self.root, style="Brand.TFrame", padding=(14, 10))
        brand.pack(fill="x")
        ttk.Label(brand, text="ControlApps", style="BrandTitle.TLabel").pack(side="left")
        ttk.Label(brand, text="DESCARGADOR  ·  archivos y redes sociales",
                  style="BrandSub.TLabel").pack(side="left", padx=(12, 0), pady=(5, 0))
        ttk.Button(brand, text="Configuracion", style="Brand.TButton",
                   command=self._abrir_configuracion).pack(side="right")
        ttk.Button(brand, text="Actualizar", style="Brand.TButton",
                   command=lambda: self._buscar_actualizacion(True)).pack(side="right", padx=(0, 6))
        ttk.Button(brand, text="Buscar", style="Brand.TButton", command=self._abrir_buscador).pack(side="right", padx=(0, 6))

        top = ttk.LabelFrame(self.root, text=" Nueva descarga ", padding=12)
        top.pack(fill="x")

        ttk.Label(top, text="Pegá uno o varios enlaces para agregarlos a la cola").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 4)
        )
        self.txt = tk.Text(top, height=3, width=70, wrap="word", font=("Segoe UI", 10),
                           relief="solid", borderwidth=1, highlightthickness=0)
        self.txt.grid(row=1, column=0, columnspan=5, sticky="we")
        self.txt.bind("<Control-Return>", self._atajo_agregar)
        self.cmb_modo = ttk.Combobox(top, state="readonly", width=29,
            values=("Video completo", "Audio original (recomendado)", "MP3 320 kbps"))
        modos = {"video": "Video completo", "original": "Audio original (recomendado)", "mp3": "MP3 320 kbps"}
        self.cmb_modo.set(modos.get(self.modo_descarga, "Video completo"))
        self.cmb_modo.grid(row=2, column=5, pady=6, sticky="e")
        self.cmb_modo.bind("<<ComboboxSelected>>", self._cambiar_modo)
        ttk.Button(top, text="Descargar", style="Primary.TButton", command=self._agregar_pegados).grid(row=2, column=0, pady=8, sticky="w")
        ttk.Button(top, text="Pegar enlace", style="Secondary.TButton", command=self._pegar_y_agregar).grid(row=2, column=1, pady=8, padx=(7, 0), sticky="w")
        ttk.Button(top, text="Recortar", style="Secondary.TButton", command=self._abrir_recorte).grid(row=2, column=2, pady=8, padx=(7, 0), sticky="w")
        ttk.Button(top, text="Lista .txt", style="Secondary.TButton", command=self._cargar_txt).grid(row=2, column=3, pady=8, padx=(7, 0), sticky="w")
        ttk.Button(top, text="Carpeta", style="Secondary.TButton", command=self._elegir_carpeta).grid(row=2, column=4, pady=8, padx=(7, 0), sticky="w")
        self.lbl_carpeta = ttk.Label(top, text=self.carpeta or "Elegí una carpeta destino", style="Muted.TLabel")
        self.lbl_carpeta.grid(row=2, column=6, pady=8, padx=(8, 0), sticky="w")

        ttk.Label(top, text="Conexiones por descarga:").grid(row=3, column=0, columnspan=2, pady=(0, 2), sticky="w")
        self.cmb_conex = ttk.Combobox(top, width=4, state="readonly", values=CONEXIONES_OPCIONES)
        self.cmb_conex.set(str(self.conexiones))
        self.cmb_conex.grid(row=3, column=1, pady=(0, 2), sticky="e")
        self.cmb_conex.bind("<<ComboboxSelected>>", self._cambiar_conexiones)
        ttk.Label(top, text="Audio original conserva la mejor calidad real de YouTube; MP3 320 prioriza compatibilidad.").grid(
            row=3, column=2, columnspan=4, padx=(12, 0), sticky="w"
        )
        top.columnconfigure(4, weight=1)
        self.root.after(1500, self._buscar_actualizacion)

        encabezado_cola = ttk.Frame(self.root, padding=(12, 11, 12, 5))
        encabezado_cola.pack(fill="x")
        ttk.Label(encabezado_cola, text="Cola de descargas", style="Section.TLabel").pack(side="left")
        ttk.Label(encabezado_cola, text="Click derecho para mas acciones", style="Muted.TLabel").pack(
            side="left", padx=(10, 0), pady=(3, 0))
        ttk.Button(encabezado_cola, text="Limpiar completas", style="Secondary.TButton",
                   command=self._limpiar_completos).pack(side="right")

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

        bottom = ttk.Frame(self.root, padding=(12, 10))
        bottom.pack(fill="x")
        self.btn_play = ttk.Button(bottom, text="Reanudar descargas", style="Primary.TButton", command=self._toggle_pausa)
        self.btn_play.grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Reintentar fallidas", style="Secondary.TButton", command=self._reintentar).grid(row=0, column=1, padx=(7, 0), sticky="w")
        ttk.Button(bottom, text="Reintentar selección", command=self._reintentar_seleccionados).grid(row=0, column=2, padx=(6, 0), sticky="w")
        ttk.Button(bottom, text="Quitar", style="Secondary.TButton", command=self._quitar_seleccionados).grid(row=0, column=3, padx=(7, 0), sticky="w")
        ttk.Button(bottom, text="Limpiar", style="Secondary.TButton", command=self._limpiar_completos).grid(row=0, column=4, padx=(7, 0), sticky="w")
        ttk.Button(bottom, text="Abrir archivo", style="Secondary.TButton", command=self._abrir_seleccionado).grid(row=0, column=5, padx=(7, 0), sticky="w")
        ttk.Button(bottom, text="Abrir carpeta", style="Secondary.TButton", command=self._abrir_carpeta).grid(row=0, column=6, padx=(7, 0), sticky="w")
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
            if self.state.add(url, nombre, self.carpeta, audio_format="" if self.modo_descarga == "video" else self.modo_descarga):
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

    def _abrir_buscador(self):
        win = tk.Toplevel(self.root)
        win.title("ControlApps · Buscar en YouTube")
        win.geometry("720x430")
        frame = ttk.Frame(win, padding=14); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Buscar en YouTube", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Resultados directos para descargar. Proximamente: TikTok y busqueda web.").pack(anchor="w", pady=(2, 8))
        consulta = tk.StringVar(); entrada = ttk.Entry(frame, textvariable=consulta)
        entrada.pack(fill="x"); entrada.focus_set()
        tree = ttk.Treeview(frame, columns=("canal", "duracion"), show="tree headings", height=12)
        tree.heading("#0", text="Titulo"); tree.heading("canal", text="Canal"); tree.heading("duracion", text="Duracion")
        tree.column("#0", width=420); tree.column("canal", width=180); tree.column("duracion", width=80)
        tree.pack(fill="both", expand=True, pady=10)
        resultados = []
        estado = ttk.Label(frame, text="Escribi una busqueda y presiona Enter."); estado.pack(anchor="w")

        def ejecutar(event=None):
            estado.config(text="Buscando..."); tree.delete(*tree.get_children())
            def trabajo():
                try:
                    encontrados = buscar_youtube(consulta.get().strip())
                    self.root.after(0, lambda: mostrar(encontrados))
                except Exception:
                    self.root.after(0, lambda: estado.config(text="No se pudo buscar en YouTube."))
            threading.Thread(target=trabajo, daemon=True).start()

        def mostrar(encontrados):
            nonlocal resultados; resultados = encontrados
            for i, item in enumerate(resultados):
                tree.insert("", "end", iid=str(i), text=item["title"], values=(item["channel"], _tiempo_humano(item["duration"])))
            estado.config(text=f"{len(resultados)} resultados. Selecciona uno para agregarlo.")

        def agregar():
            seleccion = tree.selection()
            if seleccion:
                self._agregar_links([resultados[int(seleccion[0])]["url"]])
                estado.config(text="Agregado a la cola.")

        entrada.bind("<Return>", ejecutar)
        acciones = ttk.Frame(frame); acciones.pack(fill="x", pady=(8, 0))
        ttk.Button(acciones, text="Buscar", command=ejecutar).pack(side="left")
        ttk.Button(acciones, text="Agregar a la cola", command=agregar).pack(side="right")

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

    def _cambiar_modo(self, event=None):
        texto = self.cmb_modo.get()
        self.modo_descarga = "original" if texto.startswith("Audio original") else "mp3" if texto.startswith("MP3") else "video"
        self._guardar_preferencias()

    def _guardar_preferencias(self):
        _guardar_config({
            "carpeta": self.carpeta,
            "conexiones": self.conexiones,
            "auto_iniciar": self.auto_iniciar,
            "abrir_al_finalizar": self.abrir_al_finalizar,
            "actualizar_automaticamente": self.actualizar_automaticamente,
            "modo_descarga": self.modo_descarga,
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
        actualizar_automaticamente = tk.BooleanVar(value=self.actualizar_automaticamente)

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
        ttk.Checkbutton(frame, text="Buscar e instalar actualizaciones automaticamente",
                        variable=actualizar_automaticamente).grid(row=6, column=0, columnspan=3, pady=2, sticky="w")
        ttk.Label(frame, text="Las preferencias se guardan solo en esta PC.").grid(
            row=7, column=0, columnspan=3, pady=(10, 14), sticky="w"
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
            self.actualizar_automaticamente = actualizar_automaticamente.get()
            self.cmb_conex.set(str(self.conexiones))
            self.lbl_carpeta.config(text=self.carpeta or "(sin carpeta)")
            self._guardar_preferencias()
            ventana.destroy()

        acciones = ttk.Frame(frame)
        acciones.grid(row=8, column=0, columnspan=3, sticky="e")
        ttk.Button(acciones, text="Cancelar", command=ventana.destroy).pack(side="right")
        ttk.Button(acciones, text="Guardar preferencias", command=guardar).pack(side="right", padx=(0, 6))

    def _toggle_pausa(self):
        if self.pausado.is_set():
            self.pausado.clear()
            self.btn_play.config(text="Pausar")
            self._arrancar_worker()
        else:
            self.pausado.set()
            self.btn_play.config(text="Reanudar descargas")

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
        self.btn_play.config(text="Reanudar descargas")
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
                if it.audio_format == "original":
                    nombre += "  [audio original]"
                elif it.audio_format == "mp3":
                    nombre += "  [MP3 320]"
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
