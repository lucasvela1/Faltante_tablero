import requests
import json
from datetime import datetime
from ..read_config import read_config

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
        "estacion": "hermanado placa - pantalla"
    },
    "LCD 6 - Accesorios": {
        "id": 14,
        "estacion": "puesto 1"
    },
    "LCD8 - Montaje": {
        "id": 10,
        "estacion": "pantalla - placa 1"
    },
    "LCD 8 - Accesorios": {
        "id": 9,
        "estacion": "balanza ó puesto 1"
    },
    "Celda - Montaje": {
        "id": 13,
        "estacion": "pantalla - placa 1 ó pantalla - placa 1 ó pantalla - placas - técnica"
    },
    "Celda Accesorios": {
        "id": 12,
        "estacion": "balanza"
    },
    "Celda2-Montaje": {
        "id": 82,
        "estacion": "pantalla - placas - técnica ó hermanado Placa - pantalla	"
    },
    "Celda2-Accesorios": {
        "id": 83,
        "estacion": "balanza"
    }
} #Mapeo los posibles valores que puede venir de las lineas y los vinculo a su ID. Solo manejaremos Celda y las líneas de tv en este caso como posibles.

def login_jmmes():
    global X_XSRF_TOKEN, TOKEN, COOKIE

    try:
        print("Obteniendo XSRF token...")
        get_token = requests.get(f"{API_MES}/api/XsrfToken")

        antiforgery_token = get_token.cookies[".AspNetCore.Antiforgery.T8b4Fs--lAw"] #Cuando es por Request si se necesitan las cookies
        xsrf_token = get_token.cookies["XSRF-TOKEN"]

        X_XSRF_TOKEN = xsrf_token
        COOKIE = f".AspNetCore.Antiforgery.T8b4Fs--lAw={antiforgery_token}"

        headers = {
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf_token,
            "Cookie": COOKIE, #El header que guardo completo en python incluye cookies
        }

        print("Enviando login...")
        payload = json.dumps({"name": "operador", "password": "0P3r4dOr"}) #Le envio como json el usuario y contraseña, igual que en postman
        r = requests.post(f"{API_MES}/api/User/Authenticate", data=payload, headers=headers)

        if r.status_code != 200: #El codigo 200 indica exito
            print("Error al autenticar:", r.status_code)
            print("Respuesta:", r.text)
            return

        TOKEN = r.json().get("token", "")
        print("Login exitoso. Token de sesión obtenido.")

    except Exception as e:
        print("Error durante el login:", e)


def get_line_id(line_name):  #Con el nombre de la linea me devuelve la id, como una tabla Hash
    entry = LINE_MAP.get(line_name)
    return entry["id"] if entry else None

def get_estacion_clave(line_name):
    entry= LINE_MAP.get(line_name)
    return entry["estacion"] if entry else None 

def get_product_id(modelo: str, line_id: int) -> int | None:
    print(f"Obteniendo ID para el modelo {modelo} en la línea {line_id}...")
    url = f"{API_MES}/api/Products/GetByNameAndLineId/{modelo}/{line_id}"

    headers = {
        "X-XSRF-TOKEN": X_XSRF_TOKEN,
        "token": TOKEN   # Para conseguir la id necesito de los dos tokens
    }

    r = requests.get(url, headers=headers)
    print("Status code:", r.status_code)

    if r.status_code == 200:
        data = r.json()
        product_id = data.get("id")
        print("Product ID:", product_id)
        return product_id
    else:
        print("Acceso denegado o producto no encontrado.")
        print("Respuesta:", r.text)
        return None

def get_produced_quantity(product_id, line_id, fecha_inicio):
    headers = {
        "X-XSRF-TOKEN": X_XSRF_TOKEN,
        "token": TOKEN
    }

    fecha_fin = datetime.now().strftime("%d-%m-%Y%%20%H:%M")
    url = f"{API_MES}/api/producedQuantities/GetReport/1/{fecha_inicio}/{fecha_fin}"
    params = {
        "productId": product_id,
        "lineId": line_id
    }

    r = requests.get(url, headers=headers, params=params)

    if r.status_code == 200:
        try:
            data = r.json()
            estaciones = data[0][0]

            # Obtenemos todas las estaciones posibles para esta línea
            estacion_clave = next(
                (v["estacion"] for k, v in LINE_MAP.items() if v["id"] == line_id),
                None
            )

            if not estacion_clave:
                print(f"No se encontró estación clave para line_id {line_id}")
                return 0

            # Dividimos si hay "ó" y comparamos en minúscula sin espacios extra
            posibles_estaciones = [e.strip().lower() for e in estacion_clave.split("ó")]

            for est in estaciones:
                if est["stationGroupName"].lower() in posibles_estaciones:
                    return est["count"]

            print("No se encontró ninguna de las estaciones correspondientes.")
            return 0

        except Exception as e:
            print("Error procesando la respuesta:", e)
            print("Respuesta JSON bruta:", r.text)
            return 0
    else:
        print("Error al obtener producción por estación:", r.status_code)
        print("Respuesta:", r.text)
        return 0