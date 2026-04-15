import os
import requests
import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from entorno import inicializar_entorno

# 1. Configuración inicial
config, rutas = inicializar_entorno()
srs = config['proyecto']['srs']
archivo_salida = rutas["fase_0"]

print("--- Iniciando descarga de Anexos Catastrales (Visuales) ---")

if not Path(archivo_salida).exists():
    print(f"⚠️ Advertencia: No se ha encontrado el archivo {archivo_salida}.")
    print("Por favor, ejecuta primero el script principal de la Fase 0.")
    exit()

# 2. Funciones auxiliares para la descarga WFS
def generar_cuadricula(area_bounds, tamano_celda_m):
    minx, miny, maxx, maxy = area_bounds
    tramos_x = np.arange(minx, maxx, tamano_celda_m)
    tramos_y = np.arange(miny, maxy, tamano_celda_m)
    celdas = []
    for x in tramos_x:
        for y in tramos_y:
            celdas.append(f"{int(x)},{int(y)},{int(min(x + tamano_celda_m, maxx))},{int(min(y + tamano_celda_m, maxy))}")
    return celdas

def descargar_capa_wfs(url, typename, layer_name, poligono_base):
    print(f"Descargando capa: {layer_name}...")
    celdas = generar_cuadricula(poligono_base.bounds, 500)
    gdfs = []
    archivo_temp = f"temp_{layer_name}.gml"

    for bbox in celdas:
        params = {
            "service": "wfs", "version": "2.0.0", "request": "GetFeature",
            "typenames": typename, "srsname": srs, "bbox": bbox
        }
        res = requests.get(url, params=params)
        
        if "ExceptionReport" not in res.text and len(res.content) > 500:
            with open(archivo_temp, "wb") as f:
                f.write(res.content)
            try:
                gdf = gpd.read_file(archivo_temp, layer=layer_name)
                if not gdf.empty:
                    gdfs.append(gdf)
            except Exception:
                pass

    if os.path.exists(archivo_temp):
        os.remove(archivo_temp)

    if not gdfs:
        print(f"  - No se encontraron datos para {layer_name}.")
        return gpd.GeoDataFrame(geometry=[], crs=srs)

    completo = pd.concat(gdfs, ignore_index=True)
    return gpd.clip(completo, poligono_base)

# 3. Lectura del área de diseño
print("Leyendo polígono de actuación...")
area_inicial = gpd.read_file(rutas["geojson"]).to_crs(srs)
poligono_base = area_inicial[area_inicial.geometry.type == 'Polygon'].geometry.union_all()

# 4. Descarga de datos
url_bu = "http://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"
url_cp = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"

edificios = descargar_capa_wfs(url_bu, "bu:Building", "Building", poligono_base)
parcelas = descargar_capa_wfs(url_cp, "cp:CadastralParcel", "CadastralParcel", poligono_base)

# 5. Inyección en el GeoPackage existente
print(f"Inyectando {len(edificios)} edificios y {len(parcelas)} parcelas en el proyecto...")

if not edificios.empty:
    edificios.to_file(archivo_salida, layer="Edificios_Catastrales", driver="GPKG")
if not parcelas.empty:
    parcelas.to_file(archivo_salida, layer="Parcelas_Catastrales", driver="GPKG")

print("✅ Proceso completado. Ya puedes abrir el GeoPackage en QGIS.")