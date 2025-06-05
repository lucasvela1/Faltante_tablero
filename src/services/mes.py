import requests
import json
from datetime import datetime
from ..read_config import read_config
import logging 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_MES = read_config("API_MES")

HEADERS = {
    "Content-Type": "application/json",
}

X_XSRF_TOKEN = ""
TOKEN = ""
COOKIE = ""

LINE_MAP = {
    "LCD6 - Montaje": {
        "id": 3,
        "estacion": "hermanado placa - pantalla",
        "estacion_embalaje": "Embalaje" 
    },
    "LCD 6 - Accesorios": {
        "id": 14,
        "estacion": "puesto 1"
        # NO estacion_embalaje for Accesorios
    },
    "LCD8 - Montaje": {
        "id": 10,
        "estacion": "pantalla - placa 1",
        "estacion_embalaje": "Embalaje",
        "estacion_lote": "Palletizado"
    },"LCD 8 - Accesorios": {
        "id": 9,
        "estacion": "balanza ó puesto 1"
    },
    "Celda - Montaje": {
        "id": 13,
        "estacion": "pantalla - placa 1 ó pantalla - placa 1 ó pantalla - placas - técnica ó hermanado placa - pantalla",
        "estacion_lote": "Palletizado"
    },
    "Celda Accesorios": {
        "id": 12,
        "estacion": "balanza ó puesto 1"
    },
    "Celda2-Montaje": {
        "id": 82,
        "estacion": "pantalla - placas - técnica ó hermanado Placa - pantalla",
        "estacion_lote": "Palletizado"
    },
    "Celda2-Accesorios": {
        "id": 83,
        "estacion": "balanza ó puesto 1"
    }
}

 #Mapeo los posibles valores que puede venir de las lineas y los vinculo a su ID. Solo manejaremos Celda y las líneas de tv en este caso como posibles.

def login_jmmes():
    global X_XSRF_TOKEN, TOKEN, COOKIE

    try:
        logging.info("Obteniendo XSRF token...")
        get_token = requests.get(f"{API_MES}/api/XsrfToken")
        get_token.raise_for_status() 
        antiforgery_token = get_token.cookies.get(".AspNetCore.Antiforgery.T8b4Fs--lAw")
        xsrf_token = get_token.cookies.get("XSRF-TOKEN")

        if not antiforgery_token or not xsrf_token:
            logging.error("No se pudieron obtener las cookies de antiforgery o XSRF.")
            return

        X_XSRF_TOKEN = xsrf_token
        COOKIE = f".AspNetCore.Antiforgery.T8b4Fs--lAw={antiforgery_token}"

        headers = {
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf_token,
            "Cookie": COOKIE,
        }

        logging.info("Enviando login...")
        payload = json.dumps({"name": "lvela", "password": "1997"})
        r = requests.post(f"{API_MES}/api/User/Authenticate", data=payload, headers=headers)

        if r.status_code != 200:
            logging.error(f"Error al autenticar: {r.status_code} - Respuesta: {r.text}")
            return

        TOKEN = r.json().get("token", "")
        if TOKEN:
            logging.info("Login exitoso. Token de sesión obtenido.")
        else:
            logging.error("Login fallido. No se obtuvo token de sesión.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error de red durante el login: {e}")
    except Exception as e:
        logging.error(f"Error inesperado durante el login: {e}")


def get_line_id(line_name):
    entry = LINE_MAP.get(line_name)
    return entry.get("id") if entry else None 

def get_station_name_by_key(line_name, key_name="estacion"):
    """Obtiene el nombre de la estación (o nombres separados por 'ó') para una línea dada y una clave específica."""
    entry = LINE_MAP.get(line_name)
    return entry.get(key_name) if entry else None

def get_product_id(modelo: str, line_id: int) -> int | None:
    if not TOKEN or not X_XSRF_TOKEN:
        logging.warning("Intento de obtener Product ID sin estar logueado.")
        return None 

    logging.info(f"Obteniendo ID para el modelo {modelo} en la línea {line_id}...")
    url = f"{API_MES}/api/Products/GetByNameAndLineId/{modelo}/{line_id}"

    headers = {
        "X-XSRF-TOKEN": X_XSRF_TOKEN,
        "token": TOKEN
    }

    try:
        r = requests.get(url, headers=headers)
        logging.info(f"Get Product ID Status code: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            product_id = data.get("id")
            logging.info(f"Product ID: {product_id}")
            return product_id
        elif r.status_code == 401:
             logging.warning("Token expirado o inválido al obtener Product ID. Intentando re-loguear...")
             login_jmmes() 
             return None 
        else:
            logging.error(f"Error al obtener Product ID para {modelo} en {line_id}. Status: {r.status_code}. Respuesta: {r.text}")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Error de red obteniendo Product ID: {e}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Error decodificando JSON para Product ID: {e}. Respuesta: {r.text}")
        return None


def get_produced_quantity(product_id, line_id, fecha_inicio, line_name, station_key_name="estacion"):
    """
    Obtiene la cantidad producida para un producto/línea/fecha dados,
    buscando la estación especificada por station_key_name ('estacion' o 'estacion_embalaje').
    """
    if not TOKEN or not X_XSRF_TOKEN:
        logging.warning(f"Intento de obtener cantidad producida ({station_key_name}) sin estar logueado.")
        return 0 
    headers = {
        "X-XSRF-TOKEN": X_XSRF_TOKEN,
        "token": TOKEN
    }

  
    fecha_fin = datetime.now().strftime("%d-%m-%Y %H:%M") 
    fecha_fin_encoded = fecha_fin.replace(" ", "%20") 

    url = f"{API_MES}/api/producedQuantities/GetReport/1/{fecha_inicio}/{fecha_fin_encoded}"
    params = {
        "productId": product_id,
        "lineId": line_id
    }

    try:
        logging.info(f"Consultando cantidad para Estación '{station_key_name}' - Línea: {line_name}, Producto ID: {product_id}")
        r = requests.get(url, headers=headers, params=params)
        logging.info(f"Get Quantity ({station_key_name}) Status code: {r.status_code}")

        if r.status_code == 200:
            try:
                data = r.json()

                if not data or not isinstance(data, list) or not data[0] or not isinstance(data[0], list) or not data[0][0] or not isinstance(data[0][0], list):
                    logging.warning(f"Estructura de datos inesperada en respuesta para {line_name}/{product_id} ({station_key_name}). Respuesta: {r.text}")
                    return 0

                estaciones_data = data[0][0] 

                target_station_names_str = get_station_name_by_key(line_name, station_key_name)

                if not target_station_names_str:
                    logging.warning(f"No se encontró nombre de estación para key '{station_key_name}' en linea '{line_name}' (ID: {line_id}) en LINE_MAP.")
                    return 0

                possible_station_names = [e.strip().lower() for e in target_station_names_str.split("ó")]
                logging.debug(f"Buscando estaciones: {possible_station_names}")

                for est_info in estaciones_data:
                    station_name_api = est_info.get("stationGroupName", "").strip().lower()
                    if station_name_api in possible_station_names:
                        count = est_info.get("count", 0)
                        logging.info(f"Estación encontrada: '{station_name_api}', Cantidad: {count}")
                        return count

                logging.warning(f"No se encontró ninguna de las estaciones '{possible_station_names}' en la respuesta API para {line_name}/{product_id}.")
                return 0 

            except (json.JSONDecodeError, IndexError, TypeError, KeyError) as e:
                logging.error(f"Error procesando respuesta JSON para {line_name}/{product_id} ({station_key_name}): {e}")
                logging.error(f"Respuesta JSON bruta: {r.text}")
                return 0
        elif r.status_code == 401:
             logging.warning(f"Token expirado o inválido al obtener cantidad producida ({station_key_name}). Intentando re-loguear...")
             login_jmmes() 
             return 0 
        else:
            logging.error(f"Error al obtener producción ({station_key_name}) para {line_name}/{product_id}. Status: {r.status_code}. Respuesta: {r.text}")
            return 0

    except requests.exceptions.RequestException as e:
        logging.error(f"Error de red obteniendo cantidad producida ({station_key_name}): {e}")
        return 0