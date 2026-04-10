import json
import geopandas as gpd
import matplotlib.pyplot as plt
from datos import GestorDatos
from viales import GestorVial
from enrutamiento import EnrutadorFibra

def visualizar_resultados(gdf_olt, gdf_viales, gdf_infraestructura, gdf_ctos):
    fig, ax = plt.subplots(figsize=(16, 16))
    gdf_viales.to_crs(3857).plot(ax=ax, color='black', linewidth=0.5, alpha=0.2)
    if not gdf_infraestructura.empty:
        gdf_infraestructura.to_crs(3857).plot(ax=ax, column='total_fibras', cmap='YlOrRd', linewidth=3, legend=True, zorder=5)
    gdf_ctos.to_crs(3857).plot(ax=ax, color='white', edgecolor='black', marker='^', markersize=200, zorder=6)
    gdf_olt.to_crs(3857).plot(ax=ax, color='purple', marker='s', markersize=350, zorder=7)
    ax.axis('off')
    plt.tight_layout()
    plt.show()

def cargar_configuracion(ruta_json):
    with open(ruta_json, 'r') as archivo:
        return json.load(archivo)

config = cargar_configuracion("config.json")
archivo_qgis = config['proyecto']['archivo_qgis']
srs = config['proyecto']['srs']
ruta_geojson = config['proyecto']['ruta_geojson']

gestor_datos = GestorDatos(srs)
gestor_vial = GestorVial(srs)

area_diseno, poligono_base, punto_olt, gdf_olt = gestor_datos.cargar_area_diseno(ruta_geojson)
enrutador = EnrutadorFibra(srs, punto_olt)

grafo_vial, viales = gestor_vial.obtener_red_vial(poligono_base)

portales_revisados = gpd.read_file(archivo_qgis, layer="Portales_Demanda")
ctos_revisados = gpd.read_file(archivo_qgis, layer="Nodos_CTO")

portales_asignados = portales_revisados[portales_revisados['id_cluster'] != -1].copy()

red_dist, rutas_troncales, tramos_cto, aristas_troncal = enrutador.calcular_distribucion(grafo_vial, viales, ctos_revisados)
red_acc, rutas_acceso, tramos_portal, aristas_acceso = enrutador.calcular_acceso(grafo_vial, viales, portales_asignados, ctos_revisados)

tramos_extra = tramos_cto + tramos_portal
gdf_acometidas = gpd.GeoDataFrame(tramos_extra, crs=srs)

infraestructura = enrutador.calcular_infraestructura_fisica(grafo_vial, rutas_troncales, rutas_acceso, aristas_troncal, aristas_acceso)

gestor_datos.exportar_geopackage(archivo_qgis, red_dist, red_acc, infraestructura, gdf_acometidas, ctos_revisados, portales_revisados, gdf_olt)

visualizar_resultados(gdf_olt, viales, infraestructura, ctos_revisados)