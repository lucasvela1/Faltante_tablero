import tkinter as tk
from tkinter import ttk
from tkinter import font
from src.services.mes import login_jmmes, get_product_id, get_line_id, get_produced_quantity
from src.read_config import read_config
import threading

class VentanaInfo(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Tablero de Faltantes")
        self.geometry("550x460+20+20")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        self.configure(bg="black")
        self.current_scale = 1.0

        self.bind("<ButtonPress-1>", self.start_move)
        self.bind("<B1-Motion>", self.do_move)

        # Escuchamos el resize
        self.bind("<Configure>", self.on_resize)
        self.initial_width = 550
        self.initial_height = 460

        self.container = tk.Frame(self, bg="cyan")
        self.container.pack(expand=True, fill="both", padx=10, pady=10)

        self.secciones = {
            "LCD6": [],
            "LCD8": [],
            "Celda": [],
            "Celda2": [],
        }

        login_jmmes()

        self.datos = self.obtener_datos_config()
        self.labels = {}
        self.fuentes = {}  # Guardamos las fuentes para poder modificarlas
        self.textos_modelos = {}  # Guardamos los textos de los modelos actuales

        self.construir_interfaz()
        self.actualizar_datos()

    def start_move(self, event):
        self._x = event.x
        self._y = event.y

    def do_move(self, event):
        x = self.winfo_x() + event.x - self._x
        y = self.winfo_y() + event.y - self._y
        self.geometry(f"+{x}+{y}")

    def obtener_datos_config(self):
        raw_config = read_config("LINEAS")
        return raw_config

    def construir_interfaz(self):
        fila_actual = 0
        columna_actual = 0

        # Configuramos el grid del contenedor principal (2 columnas x 2 filas)
        for i in range(2):
            self.container.grid_columnconfigure(i, weight=1)
            self.container.grid_rowconfigure(i, weight=1)

        for seccion in self.secciones:
            frame = tk.LabelFrame(self.container, text=seccion, font=("Arial", 12, "bold"), bg="cyan", padx=10, pady=10)
            frame.grid(row=fila_actual, column=columna_actual, sticky="nsew", padx=5, pady=5)
            frame.grid_propagate(True)

            montaje_agregado = False
            accesorios_agregado = False

            for item in self.datos:
                linea = item["LINE"]
                modelo = item["MODEL"]
                linea_normalizada = linea.replace(" ", "").replace("-", "").lower()
                seccion_normalizada = seccion.replace(" ", "").replace("-", "").lower()

                if seccion_normalizada in linea_normalizada:
                    if "montaje" in linea.lower() and not montaje_agregado:
                        titulo = f"Montaje: {modelo}"
                        montaje_agregado = True
                    elif "accesorios" in linea.lower() and not accesorios_agregado:
                        titulo = f"Accesorios: {modelo}"
                        accesorios_agregado = True
                    else:
                        continue

                    fuente_modelo = font.Font(family="Arial", size=12, weight="bold")
                    fuente_datos = font.Font(family="Arial", size=10, weight="bold")

                    label_modelo = ttk.Label(frame, text=titulo, font=fuente_modelo, background="cyan")
                    label_modelo.pack(anchor="w", pady=(5, 0))

                    label_producidos = ttk.Label(frame, text="Pasaron por el primer puesto: ---", font=fuente_datos, background="cyan")
                    label_producidos.pack(anchor="w")

                    label_faltan = ttk.Label(frame, text="Faltan: ---", font=fuente_datos, background="cyan")
                    label_faltan.pack(anchor="w", pady=(0, 10))

                    clave = (modelo, linea)
                    self.labels[clave] = (label_modelo, label_producidos, label_faltan)
                    self.fuentes[clave] = (fuente_datos, fuente_datos)
                    self.textos_modelos[clave] = modelo  # Guardamos el modelo actual

            columna_actual += 1
            if columna_actual >= 2:
                columna_actual = 0
                fila_actual += 1

    def actualizar_datos(self):
        self.actualizar_textos_si_cambiaron()

        for item in self.datos:
            modelo = item["MODEL"]
            linea = item["LINE"]
            fecha_inicio = item["FechaInicio"]
            total = int(item["ProduccionTotal"])
            clave = (modelo, linea)

            line_id = get_line_id(linea)
            product_id = get_product_id(modelo, line_id)
            producidos = get_produced_quantity(product_id, line_id, fecha_inicio)
            faltan = total - producidos

            label_modelo, label_producidos, label_faltan = self.labels.get(clave, (None, None, None))
            if label_producidos and label_faltan:
                label_producidos.config(text=f"Pasaron por el primer puesto: {producidos}")
                label_faltan.config(text=f"Faltan: {faltan}")

        self.after(10000, self.actualizar_datos)

    def actualizar_textos_si_cambiaron(self):
        nuevos_datos = self.obtener_datos_config()

        for item in nuevos_datos:
            modelo = item["MODEL"]
            linea = item["LINE"]
            clave = (modelo, linea)

            if clave not in self.labels:
                # Si es un nuevo modelo/linea, reconstruir todo
                self.datos = nuevos_datos
                self.labels.clear()
                self.fuentes.clear()
                self.textos_modelos.clear()
                for widget in self.container.winfo_children():
                    widget.destroy()
                self.construir_interfaz()
                return

            # Si el modelo cambió, lo actualizamos
            if self.textos_modelos.get(clave) != modelo:
                label_modelo, _, _ = self.labels[clave]
                nuevo_titulo = f"Montaje: {modelo}" if "montaje" in linea.lower() else f"Accesorios: {modelo}"
                label_modelo.config(text=nuevo_titulo)
                self.textos_modelos[clave] = modelo

        self.datos = nuevos_datos

    def on_resize(self, event):  # Callback para el resize
        if event.widget == self:
            scale_x = event.width / self.initial_width
            scale_y = event.height / self.initial_height
            self.current_scale = min(scale_x, scale_y)

            for clave, (fuente_producidos, fuente_faltan) in self.fuentes.items():
                nueva_fuente_size = max(8, int(10 * self.current_scale))
                fuente_producidos.configure(size=nueva_fuente_size)
                fuente_faltan.configure(size=nueva_fuente_size)
