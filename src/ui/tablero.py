import tkinter as tk
from tkinter import ttk
from tkinter import font
# Ensure correct import path based on your project structure
from src.services.mes import login_jmmes, get_product_id, get_line_id, get_produced_quantity # Assuming mes.py is in src/services/
from src.read_config import read_config
import threading
import time
import logging # Use logging

# Configure logging (optional, but helpful)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class VentanaInfo(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Tablero de Faltantes")
        self.geometry("650x560+20+20")
        self.attributes("-topmost", True) # Mantener la ventana siempre en primer plano
        self.resizable(True, True)
        self.configure(bg="black")
        self.current_scale = 1.0

        # --- Window Dragging ---
        self._x = 0
        self._y = 0
        self.bind("<ButtonPress-1>", self.start_move)
        self.bind("<B1-Motion>", self.do_move)

        # --- Resizing ---
        self.bind("<Configure>", self.on_resize)
        self.initial_width = 650
        self.initial_height = 560

        # --- Main Container ---
        self.container = tk.Frame(self, bg="cyan")
        self.container.pack(expand=True, fill="both", padx=10, pady=10)

        # Define sections (must match keys in construir_interfaz logic)
        self.secciones = ["LCD6", "LCD8", "Celda", "Celda2"]

        # --- Data & State ---
        self.datos = [] # Initialized empty, filled later
        # Stores tuples: (label_modelo, label_prod_1, label_faltan_1, label_prod_emb, label_faltan_emb)
        self.labels = {}
        self.fuentes_datos_base = {} # Store base font config if needed for reset/reference
        self.textos_modelos = {}  # Guardamos los textos de los modelos actuales

        # --- Initialization ---
        logging.info("Iniciando login a JMMES...")
        login_jmmes() # Perform initial login

        logging.info("Obteniendo datos de configuración inicial...")
        self.datos = self.obtener_datos_config()

        logging.info("Construyendo interfaz gráfica...")
        self.construir_interfaz()

        logging.info("Iniciando hilo de actualización de datos...")
        self.actualizar_datos_en_hilo()


    def start_move(self, event):
        # Record mouse position relative to window's top-left corner
        self._x = event.x
        self._y = event.y

    def do_move(self, event):
        # Calculate new window position based on mouse movement
        deltax = event.x - self._x
        deltay = event.y - self._y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def obtener_datos_config(self):
        try:
            raw_config = read_config("LINEAS")
            if not isinstance(raw_config, list):
                logging.error("La configuración 'LINEAS' no es una lista.")
                return []
            return raw_config
        except Exception as e:
            logging.error(f"Error al leer la configuración 'LINEAS': {e}")
            return [] # Return empty list on error

    def normalizar_cadena(self, cadena):
        """Helper to normalize strings for comparison."""
        return cadena.replace(" ", "").replace("-", "").lower()

    def crear_etiquetas_principales(self, frame, titulo, fuente_modelo, fuente_datos):
        """Crea y empaqueta las etiquetas para Modelo, Primer Puesto y Faltantes (Primer Puesto)."""
        label_modelo = ttk.Label(frame, text=titulo, font=fuente_modelo, background="cyan")
        label_modelo.pack(anchor="w", pady=(5, 0))

        label_producidos = ttk.Label(frame, text="Pasaron por Primer Puesto: ---", font=fuente_datos, background="cyan")
        label_producidos.pack(anchor="w")

        label_faltan = ttk.Label(frame, text="Faltan (Primer Puesto): ---", font=fuente_datos, background="cyan")
        label_faltan.pack(anchor="w", pady=(0, 5)) # Add padding below this group

        return label_modelo, label_producidos, label_faltan

    def crear_etiquetas_embalaje(self, frame, fuente_datos):
        """Crea y empaqueta las etiquetas para Embalaje y Faltantes (Embalaje)."""
        label_producidos_emb = ttk.Label(frame, text="Pasaron por Embalaje: ---", font=fuente_datos, background="cyan")
        label_producidos_emb.pack(anchor="w")

        label_faltan_emb = ttk.Label(frame, text="Faltan (Embalaje): ---", font=fuente_datos, background="cyan")
        label_faltan_emb.pack(anchor="w", pady=(0, 10)) # Bottom padding

        return label_producidos_emb, label_faltan_emb

    def construir_interfaz(self):
        """Construye la interfaz de usuario con secciones y etiquetas."""
        for widget in self.container.winfo_children():
            widget.destroy()

        self.labels.clear()
        self.textos_modelos.clear()
        self.fuentes_datos_base.clear()

        fila_actual = 0
        columna_actual = 0

        num_cols = 2
        for i in range(num_cols):
            self.container.grid_columnconfigure(i, weight=1, uniform="colGroup") 
        num_rows = (len(self.secciones) + num_cols - 1) // num_cols
        for i in range(num_rows):
             self.container.grid_rowconfigure(i, weight=1, uniform="rowGroup") 


        base_model_font_size = 12
        base_data_font_size = 10

        for seccion in self.secciones:
            frame = tk.LabelFrame(self.container, text=seccion, font=("Arial", base_model_font_size, "bold"), bg="cyan", fg="black", padx=10, pady=10, borderwidth=2, relief=tk.GROOVE)
            frame.grid(row=fila_actual, column=columna_actual, sticky="nsew", padx=5, pady=5)
            #frame.grid_propagate(True) 
            montaje_agregado = False
            accesorios_agregado = False
            seccion_normalizada = self.normalizar_cadena(seccion)

            for item in self.datos:
                linea = item.get("LINE", "N/A")
                modelo = item.get("MODEL", "N/A")
                linea_normalizada = self.normalizar_cadena(linea)

                if seccion_normalizada in linea_normalizada:
                    titulo_base = ""
                    item_type = "" # 'montaje' or 'accesorios'

                   
                    if "montaje" in linea.lower() and not montaje_agregado:
                        titulo_base = "Montaje"
                        montaje_agregado = True
                        item_type = "montaje"
                    elif "accesorios" in linea.lower() and not accesorios_agregado:
                        titulo_base = "Accesorios"
                        accesorios_agregado = True
                        item_type = "accesorios"
                    else:
                        continue 

                    # --- Crear Fonts ---
                    fuente_modelo = font.Font(family="Arial", size=base_model_font_size, weight="bold")
                    fuente_datos = font.Font(family="Arial", size=base_data_font_size, weight="bold")

                    # --- Crear Labels ---
                    titulo_completo = f"{titulo_base}: {modelo}"
                    label_modelo, label_prod_1, label_faltan_1 = self.crear_etiquetas_principales(frame, titulo_completo, fuente_modelo, fuente_datos)

                    label_prod_emb, label_faltan_emb = None, None

                    
                    if seccion in ["LCD6", "LCD8"] and item_type == "montaje":
                        label_prod_emb, label_faltan_emb = self.crear_etiquetas_embalaje(frame, fuente_datos)

                    clave = (modelo, linea) # Use tuple as key
                    self.labels[clave] = (label_modelo, label_prod_1, label_faltan_1, label_prod_emb, label_faltan_emb)
                    self.textos_modelos[clave] = modelo
                    self.fuentes_datos_base[clave] = {'family': "Arial", 'size': base_data_font_size, 'weight': "bold"}

            columna_actual += 1
            if columna_actual >= num_cols:
                columna_actual = 0
                fila_actual += 1

        self.update_idletasks()
        


    def actualizar_datos(self):
        while True:
            try:
                logging.info("Verificando cambios en la configuración...")
                config_changed = self.actualizar_textos_si_cambiaron()
                if config_changed:
                    logging.info("Configuración cambiada, la interfaz se reconstruyó. Saltando ciclo de actualización.")
                    time.sleep(8) 
                    continue

                logging.info("Actualizando datos de producción...")
                if not self.datos:
                    logging.warning("No hay datos de configuración ('LINEAS') para procesar.")
                    time.sleep(30) # Wait longer if config is missing
                    continue

                for item in self.datos:
                    modelo = item.get("MODEL", "N/A")
                    linea = item.get("LINE", "N/A")
                    fecha_inicio = item.get("FechaInicio", "") 
                    total = 0
                    try:
                        total = int(item.get("ProduccionTotal", 0))
                    except (ValueError, TypeError):
                         logging.warning(f"ProduccionTotal inválido para {modelo}/{linea}. Usando 0.")
                         total = 0

                    clave = (modelo, linea)

                    if clave not in self.labels:
                        continue

                    producidos_1 = 0
                    faltan_1 = total
                    producidos_emb = 0
                    faltan_emb = total

                    try:
                        line_id = get_line_id(linea)
                        if line_id is None:
                            logging.warning(f"No se encontró Line ID para '{linea}'. Saltando.")
                            continue

                        product_id = get_product_id(modelo, line_id)
                        if product_id is None:
                            logging.warning(f"No se encontró Product ID para '{modelo}' en línea ID {line_id}. Saltando.")
                            continue 

                        producidos_1 = get_produced_quantity(product_id, line_id, fecha_inicio, linea, station_key_name="estacion")
                        faltan_1 = total - producidos_1

                        
                        labels_tuple = self.labels.get(clave)
                        if labels_tuple and labels_tuple[3] is not None: 
                            producidos_emb = get_produced_quantity(product_id, line_id, fecha_inicio, linea, station_key_name="estacion_embalaje")
                            faltan_emb = total - producidos_emb

                    except Exception as e:
                        logging.error(f"Error obteniendo datos de producción para {modelo} en {linea}: {e}", exc_info=True)
                        producidos_1 = 0
                        faltan_1 = total
                        producidos_emb = 0
                        faltan_emb = total # Reset embalaje too

                    labels_tuple = self.labels.get(clave)
                    if labels_tuple:
                        _label_modelo, label_producidos_1, label_faltan_1, label_producidos_emb, label_faltan_emb = labels_tuple

                        if label_producidos_1:
                            label_producidos_1.config(text=f"Pasaron por Primer Puesto: {producidos_1}")
                        if label_faltan_1:
                            label_faltan_1.config(text=f"Faltan (Primer Puesto): {faltan_1}")

                        if label_producidos_emb:
                            label_producidos_emb.config(text=f"Pasaron por Embalaje: {producidos_emb}")
                        if label_faltan_emb:
                            label_faltan_emb.config(text=f"Faltan (Embalaje): {faltan_emb}")

                logging.info("Ciclo de actualización de datos completado.")

            except Exception as e:
                logging.error(f"Error inesperado en el hilo de actualización: {e}", exc_info=True)

            time.sleep(6)  

    def actualizar_datos_en_hilo(self):
        update_thread = threading.Thread(target=self.actualizar_datos, daemon=True)
        update_thread.start()

    def actualizar_textos_si_cambiaron(self):
        """
        Comprueba si la configuración ha cambiado (modelos o líneas)
        y reconstruye la interfaz si es necesario.
        Devuelve True si la interfaz fue reconstruida, False en caso contrario.
        """
        nuevos_datos = self.obtener_datos_config()
        reconstruir = False

        current_keys = set(self.labels.keys())
        new_keys = set((item.get("MODEL", "N/A"), item.get("LINE", "N/A")) for item in nuevos_datos)

        if current_keys != new_keys:
            logging.info("Cambio detectado en las claves Modelo/Línea. Reconstruyendo interfaz.")
            reconstruir = True
        else:
            for item in nuevos_datos:
                modelo = item.get("MODEL", "N/A")
                linea = item.get("LINE", "N/A")
                clave = (modelo, linea)
                if self.textos_modelos.get(clave) != modelo:
                     logging.info(f"Cambio de modelo detectado para la línea '{linea}'. Reconstruyendo interfaz.")
                     reconstruir = True
                     break 

        if reconstruir:
            self.datos = nuevos_datos # Update data source
            self.construir_interfaz() # Rebuild the UI completely
            return True 
        else:
            
            self.datos = nuevos_datos
            return False # Indicate no rebuild

    def on_resize(self, event):
        if event.widget == self:
            if self.initial_width == 0 or self.initial_height == 0:
                return

            current_width = self.winfo_width()
            current_height = self.winfo_height()

            scale_x = current_width / self.initial_width if self.initial_width > 0 else 1.0
            scale_y = current_height / self.initial_height if self.initial_height > 0 else 1.0

            self.current_scale = min(scale_x, scale_y)

            
            new_model_font_size = max(10, int(12 * self.current_scale)) 
            new_data_font_size = max(8, int(10 * self.current_scale))

            for clave, label_tuple in self.labels.items():
                base_data_font_cfg = self.fuentes_datos_base.get(clave, {'family': "Arial", 'size': 10, 'weight': "bold"})
                data_family = base_data_font_cfg['family']
                data_weight = base_data_font_cfg['weight']

                if label_tuple[0]: # label_modelo
                    try:
                        model_font_cfg = font.Font(font=label_tuple[0].cget('font'))
                        model_family = model_font_cfg.actual()['family']
                        model_weight = model_font_cfg.actual()['weight']
                        label_tuple[0].config(font=(model_family, new_model_font_size, model_weight))
                    except tk.TclError:
                        logging.warning(f"No se pudo parsear la fuente del modelo para {clave}")
                        label_tuple[0].config(font=("Arial", new_model_font_size, "bold"))


                data_font_tuple = (data_family, new_data_font_size, data_weight)
                if label_tuple[1]: 
                    label_tuple[1].config(font=data_font_tuple)
                if label_tuple[2]: 
                    label_tuple[2].config(font=data_font_tuple)
                if label_tuple[3]: 
                    label_tuple[3].config(font=data_font_tuple)
                if label_tuple[4]: 
                    label_tuple[4].config(font=data_font_tuple)

            for frame in self.container.winfo_children():
                 if isinstance(frame, tk.LabelFrame):
                     try:
                         frame_font_cfg = font.Font(font=frame.cget('font'))
                         frame_family = frame_font_cfg.actual()['family']
                         frame_weight = frame_font_cfg.actual()['weight']
                         frame.config(font=(frame_family, new_model_font_size, frame_weight)) # Use model size for titles
                     except tk.TclError:
                          frame.config(font=("Arial", new_model_font_size, "bold"))