import geopandas as gpd
from pathlib import Path
from datos import GestorDatos
from viales import GestorVial
from agrupacion import AgrupadorCTO
from enrutamiento import EnrutadorFibra
from entorno import inicializar_entorno

config, rutas = inicializar_entorno()

for ruta_fase in [rutas["fase_0"], rutas["fase_1"], rutas["fase_2"]]:
    archivo = Path(ruta_fase)
    if archivo.exists():
        archivo.unlink()

srs = config['proyecto']['srs']
ruta_geojson = rutas["geojson"]

gestor_datos = GestorDatos(srs)
gestor_vial = GestorVial(srs)
agrupador = AgrupadorCTO(srs)

area_diseno, poligono_base, punto_olt, gdf_olt = gestor_datos.cargar_area_diseno(ruta_geojson)
enrutador = EnrutadorFibra(srs, punto_olt)

portales_base = gestor_datos.descargar_direcciones_portales(area_diseno, poligono_base)
grafo_vial, viales = gestor_vial.obtener_red_vial(poligono_base)

modo = config['parametros']['agrupacion']['modo']
cap_max = config['parametros']['agrupacion']['capacidad_maxima']
dist_max = config['parametros']['agrupacion']['distancia_maxima']
ctos_max = config['parametros']['agrupacion']['numero_ctos']

if modo == "espacial":
    portales_cluster, ctos = agrupador.agrupar_espacial(portales_base, capacidad_maxima=cap_max)
elif modo == "topologico":
    portales_cluster, ctos = agrupador.agrupar_topologico(portales_base, grafo_vial, capacidad_maxima=cap_max, distancia_maxima=dist_max)
elif modo == "voronoi":
    portales_cluster, ctos = agrupador.agrupar_voronoi_red(portales_base, grafo_vial, numero_ctos=ctos_max)

portales_asignados = portales_cluster[portales_cluster['id_cluster'] != -1].copy()

red_acc_preliminar, _, tramos_portal_preliminar, _ = enrutador.calcular_acceso(grafo_vial, viales, portales_asignados, ctos)
gdf_acometidas_preliminar = gpd.GeoDataFrame(tramos_portal_preliminar, crs=srs)

archivo_salida = rutas["fase_0"]
if not portales_cluster.empty:
    portales_cluster.to_file(archivo_salida, layer="Portales_Demanda", driver="GPKG")
if not ctos.empty:
    ctos.to_file(archivo_salida, layer="Nodos_CTO", driver="GPKG")
gdf_olt.to_file(archivo_salida, layer="Nodo_OLT", driver="GPKG")
if not red_acc_preliminar.empty:
    red_acc_preliminar.to_file(archivo_salida, layer="Acceso_Logico", driver="GPKG")
if not gdf_acometidas_preliminar.empty:
    gdf_acometidas_preliminar.to_file(archivo_salida, layer="Acometidas_Privadas", driver="GPKG")