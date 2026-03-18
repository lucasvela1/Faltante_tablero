# 📊 Tablero de Producción MES

Tablero en tiempo real creado con Tkinter que monitorea la producción en múltiples líneas de una fábrica.

## 🎯 Funcionalidades

- ✅ **Monitoreo en tiempo real** de 5 líneas de producción (LCD6, LCD8, CELDA 1, CELDA 2, CELDA 3)
- ✅ **Faltantes por puesto**: Muestra cuántas unidades faltan en la estación 1 (montaje)
- ✅ **Control de embalaje**: Registra producción en puesto de embalaje
- ✅ **Información de lotes**: Display del lote e OP activos
- ✅ **Tiempo estimado**: Calcula automáticamente tiempo para completar la producción
- ✅ **Próximo modelo**: Predice el próximo lote a procesar
- ✅ **Modo Demo**: Funciona con datos simulados realistas sin credenciales

## Quickstart

### Opción 1: Demo Mode 

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar (ya está configurado con DEMO_MODE=true)
python tablero.py
```

**Ventaja:** Funciona inmediatamente, muestra datos realistas, sin API requerida.

### Opción 2: API Real

Edita `.env`:
```bash
DEMO_MODE=false
API_MES=http://tu-api-real.com
RUTA_EXCEL=/ruta/a/tu/plan.xlsx
USUARIO=tu_usuario
CONTRASENA=tu_contrasena
```

Luego ejecuta: `python tablero.py`


## Tecnologías

- **Python 3.x**
- **Tkinter** - GUI
- **Pandas** - Procesamiento de datos Excel
- **Requests** - Cliente HTTP para API MES
- **Threading** - Actualizaciones asincrónicas
- **Python-dotenv** - Gestión de variables de entorno

## Requisitos

```
tkinter        (incluido en Python)
pandas
requests
python-dotenv
openpyxl       (para Excel)
```

Instalar: `pip install -r requirements.txt`

## Datos Mostrados por Línea

Para cada línea se muestra:

```
┌──────────────────────┐
│ MONTAJE              │
├──────────────────────┤
│ Modelo: LCD6-4K      │
│ Producidos: 150/250  │
│ Faltan: 100 (2:30)   │
│ Embalaje: 140/250    │
│ Lote / OP: LT-001/OP-5432
│                      │
│ ACCESORIOS           │
├──────────────────────┤
│ Modelo: LCD6-4K      │
│ Producidos: 180/250  │
│ Faltan: 70 (1:45)    │
│                      │
│ Siguiente: LCD6-2K   │
└──────────────────────┘
```

## 📝 Notas

- El turno se considera desde 6:00 AM hasta 3:00 PM (9 horas)
- Las ventanas de tiempo para cálculo de ritmo son configurables (`VENTANA_TIEMPO_MINUTOS`)
- Los lotes se agrupen por modelo automáticamente
- El tiempo estimado se calcula en base a ritmos recientes

