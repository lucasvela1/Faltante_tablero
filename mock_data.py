"""
Módulo con datos mock para demostración y testing del tablero.
Simula el comportamiento de la API MES con datos realistas.
"""
from datetime import datetime, timedelta
import random
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')


MOCK_PRODUCTOS = {
    # LCD6
    (3, "LCD6-4K"):    {"id": 1001, "nombre": "LCD6-4K"},
    (3, "LCD6-2K"):    {"id": 1002, "nombre": "LCD6-2K"},
    (14, "LCD6-4K"):   {"id": 1003, "nombre": "LCD6-4K"},
    (14, "LCD6-2K"):   {"id": 1004, "nombre": "LCD6-2K"},
    # LCD8
    (10, "LCD8-4K"):   {"id": 1005, "nombre": "LCD8-4K"},
    (10, "LCD8-8K"):   {"id": 1006, "nombre": "LCD8-8K"},
    (9, "LCD8-4K"):    {"id": 1007, "nombre": "LCD8-4K"},
    (9, "LCD8-8K"):    {"id": 1008, "nombre": "LCD8-8K"},
    # CELDA 1
    (13, "CELDA1-STD"): {"id": 1009, "nombre": "CELDA1-STD"},
    (12, "CELDA1-STD"): {"id": 1010, "nombre": "CELDA1-STD"},
    # CELDA 2
    (82, "CELDA2-PRO"): {"id": 1011, "nombre": "CELDA2-PRO"},
    (83, "CELDA2-PRO"): {"id": 1012, "nombre": "CELDA2-PRO"},
    # CELDA 3
    (103, "CELDA3-PRO"): {"id": 1013, "nombre": "CELDA3-PRO"},
    (104, "CELDA3-PRO"): {"id": 1014, "nombre": "CELDA3-PRO"},
}

# Simulación de producción por hora (realista: varía a lo largo del turno)
MOCK_PRODUCCION_HISTORICA = {
    1001: [15, 18, 20, 22, 19, 21, 18, 20, 15],  # LCD6-4K Montaje (9 horas)
    1002: [12, 14, 16, 18, 15, 17, 14, 16, 12],  # LCD6-2K Montaje
    1003: [18, 20, 22, 24, 21, 23, 20, 22, 18],  # LCD6-4K Accesorios
    1004: [14, 16, 18, 20, 17, 19, 16, 18, 14],  # LCD6-2K Accesorios
    1005: [20, 22, 25, 27, 24, 26, 23, 25, 20],  # LCD8-4K Montaje
    1006: [18, 20, 22, 24, 21, 23, 20, 22, 18],  # LCD8-8K Montaje
    1007: [22, 25, 28, 30, 27, 29, 26, 28, 22],  # LCD8-4K Accesorios
    1008: [20, 22, 25, 27, 24, 26, 23, 25, 20],  # LCD8-8K Accesorios
    1009: [16, 18, 20, 22, 19, 21, 18, 20, 16],  # CELDA1-STD Montaje
    1010: [18, 20, 22, 24, 21, 23, 20, 22, 18],  # CELDA1-STD Accesorios
    1011: [18, 20, 23, 25, 22, 24, 21, 23, 18],  # CELDA2-PRO Montaje
    1012: [20, 22, 25, 27, 24, 26, 23, 25, 20],  # CELDA2-PRO Accesorios
    1013: [18, 20, 23, 25, 22, 24, 21, 23, 18],  # CELDA3-PRO Montaje
    1014: [20, 22, 25, 27, 24, 26, 23, 25, 20],  # CELDA3-PRO Accesorios
}

def mock_login_jmmes():
    """Simula login exitoso a la API MES."""
    logging.info("🔐 [MOCK] Login exitoso a API MES")
    return True

def mock_get_product_id(modelo, line_id):
    """
    Simula búsqueda de producto.
    
    Args:
        modelo: Nombre del modelo (ej: "LCD6-4K")
        line_id: ID de la línea de producción
    
    Returns:
        ID del producto simulado, o None si no existe
    """
    key = (line_id, modelo)
    if key in MOCK_PRODUCTOS:
        product_id = MOCK_PRODUCTOS[key]["id"]
        logging.info(f"[MOCK] Producto encontrado: {modelo} (ID: {product_id})")
        return product_id
    logging.warning(f"[MOCK] Producto no encontrado: {modelo} (Línea: {line_id})")
    return None

def mock_get_produced_quantity_en_intervalo(product_id, line_id, start_time, end_time, line_name, station_key_name):
    """
    Simula obtención de cantidad producida en un intervalo de tiempo.
    Usa datos históricos + variabilidad realista.
    
    Args:
        product_id: ID del producto
        line_id: ID de la línea
        start_time: Datetime de inicio
        end_time: Datetime de fin
        line_name: Nombre de la línea (ej: "LCD6 - Montaje")
        station_key_name: Clave de estación ("estacion" o "estacion_embalaje")
    
    Returns:
        Cantidad producida en el intervalo
    """
    if product_id not in MOCK_PRODUCCION_HISTORICA:
        return 0
    
    # Calcular hora simulada del turno (0-9, siendo 0 = 6:00 y 9 = 15:00).
    # Para que el demo funcione a cualquier hora, mapeamos horas fuera del turno
    # dentro de la ventana de 6-15.
    now = datetime.now()
    hora_inicio_turno = now.replace(hour=6, minute=0, second=0, microsecond=0)
    hora_fin_turno = hora_inicio_turno + timedelta(hours=9)

    if now < hora_inicio_turno:
        # Antes del turno: mapeamos la hora actual al rango 6-15 usando modulo 9
        hora_simulada = hora_inicio_turno + timedelta(hours=now.hour % 9, minutes=now.minute)
    elif now > hora_fin_turno:
        # Después del turno: devolvemos producción completa del turno
        hora_simulada = hora_fin_turno
    else:
        hora_simulada = now

    minutos_transcurridos = int((hora_simulada - hora_inicio_turno).total_seconds() / 60)
    hora_turno = minutos_transcurridos // 60
    minuto_en_hora = minutos_transcurridos % 60
    
    producciones = MOCK_PRODUCCION_HISTORICA[product_id]
    
    # Calcular producción hasta esta hora
    produccion_total = 0
    
    # Sumar todas las horas completas
    if hora_turno > 0:
        for i in range(min(hora_turno, len(producciones))):
            produccion_total += producciones[i]
    
    # Sumar la parte proporcional de la hora actual
    if hora_turno < len(producciones):
        produccion_parcial = int(producciones[hora_turno] * (minuto_en_hora / 60))
        produccion_total += produccion_parcial
    
    # Agregar variabilidad realista (±15%)
    variabilidad = random.uniform(0.85, 1.15)
    produccion_total = int(produccion_total * variabilidad)
    
    logging.debug(f"[MOCK] Intervalo {start_time.time()} - {end_time.time()}: {produccion_total} unidades (Producto ID: {product_id})")
    
    return produccion_total

def mock_get_produced_quantity(product_id, line_id, fecha_inicio, line_name, station_key_name):
    """
    Simula obtención de cantidad producida total (desde inicio hasta ahora).
    
    Args:
        product_id: ID del producto
        line_id: ID de la línea
        fecha_inicio: Fecha de inicio (formato 'dd-mm-yyyy')
        line_name: Nombre de la línea
        station_key_name: Clave de estación
    
    Returns:
        Cantidad producida total
    """
    # Usar el intervalo completo desde el inicio del turno hasta ahora
    hora_inicio_obj = datetime.strptime(fecha_inicio, '%d-%m-%Y').replace(hour=6, minute=0)
    hora_fin_obj = datetime.now()
    
    return mock_get_produced_quantity_en_intervalo(
        product_id, line_id, hora_inicio_obj, hora_fin_obj, line_name, station_key_name
    )


def info_modo_demo():
    """Imprime información de que se está usando modo demo."""
    logging.info("=" * 70)
    logging.info("MODO DEMO ACTIVADO - Usando datos mock para demostración")
    logging.info("=" * 70)
