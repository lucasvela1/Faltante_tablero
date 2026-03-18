# Arquitectura del Tablero de Producción

Este documento explica el diseño de la solución y cómo se implementó la flexibilidad entre modo demo y producción.

## Estructura General

```
┌─────────────────────────────────────────────────────────────┐
│                    TABLA GUI (Tkinter)                      │
│              (VentanaInfo, actualizar_textos_ui)            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                Lógica de Datos (tablero.py)                 │
│     obtener_datos_para_display()                            │
│     ├─ encontrar_todos_los_lotes()                          │
│     ├─ login_jmmes()                                        │
│     ├─ get_product_id()                                     │
│     ├─ get_produced_quantity()                              │
│     └─ get_produced_quantity_en_intervalo()                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
    ┌────────────────────────────────┐
    │   ¿DEMO_MODE=true?             │
    └────────┬───────────────┬──────┘
             │               │
         (Sí)│               │(No)
             ▼               ▼
    ┌──────────────┐  ┌─────────────────┐
    │ mock_data.py │  │  API MES Real    │
    │   Datos      │  │  - Login         │
    │   Simulados  │  │  - Get Products  │
    │   Realistas  │  │  - Get Produced  │
    └──────────────┘  └─────────────────┘
```

## Flujo de Datos

### Modo Demo (DEMO_MODE=true)

```
1. Startup
   └─ import mock_data
   └─ DEMO_MODE = true
   └─ info_modo_demo() ← Muestra en logs (MODO DEMO ACTIVADO)

2. Actualización Cíclica (cada 60 segundos)
   └─ obtener_datos_para_display()
      ├─ Para cada línea (LCD6, LCD8, CELDA 1, CELDA 2, CELDA 3):
      │  ├─ encontrar_todos_los_lotes() ← Lee Excel
      │  ├─ login_jmmes() ← Simula login (retorna True)
      │  ├─ get_product_id() ← Busca en MOCK_PRODUCTOS
      │  ├─ get_produced_quantity() ← Calcula producción mock
      │  └─ get_produced_quantity_en_intervalo() ← Datos históricos + variabilidad
      └─ Datos preparados para UI

3. Renderizado UI
   └─ actualizar_textos_ui() ← Muestra datos en tablero
```

### Modo Producción (DEMO_MODE=false)

```
1. Startup
   └─ No importa mock_data
   └─ DEMO_MODE = false

2. Actualización Cíclica
   └─ obtener_datos_para_display()
      ├─ Para cada línea:
      │  ├─ encontrar_todos_los_lotes() ← Lee Excel real
      │  ├─ login_jmmes() ← Autentica con API real
      │  │  └─ Obtiene tokens XSRF y Bearer
      │  ├─ get_product_id() ← Consulta API: /Products/GetByNameAndLineId
      │  │  └─ Usa headers con tokens
      │  ├─ get_produced_quantity() ← Obtiene datos acumulados
      │  └─ get_produced_quantity_en_intervalo() ← Consulta API temporal
      │     └─ /api/producedQuantities/GetReport/1/{start}/{end}?productId=XYZ
      └─ Datos reales preparados para UI

3. Renderizado UI
   └─ actualizar_textos_ui() ← Muestra datos en tablero
```

