import tkinter as tk
from tkinter import ttk, font
import pandas as pd
import requests
import json
from datetime import datetime
import threading
import time
import logging

# --- 1. CONFIGURACIÓN Y CONSTANTES GLOBALES ---
#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')

API_MES = "http://mes.newsan.com.ar"
RUTA_EXCEL = r'\\ush-nt-3\v1\infprod\PLAN_PRO\Programas de producción x planta\Programa P5 - 2025.xlsx'
NOMBRES_HOJAS = ['LCD6', 'LCD8', 'CELDA 1', 'CELDA 2']

LINE_MAP = {
    "LCD6 - Montaje":       { "id": 3, "estacion": "hermanado placa - pantalla", "estacion_embalaje": "Embalaje" },
    "LCD6 - Accesorios":    { "id": 14, "estacion": "puesto 1" },
    "LCD8 - Montaje":       { "id": 10, "estacion": "pantalla - placa 1", "estacion_embalaje": "Embalaje" },
    "LCD8 - Accesorios":    { "id": 9, "estacion": "balanza ó puesto 1" },
    "CELDA 1 - Montaje":    { "id": 13, "estacion": "pantalla - placa 1 ó pantalla - placa 1 ó pantalla - placas - técnica ó hermanado placa - pantalla" },
    "CELDA 1 - Accesorios": { "id": 12, "estacion": "balanza ó puesto 1" },
    "CELDA 2 - Montaje":    { "id": 82, "estacion": "pantalla - placas - técnica ó hermanado Placa - pantalla" },
    "CELDA 2 - Accesorios": { "id": 83, "estacion": "balanza ó puesto 1" }
}

X_XSRF_TOKEN, TOKEN, COOKIE = "", "", ""

# --- 2. FUNCIONES DE LÓGICA (EXCEL + API) ---

def encontrar_lotes_de_produccion(ruta_archivo, nombres_hojas, fecha_referencia):
    datos_por_linea = {}
    try:
        xls = pd.ExcelFile(ruta_archivo)
    except Exception as e:
        logging.error(f"No se pudo abrir el archivo Excel: {e}")
        return {}

    for nombre_linea in nombres_hojas:
        try:
            df = pd.read_excel(xls, sheet_name=nombre_linea, header=14)
            df.columns = df.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
            col_fecha = 'Fecha Ing. Produccion'
            if not all(col in df.columns for col in [col_fecha, 'Modelo', 'Cant.']): continue
            
            df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
            df.dropna(subset=[col_fecha, 'Modelo'], inplace=True)
            df.reset_index(inplace=True, drop=True)
            if df.empty: continue

            indices_candidatos = df.index[df[col_fecha] <= fecha_referencia]
            start_index = 0
            if len(indices_candidatos) > 0:
                df_candidatos = df.loc[indices_candidatos]
                fecha_mas_reciente = df_candidatos[col_fecha].max()
                indices_en_fecha = df_candidatos.index[df_candidatos[col_fecha] == fecha_mas_reciente]
                if len(indices_en_fecha) > 0:
                    start_index = indices_en_fecha.min()

            
            # Ahora, desde este punto de inicio, buscamos hacia atrás para encontrar el verdadero inicio del lote
            modelo_de_inicio = df.iloc[start_index]['Modelo']
            true_start_of_current_lot = start_index
            while true_start_of_current_lot > 0 and df.iloc[true_start_of_current_lot - 1]['Modelo'] == modelo_de_inicio:
                true_start_of_current_lot -= 1

            # Procesamos todos los lotes desde el inicio real del lote actual hacia adelante
            lotes_futuros = []
            current_pos = true_start_of_current_lot
            while current_pos < len(df):
                modelo_actual = df.iloc[current_pos]['Modelo']
                end_pos = current_pos
                while end_pos + 1 < len(df) and df.iloc[end_pos + 1]['Modelo'] == modelo_actual:
                    end_pos += 1
                
                lote_df = df.iloc[current_pos : end_pos + 1]
                fecha_inicio_lote = lote_df[col_fecha].min().strftime('%d-%m-%Y')
                produccion_total_lote = int(lote_df['Cant.'].fillna(0).clip(lower=0).sum())
                lotes_futuros.append({
                    "LINEA_BASE": nombre_linea, "MODELO": modelo_actual,
                    "FECHA_INICIO": fecha_inicio_lote,
                    "PRODUCCION_TOTAL": produccion_total_lote
                })
                current_pos = end_pos + 1
            
            datos_por_linea[nombre_linea] = lotes_futuros
        except Exception as e:
            logging.error(f"Fallo al procesar la hoja '{nombre_linea}': {e}", exc_info=True)
            continue
    return datos_por_linea

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
    except requests.exceptions.RequestException: return False

def get_product_id(modelo, line_id):
    if not TOKEN: return None
    url = f"{API_MES}/api/Products/GetByNameAndLineId/{modelo}/{line_id}"
    headers = {"X-XSRF-TOKEN": X_XSRF_TOKEN, "token": TOKEN}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200: return r.json().get("id")
        return None
    except requests.exceptions.RequestException: return None

def get_produced_quantity(product_id, line_id, fecha_inicio, line_name, station_key_name):
    if not TOKEN: return 0
    headers = {"X-XSRF-TOKEN": X_XSRF_TOKEN, "token": TOKEN}
    fecha_fin = datetime.now().strftime("%d-%m-%Y %H:%M").replace(" ", "%20")
    fecha_api = f"{fecha_inicio} 06:00".replace(' ', '%20')
    url = f"{API_MES}/api/producedQuantities/GetReport/1/{fecha_api}/{fecha_fin}"
    params = {"productId": product_id, "lineId": line_id}
    
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            estaciones_data = data[0][0]
            target_station_names_str = LINE_MAP.get(line_name, {}).get(station_key_name)
            if not target_station_names_str: return 0
            possible_names = [e.strip().lower() for e in target_station_names_str.split("ó")]
            for est_info in estaciones_data:
                if est_info.get("stationGroupName", "").strip().lower() in possible_names:
                    cantidad = est_info.get("count", 0)
                    logging.info(f"API retornó para '{station_key_name}': {cantidad}")
                    return cantidad
            return 0
        return 0
    except (requests.exceptions.RequestException, json.JSONDecodeError, IndexError, TypeError): return 0

def obtener_datos_para_display():
    lotes_por_linea = encontrar_lotes_de_produccion(RUTA_EXCEL, NOMBRES_HOJAS, datetime.now())
    datos_finales_display = {}

    for linea_base, cola_lotes in lotes_por_linea.items():
        lote_activo = None
        modelo_siguiente = "---"
        
        logging.info(f"Evaluando cola para '{linea_base}' con {len(cola_lotes)} lotes futuros...")
        for i, lote_candidato in enumerate(cola_lotes):
            planificado = lote_candidato["PRODUCCION_TOTAL"]
            linea_m_candidata = f"{linea_base} - Montaje"
            line_id_m_candidato = LINE_MAP.get(linea_m_candidata, {}).get("id")
            
            producido_total = 0
            if line_id_m_candidato:
                product_id = get_product_id(lote_candidato["MODELO"], line_id_m_candidato)
                if product_id:
                    producido_total = get_produced_quantity(product_id, line_id_m_candidato, lote_candidato["FECHA_INICIO"], linea_m_candidata, "estacion")

            faltante = planificado - producido_total

            if faltante > 0:
                lote_activo = lote_candidato
                if i + 1 < len(cola_lotes):
                    modelo_siguiente = cola_lotes[i+1]["MODELO"]
                logging.info(f"Lote activo para '{linea_base}' es {lote_activo['MODELO']} que inicia en {lote_activo['FECHA_INICIO']}")
                break
        
        if not lote_activo and cola_lotes:
            lote_activo = cola_lotes[-1]

        if lote_activo:
            modelo, plan, fecha_inicio = lote_activo["MODELO"], lote_activo["PRODUCCION_TOTAL"], lote_activo["FECHA_INICIO"]
            linea_m, line_id_m = f"{linea_base} - Montaje", LINE_MAP.get(f"{linea_base} - Montaje", {}).get("id")
            linea_a, line_id_a = f"{linea_base} - Accesorios", LINE_MAP.get(f"{linea_base} - Accesorios", {}).get("id")
            
            prod1, prod_emb, prod_acc = 0, 0, 0
            if line_id_m:
                product_id = get_product_id(modelo, line_id_m)
                if product_id:
                    prod1 = get_produced_quantity(product_id, line_id_m, fecha_inicio, linea_m, "estacion")
                    if "estacion_embalaje" in LINE_MAP.get(linea_m, {}):
                        prod_emb = get_produced_quantity(product_id, line_id_m, fecha_inicio, linea_m, "estacion_embalaje")
            if line_id_a:
                product_id_acc = get_product_id(modelo, line_id_a)
                if product_id_acc:
                    prod_acc = get_produced_quantity(product_id_acc, line_id_a, fecha_inicio, linea_a, "estacion")
            
            datos_finales_display[linea_base] = {
                "MODELO": modelo, "PLAN": plan, "MODELO_SIGUIENTE": modelo_siguiente,
                "PROD1": prod1, "FALTAN1": plan - prod1,
                "PROD_EMB": prod_emb, "FALTAN_EMB": plan - prod_emb,
                "PROD_ACC": prod_acc, "FALTAN_ACC": plan - prod_acc
            }
    return datos_finales_display

# --- 3. CLASE DE LA INTERFAZ GRÁFICA (TKINTER) ---
class VentanaInfo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tablero de Faltantes")
        self.geometry("700x650")
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.initial_width = 700
        self.initial_height = 650
        self.bind("<Configure>", self.on_resize)
        self.container = tk.Frame(self, bg="black")
        self.container.pack(expand=True, fill="both", padx=5, pady=5)
        self.datos_display = {}
        self.ui_elements = {}
        self.secciones = ["LCD6", "LCD8", "CELDA 1", "CELDA 2"]
        threading.Thread(target=login_jmmes, daemon=True).start()
        time.sleep(2)
        self.construir_interfaz()
        self.actualizar_datos_en_hilo()

    def construir_interfaz(self):
        for widget in self.container.winfo_children(): widget.destroy()
        self.ui_elements.clear()
        for i in range(2): self.container.grid_columnconfigure(i, weight=1)
        for i in range(2): self.container.grid_rowconfigure(i, weight=1)

        for i, seccion in enumerate(self.secciones):
            frame = tk.LabelFrame(self.container, text=seccion, font=("Arial", 14, "bold"), bg="#333333", fg="white", padx=10, pady=10)
            frame.grid(row=i//2, column=i%2, sticky="nsew", padx=5, pady=5)
            self.ui_elements[f"{seccion}_FRAME"] = frame
            
            lbl_m_modelo = ttk.Label(frame, text="Montaje: ---", font=("Arial", 12, "bold"), background="#333333", foreground="cyan")
            lbl_m_modelo.pack(anchor="w")
            lbl_m_prod1 = ttk.Label(frame, text="Producidos (Est. 1): ---", font=("Arial", 11, "normal"), background="#333333", foreground="white")
            lbl_m_prod1.pack(anchor="w")
            lbl_m_faltan1 = ttk.Label(frame, text="Faltan (Est. 1): ---", font=("Arial", 11, "bold"), background="#333333", foreground="yellow")
            lbl_m_faltan1.pack(anchor="w")
            
            lbl_m_prod_emb = ttk.Label(frame, font=("Arial", 11, "normal"), background="#333333", foreground="white")
            lbl_m_prod_emb.pack(anchor="w", pady=(5,0))
            lbl_m_faltan_emb = ttk.Label(frame, font=("Arial", 11, "bold"), background="#333333", foreground="yellow")
            lbl_m_faltan_emb.pack(anchor="w")
            
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            
            lbl_a_modelo = ttk.Label(frame, text="Accesorios: ---", font=("Arial", 12, "bold"), background="#333333", foreground="cyan")
            lbl_a_modelo.pack(anchor="w")
            lbl_a_prod = ttk.Label(frame, text="Producidos: ---", font=("Arial", 11, "normal"), background="#333333", foreground="white")
            lbl_a_prod.pack(anchor="w")
            lbl_a_faltan = ttk.Label(frame, text="Faltan: ---", font=("Arial", 11, "bold"), background="#333333", foreground="yellow")
            lbl_a_faltan.pack(anchor="w")
            
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            
            lbl_siguiente = ttk.Label(frame, text="Siguiente: ---", font=("Arial", 10, "italic"), background="#333333", foreground="#cccccc")
            lbl_siguiente.pack(anchor="w", pady=(5,0))
            
            self.ui_elements[seccion] = {
                "MONTAJE_MODELO": lbl_m_modelo, "MONTAJE_PROD1": lbl_m_prod1, "MONTAJE_FALTAN1": lbl_m_faltan1,
                "MONTAJE_PROD_EMB": lbl_m_prod_emb, "MONTAJE_FALTAN_EMB": lbl_m_faltan_emb,
                "ACC_MODELO": lbl_a_modelo, "ACC_PROD": lbl_a_prod, "ACC_FALTAN": lbl_a_faltan,
                "SIGUIENTE_MODELO": lbl_siguiente
            }

    def on_resize(self, event):
        scale = min(self.winfo_width() / self.initial_width, self.winfo_height() / self.initial_height)
        new_frame_font_size = max(10, int(14 * scale))
        new_model_font_size = max(9, int(12 * scale))
        new_data_font_size = max(8, int(11 * scale))
        new_next_font_size = max(7, int(10 * scale))
        for element in self.ui_elements.values():
            if isinstance(element, tk.LabelFrame): element.config(font=("Arial", new_frame_font_size, "bold"))
            elif isinstance(element, dict):
                element["MONTAJE_MODELO"].config(font=("Arial", new_model_font_size, "bold"))
                element["ACC_MODELO"].config(font=("Arial", new_model_font_size, "bold"))
                element["MONTAJE_PROD1"].config(font=("Arial", new_data_font_size, "normal"))
                element["MONTAJE_FALTAN1"].config(font=("Arial", new_data_font_size, "bold"))
                element["MONTAJE_PROD_EMB"].config(font=("Arial", new_data_font_size, "normal"))
                element["MONTAJE_FALTAN_EMB"].config(font=("Arial", new_data_font_size, "bold"))
                element["ACC_PROD"].config(font=("Arial", new_data_font_size, "normal"))
                element["ACC_FALTAN"].config(font=("Arial", new_data_font_size, "bold"))
                element["SIGUIENTE_MODELO"].config(font=("Arial", new_next_font_size, "italic"))

    def actualizar_textos_ui(self):
        for seccion, elements in self.ui_elements.items():
            if not isinstance(elements, dict): continue
            
            datos = self.datos_display.get(seccion)
            
            if datos:
                elements["MONTAJE_MODELO"].config(text=f"Montaje: {datos['MODELO']}")
                elements["MONTAJE_PROD1"].config(text=f"Producidos (Est. 1): {datos['PROD1']}")
                elements["MONTAJE_FALTAN1"].config(text=f"Faltan (Est. 1): {datos['FALTAN1']}")
                
                linea_m_ref = f"{seccion} - Montaje"
                if "estacion_embalaje" in LINE_MAP.get(linea_m_ref, {}):
                    elements["MONTAJE_PROD_EMB"].pack(anchor="w", pady=(5,0))
                    elements["MONTAJE_FALTAN_EMB"].pack(anchor="w")
                    elements["MONTAJE_PROD_EMB"].config(text=f"Producidos (Emb.): {datos['PROD_EMB']}")
                    elements["MONTAJE_FALTAN_EMB"].config(text=f"Faltan (Emb.): {datos['FALTAN_EMB']}")
                else:
                    elements["MONTAJE_PROD_EMB"].pack_forget()
                    elements["MONTAJE_FALTAN_EMB"].pack_forget()

                elements["ACC_MODELO"].config(text=f"Accesorios: {datos['MODELO']}")
                elements["ACC_PROD"].config(text=f"Producidos: {datos['PROD_ACC']}")
                elements["ACC_FALTAN"].config(text=f"Faltan: {datos['FALTAN_ACC']}")
                elements["SIGUIENTE_MODELO"].config(text=f"Siguiente: {datos['MODELO_SIGUIENTE']}")
            else:
                for label in elements.values():
                    if isinstance(label, ttk.Label):
                        original_text = label.cget("text").split(':')[0]
                        label.config(text=original_text + ": ---")

    def ciclo_de_actualizacion(self):
        while True:
            try:
                #logging.info("Iniciando ciclo de actualización de datos...")
                nuevos_datos = obtener_datos_para_display()
                if nuevos_datos != self.datos_display:
                    self.datos_display = nuevos_datos
                    #logging.info(f"Nuevos datos de planificación encontrados: {self.datos_display}")
                    self.after(0, self.actualizar_textos_ui)
                else:
                    #logging.info("No hay cambios en la planificación activa. Refrescando datos de producción...")
                    self.after(0, self.actualizar_textos_ui)
            except Exception as e:
                logging.error(f"Error en el ciclo de actualización: {e}", exc_info=True)
            time.sleep(30)

    def actualizar_datos_en_hilo(self):
        thread = threading.Thread(target=self.ciclo_de_actualizacion, daemon=True)
        thread.start()

# --- 4. PUNTO DE ENTRADA DE LA APLICACIÓN ---
if __name__ == "__main__":
    app = VentanaInfo()
    app.mainloop()