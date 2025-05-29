import tkinter as tk
from tkinter import ttk
from tkinter import font
# Asegúrate que estas importaciones sean correctas según tu estructura de proyecto
from src.services.mes import login_jmmes, get_product_id, get_line_id, get_produced_quantity
from src.read_config import read_config
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class VentanaInfo(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Tablero de Faltantes")
        self.geometry("650x700+20+20")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        self.configure(bg="black")
        self.current_scale = 1.0

        self._x = 0
        self._y = 0
        self.bind("<ButtonPress-1>", self.start_move)
        self.bind("<B1-Motion>", self.do_move)

        self.bind("<Configure>", self.on_resize)
        self.initial_width = 650
        self.initial_height = 700

        self.container = tk.Frame(self, bg="cyan")
        self.container.pack(expand=True, fill="both", padx=10, pady=10)

        self.secciones = ["LCD6", "LCD8", "Celda", "Celda2"]
        self.datos = []
        self.labels = {}
        self.fuentes_datos_base = {}
        self.textos_modelos = {}

        logging.info("Iniciando login a JMMES...")
        login_jmmes()

        logging.info("Obteniendo datos de configuración inicial...")
        self.datos = self.obtener_datos_config()

        logging.info("Construyendo interfaz gráfica...")
        self.construir_interfaz()

        logging.info("Iniciando hilo de actualización de datos...")
        self.actualizar_datos_en_hilo()

    def start_move(self, event):
        self._x = event.x
        self._y = event.y

    def do_move(self, event):
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
            return []

    def normalizar_cadena(self, cadena):
        return cadena.replace(" ", "").replace("-", "").lower()

    def crear_etiquetas_principales(self, frame, titulo, fuente_modelo, fuente_datos):
        label_modelo = ttk.Label(frame, text=titulo, font=fuente_modelo, background="cyan")
        label_modelo.pack(anchor="w", pady=(5, 0))
        label_producidos = ttk.Label(frame, text="Pasaron por Primer Puesto: ---", font=fuente_datos, background="cyan")
        label_producidos.pack(anchor="w")
        label_faltan = ttk.Label(frame, text="Faltan (Primer Puesto): ---", font=fuente_datos, background="cyan")
        label_faltan.pack(anchor="w", pady=(0, 5))
        return label_modelo, label_producidos, label_faltan

    def crear_etiquetas_embalaje(self, frame, fuente_datos):
        label_producidos_emb = ttk.Label(frame, text="Pasaron por Embalaje: ---", font=fuente_datos, background="cyan")
        label_producidos_emb.pack(anchor="w")
        label_faltan_emb = ttk.Label(frame, text="Faltan (Embalaje): ---", font=fuente_datos, background="cyan")
        label_faltan_emb.pack(anchor="w", pady=(0, 10))
        return label_producidos_emb, label_faltan_emb

    def crear_etiquetas_lotes(self, frame, fuente_datos):
        label_lote = ttk.Label(frame, text="Lote total: ---", font=fuente_datos, background="cyan")
        label_lote.pack(anchor="w", pady=(5, 0))
        label_lote_faltante = ttk.Label(frame, text="Lote faltante (Pallet): ---", font=fuente_datos, background="cyan") # Texto actualizado
        label_lote_faltante.pack(anchor="w", pady=(0, 5))
        return label_lote, label_lote_faltante

    def construir_interfaz(self):
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
            montaje_agregado = False
            accesorios_agregado = False
            seccion_normalizada = self.normalizar_cadena(seccion)

            for item in self.datos:
                linea = item.get("LINE", "N/A")
                modelo = item.get("MODEL", "N/A")
                linea_normalizada = self.normalizar_cadena(linea)

                if seccion_normalizada in linea_normalizada:
                    titulo_base = ""
                    item_type = ""
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

                    fuente_modelo = font.Font(family="Arial", size=base_model_font_size, weight="bold")
                    fuente_datos = font.Font(family="Arial", size=base_data_font_size, weight="bold")
                    titulo_completo = f"{titulo_base}: {modelo}"
                    label_modelo, label_prod_1, label_faltan_1 = self.crear_etiquetas_principales(frame, titulo_completo, fuente_modelo, fuente_datos)
                    label_prod_emb, label_faltan_emb = None, None
                    label_lote, label_lote_faltante = None, None

                    if seccion in ["LCD6", "LCD8"] and item_type == "montaje":
                        label_prod_emb, label_faltan_emb = self.crear_etiquetas_embalaje(frame, fuente_datos)
                    
                    if item_type == "montaje" and item.get("CantidadLote") is not None:
                        label_lote, label_lote_faltante = self.crear_etiquetas_lotes(frame, fuente_datos)

                    clave = (modelo, linea)
                    self.labels[clave] = (label_modelo, label_prod_1, label_faltan_1,
                                          label_prod_emb, label_faltan_emb,
                                          label_lote, label_lote_faltante)
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
                logging.debug("Verificando cambios en la configuración...")
                config_changed = self.actualizar_textos_si_cambiaron()
                if config_changed:
                    logging.info("Configuración cambiada, la interfaz se reconstruyó. Saltando ciclo de actualización.")
                    time.sleep(8)
                    continue

                logging.debug("Actualizando datos de producción...")
                if not self.datos:
                    logging.warning("No hay datos de configuración ('LINEAS') para procesar.")
                    time.sleep(30)
                    continue

                for item in self.datos:
                    modelo = item.get("MODEL", "N/A")
                    linea = item.get("LINE", "N/A")
                    fecha_inicio = item.get("FechaInicio", "")
                    total = 0
                    cantidad_lote_config = item.get("CantidadLote")
                    cantidad_lote_val = 0

                    try:
                        total = int(item.get("ProduccionTotal", 0))
                    except (ValueError, TypeError):
                        logging.warning(f"ProduccionTotal inválido para {modelo}/{linea}. Usando 0.")
                        total = 0

                    if cantidad_lote_config is not None:
                        try:
                            cantidad_lote_val = int(cantidad_lote_config)
                        except (ValueError, TypeError):
                            logging.warning(f"CantidadLote inválido para {modelo}/{linea} ('{cantidad_lote_config}'). Usando 0.")
                            cantidad_lote_val = 0
                    
                    clave = (modelo, linea)
                    if clave not in self.labels:
                        logging.debug(f"Clave {clave} no encontrada en self.labels. Saltando.")
                        continue

                    producidos_1 = 0
                    faltan_1 = total
                    producidos_emb = 0
                    faltan_emb = total
                    producidos_lote = 0 # Para la cantidad que pasó por el puesto de lote (palletizado)
                    lote_faltante_val = cantidad_lote_val # Inicializa con el total del lote

                    line_id = None
                    product_id = None

                    try:
                        line_id = get_line_id(linea)
                        if line_id is None:
                            logging.warning(f"No se encontró Line ID para '{linea}'. Saltando.")
                            continue

                        product_id = get_product_id(modelo, line_id)
                        if product_id is None:
                            logging.warning(f"No se encontró Product ID para '{modelo}' en línea ID {line_id}. Saltando.")
                            continue

                        # 1. Cantidad del primer puesto
                        producidos_1 = get_produced_quantity(product_id, line_id, fecha_inicio, linea, station_key_name="estacion")
                        faltan_1 = total - producidos_1
                        
                        # 2. Cantidad de embalaje (LCD6 y LCD8)
                        labels_tuple_check_emb = self.labels.get(clave)
                        if labels_tuple_check_emb and labels_tuple_check_emb[3] is not None: # Verifica si label_prod_emb existe
                            producidos_emb = get_produced_quantity(product_id, line_id, fecha_inicio, linea, station_key_name="estacion_embalaje")
                            faltan_emb = total - producidos_emb

                        # 3. Cantidad del puesto de lote (palletizado) - SOLO si hay CantidadLote en config
                        if cantidad_lote_config is not None:
                            producidos_lote = get_produced_quantity(product_id, line_id, fecha_inicio, linea, station_key_name="estacion_lote")
                            lote_faltante_val = cantidad_lote_val - producidos_lote
                        
                    except Exception as e:
                        logging.error(f"Error obteniendo datos de producción para {modelo} en {linea}: {e}", exc_info=False)
                        producidos_1 = 0; faltan_1 = total
                        producidos_emb = 0; faltan_emb = total
                        producidos_lote = 0; lote_faltante_val = cantidad_lote_val
                    
                    # Actualizar etiquetas
                    labels_tuple = self.labels.get(clave)
                    if labels_tuple:
                        _label_modelo, label_producidos_1, label_faltan_1, \
                        label_producidos_emb, label_faltan_emb, \
                        label_lote, label_lote_faltante = labels_tuple

                        if label_producidos_1: label_producidos_1.config(text=f"Pasaron por Primer Puesto: {producidos_1}")
                        if label_faltan_1: label_faltan_1.config(text=f"Faltan (Primer Puesto): {faltan_1}")
                        if label_producidos_emb: label_producidos_emb.config(text=f"Pasaron por Embalaje: {producidos_emb}")
                        if label_faltan_emb: label_faltan_emb.config(text=f"Faltan (Embalaje): {faltan_emb}")

                        if cantidad_lote_config is not None: # Solo actualiza si hay config de lote
                            if label_lote: label_lote.config(text=f"Lote total: {cantidad_lote_val}")
                            if label_lote_faltante: label_lote_faltante.config(text=f"Lote faltante (Pallet): {lote_faltante_val}") 
                        else: # Si no hay config de lote, las etiquetas (si existen por error) deberían mostrar "---"
                            if label_lote: label_lote.config(text="Lote total: ---")
                            if label_lote_faltante: label_lote_faltante.config(text="Lote faltante (Pallet): ---")
                
                logging.debug("Ciclo de actualización de datos completado.")
            except Exception as e:
                logging.error(f"Error inesperado en el hilo de actualización: {e}", exc_info=True)
            time.sleep(6)

    def actualizar_datos_en_hilo(self):
        update_thread = threading.Thread(target=self.actualizar_datos, daemon=True)
        update_thread.start()

    def item_config_changed(self, old_item, new_item):
        if old_item.get("MODEL") != new_item.get("MODEL"): return True
        if old_item.get("LINE") != new_item.get("LINE"): return True
        if ("CantidadLote" in old_item) != ("CantidadLote" in new_item): return True
        if old_item.get("CantidadLote") != new_item.get("CantidadLote") and \
           ("CantidadLote" in old_item or "CantidadLote" in new_item) : return True
        return False

    def actualizar_textos_si_cambiaron(self):
        nuevos_datos = self.obtener_datos_config()
        reconstruir = False
        current_config_map = {(item.get("MODEL", "N/A"), item.get("LINE", "N/A")): item for item in self.datos}
        new_config_map = {(item.get("MODEL", "N/A"), item.get("LINE", "N/A")): item for item in nuevos_datos}

        if set(current_config_map.keys()) != set(new_config_map.keys()):
            logging.info("Cambio detectado en el conjunto de Modelo/Línea. Reconstruyendo interfaz.")
            reconstruir = True
        else:
            for key, old_item in current_config_map.items():
                new_item = new_config_map[key]
                if self.item_config_changed(old_item, new_item):
                    logging.info(f"Cambio detectado en la config del item {key}. Reconstruyendo interfaz.")
                    reconstruir = True
                    break
        
        if reconstruir:
            self.datos = nuevos_datos
            self.construir_interfaz()
            return True
        else:
            self.datos = nuevos_datos # Actualiza con los nuevos datos aunque no se reconstruya (ej. ProduccionTotal cambia)
            return False

    def on_resize(self, event):
        if event.widget == self:
            if self.initial_width == 0 or self.initial_height == 0: return
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
                data_font_tuple = (data_family, new_data_font_size, data_weight)

                if label_tuple[0]: # label_modelo
                    try:
                        model_font_cfg = font.Font(font=label_tuple[0].cget('font'))
                        label_tuple[0].config(font=(model_font_cfg.actual()['family'], new_model_font_size, model_font_cfg.actual()['weight']))
                    except tk.TclError:
                        label_tuple[0].config(font=("Arial", new_model_font_size, "bold"))
                
                for i in range(1, len(label_tuple)): # Resto de las etiquetas de datos
                    if label_tuple[i]:
                        label_tuple[i].config(font=data_font_tuple)

            for frame_widget in self.container.winfo_children(): 
                if isinstance(frame_widget, tk.LabelFrame):
                    try:
                        frame_font_cfg = font.Font(font=frame_widget.cget('font'))
                        frame_widget.config(font=(frame_font_cfg.actual()['family'], new_model_font_size, frame_font_cfg.actual()['weight']))
                    except tk.TclError:
                        frame_widget.config(font=("Arial", new_model_font_size, "bold"))
