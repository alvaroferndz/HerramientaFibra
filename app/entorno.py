import json
from pathlib import Path

def inicializar_entorno(ruta_json="config.json"):
    with open(ruta_json, 'r') as archivo:
        config = json.load(archivo)
        
    ruta_geojson = config['proyecto']['ruta_geojson']
    nombre_base = Path(ruta_geojson).stem
    
    directorio_out = Path("out") / nombre_base
    directorio_out.mkdir(parents=True, exist_ok=True)
    
    rutas = {
        "geojson": ruta_geojson,
        "fase_0": str(directorio_out / f"{nombre_base}_00_datos.gpkg"),
        "fase_1": str(directorio_out / f"{nombre_base}_01_ctos.gpkg"),
        "fase_2": str(directorio_out / f"{nombre_base}_02_obra.gpkg"),
        "excel": str(directorio_out / f"{nombre_base}_resumen.xlsx")
    }
    
    return config, rutas