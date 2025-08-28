import tkinter as tk
from tkinter import ttk, font
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import threading
import time
import logging
import warnings

# --- 0. CONFIGURACIÓN INICIAL ---
# Oculta advertencias de openpyxl sobre el formato condicional no soportado
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')


# --- 1. CONFIGURACIÓN Y CONSTANTES GLOBALES ---
API_MES = "http://premes.newsan.com.ar"
RUTA_EXCEL = r'\\ush-nt-3\v1\infprod\PLAN_PRO\Programas de producción x planta\Programa P5 - 2025.xlsx' #La r es para leer el String "raw"
NOMBRES_HOJAS = ['LCD6', 'LCD8', 'CELDA 1', 'CELDA 2', 'CELDA 3'] #Nombres de las hojas en el Excel

# Se define la ventana de tiempo para la media móvil en minutos.
VENTANA_TIEMPO_MINUTOS = 60 

LINE_MAP = {
    "LCD6 - Montaje":      { "id": 3, "estacion": "hermanado placa - pantalla", "estacion_embalaje": "Embalaje" },
    "LCD6 - Accesorios":   { "id": 14, "estacion": "puesto 1" },
    "LCD8 - Montaje":      { "id": 10, "estacion": "pantalla - placa 1", "estacion_embalaje": "Embalaje" },
    "LCD8 - Accesorios":   { "id": 9, "estacion": "balanza ó puesto 1" },
    "CELDA 1 - Montaje":   { "id": 13, "estacion": "pantalla - placa 1 ó pantalla - placa 1 ó pantalla - placas - técnica ó hermanado placa - pantalla" },
    "CELDA 1 - Accesorios":{ "id": 12, "estacion": "balanza ó puesto 1" },
    "CELDA 2 - Montaje":   { "id": 82, "estacion": "pantalla - placas - técnica ó hermanado Placa - pantalla" },
    "CELDA 2 - Accesorios":{ "id": 83, "estacion": "balanza ó puesto 1" },
    "CELDA 3 - Montaje":   { "id": 103, "estacion": "pantalla - placas - técnica ó hermanado Placa - pantalla" },
    "CELDA 3 - Accesorios":{ "id": 104, "estacion": "balanza ó puesto 1" }
}
#Cada línea esta mapeada a su ID para hacer la consulta a la api, su primer puesto y su puesto de embalaje

X_XSRF_TOKEN, TOKEN, COOKIE = "", "", ""

# --- 2. FUNCIONES DE LÓGICA (EXCEL + API) ---

def encontrar_todos_los_lotes(ruta_archivo, nombre_hoja):
    try:
        df = pd.read_excel(ruta_archivo, sheet_name=nombre_hoja, header=14) #Con pandas leemos el Excel, la cabecera empieza en la fila 14, y busca el archivo en la dirección que le pasamos
        df.columns = df.columns.str.replace(r'\s+', ' ', regex=True).str.strip() #Normalizamos, esto elimina dobles espacios y espacios al principio o final de los nombres de columnas.
        
        if 'Cant.' in df.columns:
            df.rename(columns={'Cant.': 'Cant'}, inplace=True) #Si encuentra la columa Cant. la renombra sin punto

        col_fecha = 'Fecha Ing. Produccion'
        columnas_requeridas = [col_fecha, 'Modelo', 'Cant', 'Lote', 'OP']
        
        if not all(col in df.columns for col in columnas_requeridas):
            logging.warning(f"La hoja '{nombre_hoja}' no tiene las columnas requeridas: {columnas_requeridas}")
            return [] #Comprobamos que las columnas requeridas existen, si no, devolvemos una lista vacía.
            
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce') #Convertimos la fecha a un formato de fecha
        df.dropna(subset=[col_fecha, 'Modelo'], inplace=True)

        # Esto asegura que el plan de producción siempre está en orden cronológico.
        df.sort_values(by=col_fecha, inplace=True, kind='mergesort')
        df.reset_index(inplace=True, drop=True)
        
        macro_lotes = []
        current_pos = 0
        while current_pos < len(df):
            modelo_actual = df.iloc[current_pos]['Modelo'] #Iloc es integer location para la fila, buscamos el valor en la columna modelo
            end_pos = current_pos
            while end_pos + 1 < len(df) and df.iloc[end_pos + 1]['Modelo'] == modelo_actual:
                end_pos += 1
            
            lote_df = df.iloc[current_pos : end_pos + 1] #Creamos un DataFrame con las filas del lote actual
            micro_lotes = lote_df[['Lote', 'OP', 'Cant']].to_dict('records') #Lo convertimos a un diccionario de registros, cada registro es un micro lote con su Lote, OP y Cantidad.

            macro_lotes.append({
                "MODELO": modelo_actual,
                "FECHA_INICIO": lote_df[col_fecha].min().strftime('%d-%m-%Y'), #nos quedamos la más antigua
                "PRODUCCION_TOTAL": int(lote_df['Cant'].fillna(0).clip(lower=0).sum()), #fillna(0) remplaza celdas vacías por 0. Clip(lower=0) evita números negativos.
                "MICRO_LOTES": micro_lotes
            })
            current_pos = end_pos + 1
        return macro_lotes
    except Exception as e:
        logging.error(f"Fallo al procesar la hoja '{nombre_hoja}': {e}")
        return []

def login_jmmes():
    global X_XSRF_TOKEN, TOKEN, COOKIE
    try:
        get_token = requests.get(f"{API_MES}/api/XsrfToken", timeout=10)
        get_token.raise_for_status()
        antiforgery_token = get_token.cookies.get(".AspNetCore.Antiforgery.T8b4Fs--lAw")
        xsrf_token = get_token.cookies.get("XSRF-TOKEN")
        if not antiforgery_token or not xsrf_token: return False
        X_XSRF_TOKEN, COOKIE = xsrf_token, f".AspNetCore.Antiforgery.T8b4Fs--lAw={antiforgery_token}"
        headers = {"Content-Type": "application/json", "X-XSRF-TOKEN": xsrf_token, "Cookie": COOKIE}
        payload = json.dumps({"name": "lvela", "password": "1997"})
        r = requests.post(f"{API_MES}/api/User/Authenticate", data=payload, headers=headers, timeout=10)
        r.raise_for_status()
        TOKEN = r.json().get("token", "")
        return bool(TOKEN)
    except requests.exceptions.RequestException as e:
        logging.error(f"Fallo en el login: {e}")
        return False

def get_product_id(modelo, line_id): #Con el nombre del modelo y a qué línea pertenece, devuelve el ID del producto.
    if not TOKEN: return None
    url = f"{API_MES}/api/Products/GetByNameAndLineId/{modelo}/{line_id}"
    headers = {"X-XSRF-TOKEN": X_XSRF_TOKEN, "token": TOKEN}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200: return r.json().get("id")
        return None
    except requests.exceptions.RequestException: return None

def get_produced_quantity(product_id, line_id, fecha_inicio, line_name, station_key_name): #Con el ID del producto, la línea y la fecha de inicio, devuelve la cantidad producida.
    if not TOKEN: return 0
    # Esta función ahora obtiene la producción TOTAL del lote (desde su inicio hasta ahora)
    hora_fin_obj = datetime.now()
    hora_inicio_obj = datetime.strptime(fecha_inicio, '%d-%m-%Y').replace(hour=6, minute=0)
    return get_produced_quantity_en_intervalo(product_id, line_id, hora_inicio_obj, hora_fin_obj, line_name, station_key_name)

def get_produced_quantity_en_intervalo(product_id, line_id, start_time, end_time, line_name, station_key_name):
    """
    Función auxiliar para obtener la cantidad producida en un intervalo de tiempo específico.
    """
    if not TOKEN or not product_id: return 0
    
    headers = {"X-XSRF-TOKEN": X_XSRF_TOKEN, "token": TOKEN}
    fecha_api_inicio = start_time.strftime("%d-%m-%Y %H:%M").replace(" ", "%20")
    fecha_api_fin = end_time.strftime("%d-%m-%Y %H:%M").replace(" ", "%20")

    url = f"{API_MES}/api/producedQuantities/GetReport/1/{fecha_api_inicio}/{fecha_api_fin}"
    params = {"productId": product_id, "lineId": line_id}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if not data or not data[0]: return 0

            estaciones_data = data[0][0]
            target_station_names_str = LINE_MAP.get(line_name, {}).get(station_key_name)
            if not target_station_names_str: return 0

            possible_names = [e.strip().lower() for e in target_station_names_str.split("ó")]
            for est_info in estaciones_data:
                if est_info.get("stationGroupName", "").strip().lower() in possible_names:
                    return est_info.get("count", 0)
            return 0
        return 0
    except (requests.exceptions.RequestException, json.JSONDecodeError, IndexError, TypeError) as e:
        logging.error(f"Error en API call para intervalo: {e}")
        return 0

def obtener_datos_para_display():
    datos_finales_display = {}
    for nombre_hoja in NOMBRES_HOJAS: #Recorremos cada hoja de Excel (Lcd6, lcd8, celda 1, celda 2).
        todos_los_lotes = encontrar_todos_los_lotes(RUTA_EXCEL, nombre_hoja)
        if not todos_los_lotes: continue

        # 1. Encontrar el índice del último lote planificado para hoy o una fecha anterior.
        indice_teorico = -1
        for i, lote in enumerate(todos_los_lotes):
            fecha_lote = datetime.strptime(lote["FECHA_INICIO"], '%d-%m-%Y').date()
            if fecha_lote <= datetime.now().date():
                indice_teorico = i
        
        if indice_teorico == -1: continue

        # 2. Búsqueda con prioridades para encontrar el lote verdaderamente activo.
        indice_activo = -1
        prod1_activo = 0
        
        # Candidatos:
        indice_lote_en_progreso = -1
        prod1_lote_en_progreso = 0
        indice_lote_planeado = -1

        for i in range(indice_teorico, -1, -1):
            lote_candidato = todos_los_lotes[i]
            plan_candidato = lote_candidato.get("PRODUCCION_TOTAL", 0)
            if plan_candidato == 0: continue

            linea_m_candidata = f"{nombre_hoja} - Montaje"
            line_id_m_candidato = LINE_MAP.get(linea_m_candidata, {}).get("id")
            if not line_id_m_candidato: continue
            
            product_id_candidato = get_product_id(lote_candidato["MODELO"], line_id_m_candidato)
            if not product_id_candidato: continue

            producido_candidato = get_produced_quantity(product_id_candidato, line_id_m_candidato, lote_candidato["FECHA_INICIO"], linea_m_candidata, "estacion")

            if producido_candidato < plan_candidato:
                # PRIORIDAD 1: ¿El lote ya empezó?
                if producido_candidato > 0:
                    indice_lote_en_progreso = i
                    prod1_lote_en_progreso = producido_candidato
                    break # Encontramos el más importante, no necesitamos buscar más.
                
                # PRIORIDAD 2: ¿Es un lote planeado sin empezar?
                elif producido_candidato == 0 and indice_lote_planeado == -1:
                    # Solo guardamos el primero que encontramos (el más reciente).
                    indice_lote_planeado = i
        
        # 3. Decidir cuál lote mostrar según las prioridades.
        if indice_lote_en_progreso != -1:
            indice_activo = indice_lote_en_progreso
            prod1_activo = prod1_lote_en_progreso
            logging.info(f"Mostrando lote EN PROGRESO para '{nombre_hoja}': {todos_los_lotes[indice_activo]['MODELO']}")
        elif indice_lote_planeado != -1:
            indice_activo = indice_lote_planeado
            prod1_activo = 0
            logging.info(f"Mostrando lote PLANEADO para '{nombre_hoja}': {todos_los_lotes[indice_activo]['MODELO']}")
        else:
            indice_activo = indice_teorico # Fallback: todos los lotes pasados están completos.
            logging.warning(f"No se encontró lote activo para '{nombre_hoja}', mostrando el último teórico.")

        # 4. Preparar los datos para mostrar.
        lote_activo = todos_los_lotes[indice_activo]
        modelo_siguiente = todos_los_lotes[indice_activo + 1]["MODELO"] if indice_activo + 1 < len(todos_los_lotes) else "---"
        modelo, plan, fecha_inicio = lote_activo["MODELO"], lote_activo["PRODUCCION_TOTAL"], lote_activo["FECHA_INICIO"]
        
        linea_m, line_id_m = f"{nombre_hoja} - Montaje", LINE_MAP.get(f"{nombre_hoja} - Montaje", {}).get("id")
        linea_a, line_id_a = f"{nombre_hoja} - Accesorios", LINE_MAP.get(f"{nombre_hoja} - Accesorios", {}).get("id")
        prod_emb, prod_acc = 0, 0
        micro_lote_activo_info = {}
        tiempo_restante_str = "--:--"
        tiempo_restante_acc_str = "--:--"
        now = datetime.now()

        if line_id_m:
            product_id = get_product_id(modelo, line_id_m)
            if product_id:
                if "estacion_embalaje" in LINE_MAP.get(linea_m, {}):
                    prod_emb = get_produced_quantity(product_id, line_id_m, fecha_inicio, linea_m, "estacion_embalaje")
                
                start_of_shift = now.replace(hour=6, minute=0, second=0, microsecond=0)
                if now > start_of_shift:
                    end_time_window = now
                    start_time_window = now - timedelta(minutes=VENTANA_TIEMPO_MINUTOS)
                    produccion_ventana = get_produced_quantity_en_intervalo(product_id, line_id_m, start_time_window, end_time_window, linea_m, "estacion")
                    
                    if produccion_ventana > 0:
                        faltan_total = plan - prod1_activo
                        if faltan_total > 0:
                            segundos_en_ventana = VENTANA_TIEMPO_MINUTOS * 60
                            segundos_por_unidad = segundos_en_ventana / produccion_ventana
                            segundos_restantes = faltan_total * segundos_por_unidad
                            horas = int(segundos_restantes // 3600)
                            minutos = int((segundos_restantes % 3600) // 60)
                            tiempo_restante_str = f"{horas:02d}:{minutos:02d}"
                    else:
                        tiempo_restante_str = "Detenido"

                cantidad_acumulada = 0
                for micro_lote in lote_activo["MICRO_LOTES"]:
                    cantidad_acumulada += int(micro_lote.get('Cant', 0) or 0)
                    if prod1_activo < cantidad_acumulada:
                        faltante_micro_lote = cantidad_acumulada - prod1_activo
                        micro_lote_activo_info = {"LOTE": micro_lote['Lote'], "OP": micro_lote['OP'], "FALTAN_LOTE": faltante_micro_lote}
                        break
        
        if line_id_a:
            product_id_acc = get_product_id(modelo, line_id_a)
            if product_id_acc:
                fecha_inicio_obj = datetime.strptime(fecha_inicio, '%d-%m-%Y')
                fecha_inicio_accesorios = (fecha_inicio_obj - timedelta(days=1)).strftime('%d-%m-%Y')
                prod_acc = get_produced_quantity(product_id_acc, line_id_a, fecha_inicio_accesorios, linea_a, "estacion")

                # Lógica de estimación para Accesorios
                start_of_shift = now.replace(hour=6, minute=0, second=0, microsecond=0)
                if now > start_of_shift:
                    end_time_window = now
                    start_time_window = now - timedelta(minutes=VENTANA_TIEMPO_MINUTOS)
                    produccion_ventana_acc = get_produced_quantity_en_intervalo(product_id_acc, line_id_a, start_time_window, end_time_window, linea_a, "estacion")

                    if produccion_ventana_acc > 0:
                        faltan_total_acc = plan - prod_acc
                        if faltan_total_acc > 0:
                            segundos_en_ventana = VENTANA_TIEMPO_MINUTOS * 60
                            segundos_por_unidad_acc = segundos_en_ventana / produccion_ventana_acc
                            segundos_restantes_acc = faltan_total_acc * segundos_por_unidad_acc
                            horas = int(segundos_restantes_acc // 3600)
                            minutos = int((segundos_restantes_acc % 3600) // 60)
                            tiempo_restante_acc_str = f"{horas:02d}:{minutos:02d}"
                    else:
                        tiempo_restante_acc_str = "Detenido"
        
        datos_finales_display[nombre_hoja] = {
            "MODELO": modelo, "PLAN": plan, "MODELO_SIGUIENTE": modelo_siguiente,
            "PROD1": prod1_activo, "FALTAN1": plan - prod1_activo,
            "PROD_EMB": prod_emb, "FALTAN_EMB": plan - prod_emb,
            "PROD_ACC": prod_acc, "FALTAN_ACC": plan - prod_acc,
            "MICRO_LOTE_INFO": micro_lote_activo_info,
            "TIEMPO_RESTANTE": tiempo_restante_str,
            "TIEMPO_RESTANTE_ACC": tiempo_restante_acc_str
        }
    return datos_finales_display

# --- 3. CLASE DE LA INTERFAZ GRÁFICA (TKINTER) ---
class VentanaInfo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tablero de Faltantes")
        self.geometry("1200x700") 
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.initial_width, self.initial_height = 1200, 700 
        self.bind("<Configure>", self.on_resize)
        self.container = tk.Frame(self, bg="black")
        self.container.pack(expand=True, fill="both", padx=5, pady=5)
        self.datos_display, self.ui_elements = {}, {}
        self.secciones = ["LCD6", "LCD8", "CELDA 1", "CELDA 2", "CELDA 3"]
        
        login_thread = threading.Thread(target=login_jmmes, daemon=True)
        login_thread.start()
        login_thread.join(timeout=5) # Esperar un máximo de 5 segundos a que el login termine
        
        self.construir_interfaz()
        self.actualizar_datos_en_hilo()

    def construir_interfaz(self):
        for widget in self.container.winfo_children(): widget.destroy()
        self.ui_elements.clear()
        
        # 3 columnas y 2 filas
        for i in range(3): self.container.grid_columnconfigure(i, weight=1)
        for i in range(2): self.container.grid_rowconfigure(i, weight=1)

        for i, seccion in enumerate(self.secciones):
            frame = tk.LabelFrame(self.container, text=seccion, font=("Arial", 14, "bold"), bg="#333333", fg="white", padx=10, pady=10)
            frame.grid(row=i//3, column=i%3, sticky="nsew", padx=5, pady=5)
            
            # --- SECCIÓN MONTAJE ---
            lbl_m_modelo = ttk.Label(frame, text="Montaje: ---", font=("Arial", 12, "bold"), background="#333333", foreground="cyan")
            lbl_m_modelo.pack(anchor="w")

            lbl_m_prod1 = ttk.Label(frame, text="Producidos (Est. 1): ---", font=("Arial", 11, "normal"), background="#333333", foreground="white")
            lbl_m_prod1.pack(anchor="w")

            faltan1_frame = tk.Frame(frame, bg="#333333")
            faltan1_frame.pack(anchor="w", fill="x")
            lbl_m_faltan1 = ttk.Label(faltan1_frame, text="Faltan (Est. 1): ---", font=("Arial", 11, "bold"), background="#333333", foreground="yellow")
            lbl_m_faltan1.pack(side="left")
            lbl_m_estimativo = ttk.Label(faltan1_frame, text="(Estim: --:--)", font=("Arial", 10, "italic"), background="#333333", foreground="orange")
            lbl_m_estimativo.pack(side="left", padx=(10, 0))
            
            lbl_m_prod_emb = ttk.Label(frame, font=("Arial", 11, "normal"), background="#333333", foreground="white")
            lbl_m_prod_emb.pack(anchor="w", pady=(5,0))
            lbl_m_faltan_emb = ttk.Label(frame, font=("Arial", 11, "bold"), background="#333333", foreground="yellow")
            lbl_m_faltan_emb.pack(anchor="w")

            sep_lote = ttk.Separator(frame, orient='horizontal')
            sep_lote.pack(fill='x', pady=5)
            lbl_lote_op = ttk.Label(frame, text="Lote / OP: --- / ---", font=("Arial", 10, "bold"), background="#333333", foreground="white")
            lbl_lote_op.pack(anchor="w")
            lbl_lote_faltan = ttk.Label(frame, text="Faltan del Lote: ---", font=("Arial", 10, "bold"), background="#333333", foreground="orange")
            lbl_lote_faltan.pack(anchor="w")
            
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            
            # --- SECCIÓN ACCESORIOS ---
            lbl_a_modelo = ttk.Label(frame, text="Accesorios: ---", font=("Arial", 12, "bold"), background="#333333", foreground="cyan")
            lbl_a_modelo.pack(anchor="w")
            lbl_a_prod = ttk.Label(frame, text="Producidos: ---", font=("Arial", 11, "normal"), background="#333333", foreground="white")
            lbl_a_prod.pack(anchor="w")
            
            faltan_acc_frame = tk.Frame(frame, bg="#333333")
            faltan_acc_frame.pack(anchor="w", fill="x")
            lbl_a_faltan = ttk.Label(faltan_acc_frame, text="Faltan: ---", font=("Arial", 11, "bold"), background="#333333", foreground="yellow")
            lbl_a_faltan.pack(side="left")
            lbl_a_estimativo = ttk.Label(faltan_acc_frame, text="(Estim: --:--)", font=("Arial", 10, "italic"), background="#333333", foreground="orange")
            lbl_a_estimativo.pack(side="left", padx=(10,0))
            
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            
            lbl_siguiente = ttk.Label(frame, text="Siguiente: ---", font=("Arial", 10, "italic"), background="#333333", foreground="#cccccc")
            lbl_siguiente.pack(anchor="w", pady=(5,0))
            
            self.ui_elements[seccion] = {
                "MONTAJE_MODELO": lbl_m_modelo, "MONTAJE_PROD1": lbl_m_prod1, "MONTAJE_FALTAN1": lbl_m_faltan1,
                "MONTAJE_PROD_EMB": lbl_m_prod_emb, "MONTAJE_FALTAN_EMB": lbl_m_faltan_emb,
                "SEP_LOTE": sep_lote, "LOTE_OP": lbl_lote_op, "LOTE_FALTAN": lbl_lote_faltan,
                "ACC_MODELO": lbl_a_modelo, "ACC_PROD": lbl_a_prod, "ACC_FALTAN": lbl_a_faltan,
                "SIGUIENTE_MODELO": lbl_siguiente,
                "MONTAJE_ESTIMATIVO": lbl_m_estimativo,
                "ACC_ESTIMATIVO": lbl_a_estimativo
            }

    def on_resize(self, event):
        if not hasattr(self, 'initial_width') or not self.ui_elements:
            return
            
        scale = min(self.winfo_width() / self.initial_width, self.winfo_height() / self.initial_height)
        new_frame_font_size = max(10, int(14 * scale))
        new_model_font_size = max(9, int(12 * scale))
        new_data_font_size = max(8, int(11 * scale))
        new_lote_font_size = max(8, int(10 * scale))
        new_next_font_size = max(7, int(10 * scale))
        new_estim_font_size = max(7, int(10 * scale))

        for seccion, elements in self.ui_elements.items():
            frame_widget = self.container.nametowidget(elements["MONTAJE_MODELO"].winfo_parent())
            if isinstance(frame_widget, tk.LabelFrame):
                frame_widget.config(font=("Arial", new_frame_font_size, "bold"))

            elements["MONTAJE_MODELO"].config(font=("Arial", new_model_font_size, "bold"))
            elements["ACC_MODELO"].config(font=("Arial", new_model_font_size, "bold"))
            elements["MONTAJE_PROD1"].config(font=("Arial", new_data_font_size, "normal"))
            elements["MONTAJE_FALTAN1"].config(font=("Arial", new_data_font_size, "bold"))
            elements["MONTAJE_PROD_EMB"].config(font=("Arial", new_data_font_size, "normal"))
            elements["MONTAJE_FALTAN_EMB"].config(font=("Arial", new_data_font_size, "bold"))
            elements["LOTE_OP"].config(font=("Arial", new_lote_font_size, "bold"))
            elements["LOTE_FALTAN"].config(font=("Arial", new_lote_font_size, "bold"))
            elements["ACC_PROD"].config(font=("Arial", new_data_font_size, "normal"))
            elements["ACC_FALTAN"].config(font=("Arial", new_data_font_size, "bold"))
            elements["SIGUIENTE_MODELO"].config(font=("Arial", new_next_font_size, "italic"))
            elements["MONTAJE_ESTIMATIVO"].config(font=("Arial", new_estim_font_size, "italic"))
            elements["ACC_ESTIMATIVO"].config(font=("Arial", new_estim_font_size, "italic"))

    def actualizar_textos_ui(self):
        for seccion, elements in self.ui_elements.items():
            if not isinstance(elements, dict): continue
            
            datos = self.datos_display.get(seccion)
            
            if datos:
                # Actualizar Montaje
                elements["MONTAJE_MODELO"].config(text=f"Montaje: {datos['MODELO']}")
                elements["MONTAJE_PROD1"].config(text=f"Producidos (Est. 1): {datos['PROD1']}")
                elements["MONTAJE_FALTAN1"].config(text=f"Faltan (Est. 1): {datos['FALTAN1']}")
                
                tiempo_restante = datos.get('TIEMPO_RESTANTE', '--:--')
                color = "orange"
                if tiempo_restante == "Detenido":
                    color = "red"
                elements["MONTAJE_ESTIMATIVO"].config(text=f"(Estim: {tiempo_restante})", foreground=color)

                if "estacion_embalaje" in LINE_MAP.get(f"{seccion} - Montaje", {}):
                    elements["MONTAJE_PROD_EMB"].pack(anchor="w", pady=(5,0))
                    elements["MONTAJE_FALTAN_EMB"].pack(anchor="w")
                    elements["MONTAJE_PROD_EMB"].config(text=f"Producidos (Emb.): {datos['PROD_EMB']}")
                    elements["MONTAJE_FALTAN_EMB"].config(text=f"Faltan (Emb.): {datos['FALTAN_EMB']}")
                else:
                    elements["MONTAJE_PROD_EMB"].pack_forget()
                    elements["MONTAJE_FALTAN_EMB"].pack_forget()

                micro_lote = datos.get("MICRO_LOTE_INFO", {})
                if micro_lote and micro_lote.get("LOTE") is not None:
                    elements["LOTE_OP"].config(text=f"Lote / OP: {micro_lote.get('LOTE', 'N/A')} / {micro_lote.get('OP', 'N/A')}")
                    elements["LOTE_FALTAN"].config(text=f"Faltan del Lote: {micro_lote.get('FALTAN_LOTE', 'N/A')}")
                else:
                    elements["LOTE_OP"].config(text="Lote / OP: ---")
                    elements["LOTE_FALTAN"].config(text="Faltan del Lote: ---")

                # Actualizar Accesorios
                elements["ACC_MODELO"].config(text=f"Accesorios: {datos['MODELO']}")
                elements["ACC_PROD"].config(text=f"Producidos: {datos['PROD_ACC']}")
                elements["ACC_FALTAN"].config(text=f"Faltan: {datos['FALTAN_ACC']}")
                
                tiempo_restante_acc = datos.get('TIEMPO_RESTANTE_ACC', '--:--')
                color_acc = "orange"
                if tiempo_restante_acc == "Detenido":
                    color_acc = "red"
                elements["ACC_ESTIMATIVO"].config(text=f"(Estim: {tiempo_restante_acc})", foreground=color_acc)

                elements["SIGUIENTE_MODELO"].config(text=f"Siguiente: {datos['MODELO_SIGUIENTE']}")
            else:
                for label_key, label in elements.items():
                    if isinstance(label, ttk.Label):
                        if "ESTIMATIVO" in label_key:
                           label.config(text="(Estim: --:--)")
                        else:
                            original_text = label.cget("text").split(':')[0]
                            label.config(text=original_text + ": ---")

    def ciclo_de_actualizacion(self):
        while True:
            try:
                logging.info("Iniciando ciclo de actualización de datos...")
                nuevos_datos = obtener_datos_para_display()
                self.datos_display = nuevos_datos
                self.after(0, self.actualizar_textos_ui)
            except Exception as e:
                logging.error(f"Error en el ciclo de actualización: {e}", exc_info=True)
            time.sleep(30)

    def actualizar_datos_en_hilo(self):
        thread = threading.Thread(target=self.ciclo_de_actualizacion, daemon=True)
        thread.start()

if __name__ == "__main__":
    app = VentanaInfo()
    app.mainloop()