import geopandas as gpd
from shapely.geometry import Point
from datos import GestorDatos
from viales import GestorVial
from enrutamiento import EnrutadorFibra
from entorno import inicializar_entorno

def optimizar_ctos_en_vertices_geometria(gdf_portales, gdf_ctos, gdf_viales):
    ctos_optimizadas = []

    for id_cluster in gdf_ctos['id_cluster'].unique():
        portales = gdf_portales[gdf_portales['id_cluster'] == id_cluster]
        
        calles_involucradas = set()
        for p in portales.geometry:
            idx_calle = gdf_viales.geometry.distance(p).idxmin()
            calles_involucradas.add(idx_calle)
            
        coordenadas_candidatas = set()
        for idx in calles_involucradas:
            linea = gdf_viales.loc[idx].geometry
            # Uso de geom_type para evitar ShapelyDeprecationWarning
            if linea.geom_type == 'LineString':
                coordenadas_candidatas.update(list(linea.coords))
            elif linea.geom_type == 'MultiLineString':
                for parte in linea.geoms:
                    coordenadas_candidatas.update(list(parte.coords))
                    
        candidatos = [Point(c) for c in coordenadas_candidatas]
        
        mejor_punto = None
        min_distancia = float('inf')
        
        for candidato in candidatos:
            dist_total = portales.geometry.distance(candidato).sum()
            if dist_total < min_distancia:
                min_distancia = dist_total
                mejor_punto = candidato
                
        ctos_optimizadas.append({
            'id_cluster': id_cluster,
            'geometry': mejor_punto,
            'num_portales': len(portales)
        })

    return gpd.GeoDataFrame(ctos_optimizadas, crs=gdf_ctos.crs)

config, rutas = inicializar_entorno()
srs = config['proyecto']['srs']

gestor_datos = GestorDatos(srs)
gestor_vial = GestorVial(srs)

# Carga de área y red vial
_, poligono_base, _, _ = gestor_datos.cargar_area_diseno(rutas["geojson"])
grafo_vial, viales = gestor_vial.obtener_red_vial(poligono_base)

# Lectura de la fase inicial
portales = gpd.read_file(rutas["fase_0"], layer="Portales_Demanda")
ctos_preliminares = gpd.read_file(rutas["fase_0"], layer="Nodos_CTO")
gdf_olt = gpd.read_file(rutas["fase_0"], layer="Nodo_OLT")
punto_olt = gdf_olt.geometry.iloc[0]

# Optimización de posiciones
portales_asignados = portales[portales['id_cluster'] != -1].copy()
ctos_optimizadas = optimizar_ctos_en_vertices_geometria(portales_asignados, ctos_preliminares, viales)

# Cálculo de red lógica para guía visual
enrutador = EnrutadorFibra(srs, punto_olt)
red_acc, _, tramos_portal, _ = enrutador.calcular_acceso(grafo_vial, viales, portales_asignados, ctos_optimizadas)
gdf_acometidas = gpd.GeoDataFrame(tramos_portal, crs=srs)

# Guardado completo en Fase 1
archivo_salida = rutas["fase_1"]
ctos_optimizadas.to_file(archivo_salida, layer="Nodos_CTO", driver="GPKG")
portales.to_file(archivo_salida, layer="Portales_Demanda", driver="GPKG")
gdf_olt.to_file(archivo_salida, layer="Nodo_OLT", driver="GPKG")

if not red_acc.empty:
    red_acc.to_file(archivo_salida, layer="Acceso_Logico", driver="GPKG")
if not gdf_acometidas.empty:
    gdf_acometidas.to_file(archivo_salida, layer="Acometidas_Privadas", driver="GPKG")

print(f"Fase 1 finalizada. Red lógica generada para guía en {archivo_salida}")