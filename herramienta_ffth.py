import requests
import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as ctx
import osmnx as ox
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import substring
from sklearn.cluster import KMeans
import os
from sklearn_extra.cluster import KMedoids

class PlanificadorFibra:
    def __init__(self, ruta_geojson):
        self.srs_destino = "EPSG:25830"
        self.wfs_url_direcciones = "http://ovc.catastro.meh.es/INSPIRE/wfsAD.aspx"
        
        gdf_inicial = gpd.read_file(ruta_geojson).to_crs(self.srs_destino)
        self.area_diseno = gdf_inicial[gdf_inicial.geometry.type == 'Polygon']
        self.poligono_base = self.area_diseno.geometry.union_all()
        
        gdf_punto = gdf_inicial[gdf_inicial.geometry.type == 'Point']
        if gdf_punto.empty:
            raise ValueError("El GeoJSON no contiene el punto de la OLT.")
        
        self.punto_olt = gdf_punto.geometry.iloc[0]
        self.gdf_olt = gdf_punto.head(1)

    def _generar_cuadricula(self, tamano_celda_m):
        minx, miny, maxx, maxy = self.area_diseno.total_bounds
        tramos_x = np.arange(minx, maxx, tamano_celda_m)
        tramos_y = np.arange(miny, maxy, tamano_celda_m)
        
        celdas = []
        for x in tramos_x:
            for y in tramos_y:
                celda_maxx = min(x + tamano_celda_m, maxx)
                celda_maxy = min(y + tamano_celda_m, maxy)
                celdas.append(f"{int(x)},{int(y)},{int(celda_maxx)},{int(celda_maxy)}")
                
        return celdas

    def descargar_direcciones_portales(self):
        lista_bboxes = self._generar_cuadricula(500)
        gdfs_parciales = []
        archivo_temp = "temp_celda.gml"
        
        for bbox in lista_bboxes:
            params = {
                "service": "wfs",
                "version": "2.0.0",
                "request": "GetFeature",
                "typenames": "ad:Address",
                "srsname": self.srs_destino,
                "bbox": bbox
            }
            
            respuesta = requests.get(self.wfs_url_direcciones, params=params)
            
            if "ExceptionReport" not in respuesta.text and len(respuesta.content) > 500:
                with open(archivo_temp, "wb") as archivo:
                    archivo.write(respuesta.content)
                
                try:
                    gdf_celda = gpd.read_file(archivo_temp, layer="Address")
                    if not gdf_celda.empty:
                        gdfs_parciales.append(gdf_celda)
                except Exception:
                    pass

        if os.path.exists(archivo_temp):
            os.remove(archivo_temp)
            
        if not gdfs_parciales:
            raise ValueError("No se encontraron portales.")
            
        gdf_completo = pd.concat(gdfs_parciales, ignore_index=True)
        gdf_recortado = gpd.clip(gdf_completo, self.poligono_base)
        
        return gdf_recortado.drop_duplicates(subset=['geometry'])

    def obtener_red_vial(self):
        poligono_ampliado = self.poligono_base.buffer(200)
        poligono_wgs84 = gpd.GeoSeries([poligono_ampliado], crs=self.srs_destino).to_crs(epsg=4326).iloc[0]
        
        grafo = ox.graph_from_polygon(poligono_wgs84, network_type='all')
        grafo_25830 = ox.project_graph(grafo, to_crs=self.srs_destino)
        
        # Sintaxis actualizada para OSMnx 2.0+
        grafo_25830 = ox.convert.to_undirected(grafo_25830)
        
        viales = ox.graph_to_gdfs(grafo_25830, nodes=False, edges=True)
        
        return grafo_25830, viales

    def agrupar_portales_cto(self, gdf_portales, numero_ctos):
        portales = gdf_portales.copy()
        coordenadas = list(zip(portales.geometry.x, portales.geometry.y))
        
        kmeans = KMeans(n_clusters=numero_ctos, random_state=42, n_init=10)
        portales['id_cluster'] = kmeans.fit_predict(coordenadas)
        
        ctos = []
        for i in range(numero_ctos):
            grupo = portales[portales['id_cluster'] == i]
            centro_matematico = Point(kmeans.cluster_centers_[i])
            indice_portal_cto = grupo.geometry.distance(centro_matematico).idxmin()
            
            ctos.append({
                'id_cluster': i,
                'id_portal_cto': indice_portal_cto,
                'geometry': portales.loc[indice_portal_cto].geometry,
                'num_portales': len(grupo)
            })
            
        return portales, gpd.GeoDataFrame(ctos, crs=portales.crs)

    def agrupar_portales_topologico(self, gdf_portales, grafo, numero_ctos):
        portales = gdf_portales.copy()
        n_portales = len(portales)
        matriz_distancias = np.zeros((n_portales, n_portales))
        
        nodos_proyectados = []
        for _, portal in portales.iterrows():
            nodo_cercano = ox.distance.nearest_nodes(grafo, portal.geometry.x, portal.geometry.y)
            nodos_proyectados.append(nodo_cercano)
            
        for i in range(n_portales):
            for j in range(n_portales):
                if i != j:
                    origen = nodos_proyectados[i]
                    destino = nodos_proyectados[j]
                    try:
                        distancia = nx.shortest_path_length(grafo, origen, destino, weight='length')
                    except nx.NetworkXNoPath:
                        distancia = 999999
                    matriz_distancias[i][j] = distancia
                    
        kmedoids = KMedoids(n_clusters=numero_ctos, metric='precomputed', random_state=42)
        portales['id_cluster'] = kmedoids.fit_predict(matriz_distancias)
        
        ctos = []
        indices_centros = kmedoids.medoid_indices_
        for i, idx_centro in enumerate(indices_centros):
            nodo_centro = nodos_proyectados[idx_centro]
            x = grafo.nodes[nodo_centro]['x']
            y = grafo.nodes[nodo_centro]['y']
            
            grupo = portales[portales['id_cluster'] == i]
            
            ctos.append({
                'id_cluster': i,
                'id_portal_cto': idx_centro,
                'geometry': Point(x, y),
                'num_portales': len(grupo)
            })
            
        return portales, gpd.GeoDataFrame(ctos, crs=self.srs_destino)

    def calcular_red_distribucion(self, grafo, gdf_viales, gdf_ctos):
        nodo_olt = ox.distance.nearest_nodes(grafo, self.punto_olt.x, self.punto_olt.y)
        distribucion = []
        rutas_troncales = []
        tramos_fuera_grafo = []
        aristas_insercion = []
        
        for _, cto in gdf_ctos.iterrows():
            distancias = gdf_viales.geometry.distance(cto.geometry)
            idx_segmento = distancias.idxmin()
            u, v, key = idx_segmento
            
            aristas_insercion.append((u, v, key))
            
            linea_carretera = gdf_viales.loc[idx_segmento].geometry
            dist_proj = linea_carretera.project(cto.geometry)
            
            try:
                path_u_len = nx.shortest_path_length(grafo, nodo_olt, u, weight='length')
                path_v_len = nx.shortest_path_length(grafo, nodo_olt, v, weight='length')
                pos_u = linea_carretera.project(Point(grafo.nodes[u]['x'], grafo.nodes[u]['y']))
                pos_v = linea_carretera.project(Point(grafo.nodes[v]['x'], grafo.nodes[v]['y']))
                
                if (path_u_len + abs(dist_proj - pos_u)) < (path_v_len + abs(dist_proj - pos_v)):
                    nodo_optimo, pos_optimo = u, pos_u
                else:
                    nodo_optimo, pos_optimo = v, pos_v
                    
                ruta_nodos = nx.shortest_path(grafo, nodo_olt, nodo_optimo, weight='length')
                rutas_troncales.append(ruta_nodos)
                
                coordenadas_linea = [(self.punto_olt.x, self.punto_olt.y)]
                for i in range(len(ruta_nodos) - 1):
                    origen, destino = ruta_nodos[i], ruta_nodos[i+1]
                    datos = grafo.get_edge_data(origen, destino)[0]
                    if 'geometry' in datos:
                        c = list(datos['geometry'].coords)
                        if Point(c[0]).distance(Point(grafo.nodes[origen]['x'], grafo.nodes[origen]['y'])) > 1e-3:
                            c.reverse()
                        coordenadas_linea.extend(c if i == 0 else c[1:])
                    else:
                        nodo_dest = grafo.nodes[destino]
                        coordenadas_linea.append((nodo_dest['x'], nodo_dest['y']))
                
                tramo_vial = substring(linea_carretera, pos_optimo, dist_proj)
                coordenadas_linea.extend(list(tramo_vial.coords))
                coordenadas_linea.append((cto.geometry.x, cto.geometry.y))
                distribucion.append({'geometry': LineString(coordenadas_linea), 'tipo': 'Distribución'})
                
                punto_proy_cto = linea_carretera.interpolate(dist_proj)
                tramo_cto = LineString([punto_proy_cto, cto.geometry])
                tramos_fuera_grafo.append({
                    'geometry': tramo_cto,
                    'fibras_troncal': 1,
                    'fibras_acceso': cto['num_portales'],
                    'total_fibras': 1 + cto['num_portales'],
                    'length': tramo_cto.length
                })
                
            except nx.NetworkXNoPath:
                pass
                
        return gpd.GeoDataFrame(distribucion, crs=self.srs_destino), rutas_troncales, tramos_fuera_grafo, aristas_insercion

    def calcular_red_acceso(self, grafo, gdf_viales, gdf_portales_cluster, gdf_ctos):
        acceso = []
        rutas_acceso = []
        tramos_fuera_grafo = []
        aristas_insercion = []
        
        for _, portal in gdf_portales_cluster.iterrows():
            id_cluster = portal['id_cluster']
            cto_destino = gdf_ctos[gdf_ctos['id_cluster'] == id_cluster].iloc[0]
            nodo_cto = ox.distance.nearest_nodes(grafo, cto_destino.geometry.x, cto_destino.geometry.y)
            distancias = gdf_viales.geometry.distance(portal.geometry)
            idx_segmento = distancias.idxmin()
            u, v, key = idx_segmento
            
            aristas_insercion.append((u, v, key))
            
            linea_carretera = gdf_viales.loc[idx_segmento].geometry
            dist_proj = linea_carretera.project(portal.geometry)
            
            try:
                path_u_len = nx.shortest_path_length(grafo, u, nodo_cto, weight='length')
                path_v_len = nx.shortest_path_length(grafo, v, nodo_cto, weight='length')
                pos_u = linea_carretera.project(Point(grafo.nodes[u]['x'], grafo.nodes[u]['y']))
                pos_v = linea_carretera.project(Point(grafo.nodes[v]['x'], grafo.nodes[v]['y']))
                
                if (abs(dist_proj - pos_u) + path_u_len) < (abs(dist_proj - pos_v) + path_v_len):
                    nodo_optimo, pos_optimo = u, pos_u
                else:
                    nodo_optimo, pos_optimo = v, pos_v
                    
                ruta_nodos = nx.shortest_path(grafo, nodo_optimo, nodo_cto, weight='length')
                rutas_acceso.append(ruta_nodos)
                
                tramo_vial = substring(linea_carretera, dist_proj, pos_optimo)
                coords_finales = [(portal.geometry.x, portal.geometry.y)] + list(tramo_vial.coords)
                for i in range(len(ruta_nodos) - 1):
                    origen, destino = ruta_nodos[i], ruta_nodos[i+1]
                    datos = grafo.get_edge_data(origen, destino)[0]
                    if 'geometry' in datos:
                        c = list(datos['geometry'].coords)
                        if Point(c[0]).distance(Point(grafo.nodes[origen]['x'], grafo.nodes[origen]['y'])) > 1e-3:
                            c.reverse()
                        coords_finales.extend(c[1:])
                    else:
                        coords_finales.append((grafo.nodes[destino]['x'], grafo.nodes[destino]['y']))
                
                acceso.append({'geometry': LineString(coords_finales), 'id_cluster': id_cluster})
                
                punto_proy_portal = linea_carretera.interpolate(dist_proj)
                tramo_portal = LineString([punto_proy_portal, portal.geometry])
                tramos_fuera_grafo.append({
                    'geometry': tramo_portal,
                    'fibras_troncal': 0,
                    'fibras_acceso': 1,
                    'total_fibras': 1,
                    'length': tramo_portal.length
                })
                
            except Exception:
                pass
        
        return gpd.GeoDataFrame(acceso, crs=self.srs_destino), rutas_acceso, tramos_fuera_grafo, aristas_insercion

    def calcular_infraestructura_fisica(self, grafo, listas_nodos_troncales, listas_nodos_acceso, aristas_troncal_insercion, aristas_acceso_insercion):
        nx.set_edge_attributes(grafo, 0, 'fibras_troncal')
        nx.set_edge_attributes(grafo, 0, 'fibras_acceso')
        
        for ruta in listas_nodos_troncales:
            for i in range(len(ruta) - 1):
                origen, destino = ruta[i], ruta[i+1]
                if 0 in grafo[origen][destino]:
                    grafo[origen][destino][0]['fibras_troncal'] += 1
                    
        for u, v, key in aristas_troncal_insercion:
            if key in grafo[u][v]:
                grafo[u][v][key]['fibras_troncal'] += 1
                
        for ruta in listas_nodos_acceso:
            for i in range(len(ruta) - 1):
                origen, destino = ruta[i], ruta[i+1]
                if 0 in grafo[origen][destino]:
                    grafo[origen][destino][0]['fibras_acceso'] += 1
                    
        for u, v, key in aristas_acceso_insercion:
            if key in grafo[u][v]:
                grafo[u][v][key]['fibras_acceso'] += 1
                    
        gdf_aristas = ox.graph_to_gdfs(grafo, nodes=False, edges=True)
        gdf_aristas['total_fibras'] = gdf_aristas['fibras_troncal'] + gdf_aristas['fibras_acceso']
        
        return gdf_aristas[gdf_aristas['total_fibras'] > 0][['geometry', 'fibras_troncal', 'fibras_acceso', 'total_fibras', 'length']].copy()

    def exportar_geopackage(self, archivo_salida, gdf_distribucion, gdf_acceso, gdf_infraestructura, gdf_acometidas, gdf_ctos, gdf_portales):
        if not gdf_distribucion.empty:
            gdf_distribucion.to_file(archivo_salida, layer="Distribucion_Logica", driver="GPKG")
        if not gdf_acceso.empty:
            gdf_acceso.to_file(archivo_salida, layer="Acceso_Logico", driver="GPKG")
        if not gdf_infraestructura.empty:
            gdf_infraestructura.to_file(archivo_salida, layer="Canalizacion_Publica", driver="GPKG")
        if not gdf_acometidas.empty:
            gdf_acometidas.to_file(archivo_salida, layer="Acometidas_Privadas", driver="GPKG")
            
        self.gdf_olt.to_file(archivo_salida, layer="Nodo_OLT", driver="GPKG")
        gdf_ctos.to_file(archivo_salida, layer="Nodos_CTO", driver="GPKG")
        
        if not gdf_portales.empty:
            gdf_portales.to_file(archivo_salida, layer="Portales_Demanda", driver="GPKG")

    def visualizar_resultados(self, gdf_viales, gdf_infraestructura, gdf_ctos):
        fig, ax = plt.subplots(figsize=(16, 16))
        
        gdf_viales.to_crs(3857).plot(ax=ax, color='black', linewidth=0.5, alpha=0.2)
        if not gdf_infraestructura.empty:
            gdf_infraestructura.to_crs(3857).plot(ax=ax, column='total_fibras', cmap='YlOrRd', linewidth=3, legend=True, zorder=5)
            
        gdf_ctos.to_crs(3857).plot(ax=ax, color='white', edgecolor='black', marker='^', markersize=200, zorder=6)
        self.gdf_olt.to_crs(3857).plot(ax=ax, color='purple', marker='s', markersize=350, zorder=7)
        
        ax.axis('off')
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    planificador = PlanificadorFibra("./areas_cobertura/pancar.geojson")
    
    portales_base = planificador.descargar_direcciones_portales()
    grafo_vial, viales = planificador.obtener_red_vial()

    modo_agrupacion = "topologico"

    n_cluster = 12

    if modo_agrupacion == "espacial":
        portales_cluster, ctos = planificador.agrupar_portales_cto(portales_base, n_cluster)
    elif modo_agrupacion == "topologico":
        portales_cluster, ctos = planificador.agrupar_portales_topologico(portales_base, grafo_vial, n_cluster)
    
    red_distribucion, rutas_troncales, tramos_cto, aristas_insercion_troncal = planificador.calcular_red_distribucion(grafo_vial, viales, ctos)
    red_acceso, rutas_acceso, tramos_portal, aristas_insercion_acceso = planificador.calcular_red_acceso(grafo_vial, viales, portales_cluster, ctos)
    
    tramos_totales_fuera_grafo = tramos_cto + tramos_portal
    gdf_acometidas_fisicas = gpd.GeoDataFrame(tramos_totales_fuera_grafo, crs=planificador.srs_destino)
    
    infraestructura_publica = planificador.calcular_infraestructura_fisica(
        grafo_vial, 
        rutas_troncales, 
        rutas_acceso, 
        aristas_insercion_troncal, 
        aristas_insercion_acceso
    )
    
    planificador.exportar_geopackage(
        "./out/pancar.gpkg", 
        red_distribucion, 
        red_acceso, 
        infraestructura_publica, 
        gdf_acometidas_fisicas, 
        ctos, 
        portales_cluster
    )
    
    planificador.visualizar_resultados(viales, infraestructura_publica, ctos)