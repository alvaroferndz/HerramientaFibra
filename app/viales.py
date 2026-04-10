import osmnx as ox
import geopandas as gpd

class GestorVial:
    def __init__(self, srs_destino="EPSG:25830"):
        self.srs_destino = srs_destino

    def obtener_red_vial(self, poligono_base):
        poligono_ampliado = poligono_base.buffer(200)
        poligono_wgs84 = gpd.GeoSeries([poligono_ampliado], crs=self.srs_destino).to_crs(epsg=4326).iloc[0]
        
        grafo = ox.graph_from_polygon(poligono_wgs84, network_type='all')
        grafo_25830 = ox.project_graph(grafo, to_crs=self.srs_destino)
        grafo_25830 = ox.convert.to_undirected(grafo_25830)
        viales = ox.graph_to_gdfs(grafo_25830, nodes=False, edges=True)
        
        return grafo_25830, viales