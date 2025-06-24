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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')

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

def encontrar_todos_los_lotes(ruta_archivo, nombre_hoja):
    try:
        df = pd.read_excel(ruta_archivo, sheet_name=nombre_hoja, header=14)
        df.columns = df.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        if 'Cant.' in df.columns:
            df.rename(columns={'Cant.': 'Cant'}, inplace=True)

        col_fecha = 'Fecha Ing. Produccion'
        columnas_requeridas = [col_fecha, 'Modelo', 'Cant', 'Lote', 'PO']
        
        if not all(col in df.columns for col in columnas_requeridas):
            logging.warning(f"La hoja '{nombre_hoja}' no tiene todas las columnas requeridas.")
            logging.warning(f"Se necesitan: {columnas_requeridas}")
            logging.warning(f"Se encontraron: {list(df.columns)}")
            return []
            
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
        df.dropna(subset=[col_fecha, 'Modelo'], inplace=True)
        df.reset_index(inplace=True, drop=True)
        
        macro_lotes = []
        current_pos = 0
        while current_pos < len(df):
            modelo_actual = df.iloc[current_pos]['Modelo']
            end_pos = current_pos
            while end_pos + 1 < len(df) and df.iloc[end_pos + 1]['Modelo'] == modelo_actual:
                end_pos += 1
            
            lote_df = df.iloc[current_pos : end_pos + 1]
            micro_lotes = lote_df[['Lote', 'PO', 'Cant']].to_dict('records')

            macro_lotes.append({
                "MODELO": modelo_actual,
                "FECHA_INICIO": lote_df[col_fecha].min().strftime('%d-%m-%Y'),
                "PRODUCCION_TOTAL": int(lote_df['Cant'].fillna(0).clip(lower=0).sum()),
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
                    return est_info.get("count", 0)
            return 0
        return 0
    except (requests.exceptions.RequestException, json.JSONDecodeError, IndexError, TypeError): return 0

def obtener_datos_para_display():
    datos_finales_display = {}
    for nombre_hoja in NOMBRES_HOJAS:
        todos_los_lotes = encontrar_todos_los_lotes(RUTA_EXCEL, nombre_hoja)
        if not todos_los_lotes: continue

        indice_teorico = -1
        fecha_mas_cercana = datetime.min
        for i, lote in enumerate(todos_los_lotes):
            fecha_lote = datetime.strptime(lote["FECHA_INICIO"], '%d-%m-%Y')
            if fecha_lote.date() <= datetime.now().date() and fecha_lote >= fecha_mas_cercana:
                fecha_mas_cercana = fecha_lote
                indice_teorico = i
        
        if indice_teorico == -1: continue

        lote_teorico = todos_los_lotes[indice_teorico]
        linea_m_teorica = f"{nombre_hoja} - Montaje"
        line_id_m_teorico = LINE_MAP.get(linea_m_teorica, {}).get("id")
        producido_teorico = 0
        if line_id_m_teorico:
            product_id_teorico = get_product_id(lote_teorico["MODELO"], line_id_m_teorico)
            if product_id_teorico:
                producido_teorico = get_produced_quantity(product_id_teorico, line_id_m_teorico, lote_teorico["FECHA_INICIO"], linea_m_teorica, "estacion")

        indice_activo = indice_teorico
        if producido_teorico == 0 and indice_teorico > 0:
            indice_activo = indice_teorico - 1
        
        lote_activo = todos_los_lotes[indice_activo]
        modelo_siguiente = todos_los_lotes[indice_activo + 1]["MODELO"] if indice_activo + 1 < len(todos_los_lotes) else "---"

        modelo, plan, fecha_inicio = lote_activo["MODELO"], lote_activo["PRODUCCION_TOTAL"], lote_activo["FECHA_INICIO"]
        linea_m, line_id_m = f"{nombre_hoja} - Montaje", LINE_MAP.get(f"{nombre_hoja} - Montaje", {}).get("id")
        linea_a, line_id_a = f"{nombre_hoja} - Accesorios", LINE_MAP.get(f"{nombre_hoja} - Accesorios", {}).get("id")
        
        prod1, prod_emb, prod_acc = 0, 0, 0
        micro_lote_activo_info = {}
        if line_id_m:
            product_id = get_product_id(modelo, line_id_m)
            if product_id:
                prod1 = get_produced_quantity(product_id, line_id_m, fecha_inicio, linea_m, "estacion")
                if "estacion_embalaje" in LINE_MAP.get(linea_m, {}):
                    prod_emb = get_produced_quantity(product_id, line_id_m, fecha_inicio, linea_m, "estacion_embalaje")
                
                cantidad_acumulada = 0
                for micro_lote in lote_activo["MICRO_LOTES"]:
                    cantidad_acumulada += int(micro_lote.get('Cant', 0) or 0)
                    if prod1 < cantidad_acumulada:
                        faltante_micro_lote = cantidad_acumulada - prod1
                        micro_lote_activo_info = {"LOTE": micro_lote['Lote'], "PO": micro_lote['PO'], "FALTAN_LOTE": faltante_micro_lote}
                        break
        
        if line_id_a:
            product_id_acc = get_product_id(modelo, line_id_a)
            if product_id_acc:
                prod_acc = get_produced_quantity(product_id_acc, line_id_a, fecha_inicio, linea_a, "estacion")
        
        datos_finales_display[nombre_hoja] = {
            "MODELO": modelo, "PLAN": plan, "MODELO_SIGUIENTE": modelo_siguiente,
            "PROD1": prod1, "FALTAN1": plan - prod1,
            "PROD_EMB": prod_emb, "FALTAN_EMB": plan - prod_emb,
            "PROD_ACC": prod_acc, "FALTAN_ACC": plan - prod_acc,
            "MICRO_LOTE_INFO": micro_lote_activo_info
        }
    return datos_finales_display

# --- 3. CLASE DE LA INTERFAZ GRÁFICA (TKINTER) ---
class VentanaInfo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tablero de Faltantes")
        self.geometry("800x750")
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.initial_width, self.initial_height = 800, 750
        self.bind("<Configure>", self.on_resize)
        self.container = tk.Frame(self, bg="black")
        self.container.pack(expand=True, fill="both", padx=5, pady=5)
        self.datos_display, self.ui_elements = {}, {}
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

            sep_lote = ttk.Separator(frame, orient='horizontal')
            sep_lote.pack(fill='x', pady=5)
            lbl_lote_po = ttk.Label(frame, text="Lote / PO: --- / ---", font=("Arial", 10, "bold"), background="#333333", foreground="white")
            lbl_lote_po.pack(anchor="w")
            lbl_lote_faltan = ttk.Label(frame, text="Faltan del Lote: ---", font=("Arial", 10, "bold"), background="#333333", foreground="orange")
            lbl_lote_faltan.pack(anchor="w")
            
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
                "SEP_LOTE": sep_lote, "LOTE_PO": lbl_lote_po, "LOTE_FALTAN": lbl_lote_faltan,
                "ACC_MODELO": lbl_a_modelo, "ACC_PROD": lbl_a_prod, "ACC_FALTAN": lbl_a_faltan,
                "SIGUIENTE_MODELO": lbl_siguiente
            }

    def on_resize(self, event):
        scale = min(self.winfo_width() / self.initial_width, self.winfo_height() / self.initial_height)
        new_frame_font_size = max(10, int(14 * scale))
        new_model_font_size = max(9, int(12 * scale))
        new_data_font_size = max(8, int(11 * scale))
        new_lote_font_size = max(8, int(10 * scale))
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
                element["LOTE_PO"].config(font=("Arial", new_lote_font_size, "bold"))
                element["LOTE_FALTAN"].config(font=("Arial", new_lote_font_size, "bold"))
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
                
                if "estacion_embalaje" in LINE_MAP.get(f"{seccion} - Montaje", {}):
                    elements["MONTAJE_PROD_EMB"].pack(anchor="w", pady=(5,0))
                    elements["MONTAJE_FALTAN_EMB"].pack(anchor="w")
                    elements["MONTAJE_PROD_EMB"].config(text=f"Producidos (Emb.): {datos['PROD_EMB']}")
                    elements["MONTAJE_FALTAN_EMB"].config(text=f"Faltan (Emb.): {datos['FALTAN_EMB']}")
                else:
                    elements["MONTAJE_PROD_EMB"].pack_forget()
                    elements["MONTAJE_FALTAN_EMB"].pack_forget()

                micro_lote = datos.get("MICRO_LOTE_INFO", {})
                if micro_lote:
                    elements["LOTE_PO"].config(text=f"Lote / PO: {micro_lote.get('LOTE', 'N/A')} / {micro_lote.get('PO', 'N/A')}")
                    elements["LOTE_FALTAN"].config(text=f"Faltan del Lote: {micro_lote.get('FALTAN_LOTE', 'N/A')}")
                else:
                    elements["LOTE_PO"].config(text="Lote / PO: ---")
                    elements["LOTE_FALTAN"].config(text="Faltan del Lote: ---")

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
                logging.info("Iniciando ciclo de actualización de datos...")
                nuevos_datos = obtener_datos_para_display()
                self.datos_display = nuevos_datos
                #logging.info(f"Nuevos datos de planificación: {self.datos_display}")
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