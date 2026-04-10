import numpy as np
import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import Point, LineString
from sklearn.cluster import KMeans
from sklearn_extra.cluster import KMedoids
from scipy.optimize import linear_sum_assignment
from sklearn.neighbors import KNeighborsClassifier

class AgrupadorCTO:
    def __init__(self, srs_destino="EPSG:25830"):
        self.srs_destino = srs_destino

    def agrupar_espacial(self, gdf_portales, numero_ctos=None, capacidad_maxima=None):
        if numero_ctos is None and capacidad_maxima is None:
            raise ValueError("Debes especificar 'numero_ctos' o 'capacidad_maxima'.")
            
        portales = gdf_portales.copy()
        coordenadas = np.array(list(zip(portales.geometry.x, portales.geometry.y)))
        
        if capacidad_maxima is not None:
            k = int(np.ceil(len(portales) / capacidad_maxima))
        else:
            k = numero_ctos
            
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        
        if capacidad_maxima is None:
            portales['id_cluster'] = kmeans.fit_predict(coordenadas)
            centros = kmeans.cluster_centers_
        else:
            kmeans.fit(coordenadas)
            centros = kmeans.cluster_centers_
            matriz_distancias = np.linalg.norm(coordenadas[:, np.newaxis] - centros, axis=2)
            
            # --- ASIGNACIÓN LINEAL GLOBAL (Min-Cost Flow) ---
            total_puertos = k * capacidad_maxima
            matriz_costes = np.zeros((len(portales), total_puertos))
            mapa_puerto_cto = np.repeat(np.arange(k), capacidad_maxima)
            
            for i in range(len(portales)):
                for j in range(total_puertos):
                    id_cluster = mapa_puerto_cto[j]
                    matriz_costes[i, j] = matriz_distancias[i][id_cluster]
                    
            row_ind, col_ind = linear_sum_assignment(matriz_costes)
            asignacion_final = np.full(len(portales), -1)
            
            for i, p_idx in zip(row_ind, col_ind):
                asignacion_final[i] = mapa_puerto_cto[p_idx]
                        
            portales['id_cluster'] = asignacion_final

        ctos = []
        for i in range(k):
            grupo = portales[portales['id_cluster'] == i]
            
            if not grupo.empty:
                centro_matematico = Point(centros[i])
                indice_portal_cto = grupo.geometry.distance(centro_matematico).idxmin()
                
                ctos.append({
                    'id_cluster': i,
                    'id_portal_cto': indice_portal_cto,
                    'geometry': portales.loc[indice_portal_cto].geometry,
                    'num_portales': len(grupo)
                })
                
        return portales, gpd.GeoDataFrame(ctos, crs=self.srs_destino)

    def agrupar_topologico(self, gdf_portales, grafo, capacidad_maxima, distancia_maxima):
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

        numero_ctos_necesarios = int(np.ceil(n_portales / capacidad_maxima))
        nodos_unicos = len(set(nodos_proyectados))
        ctos_reales = min(numero_ctos_necesarios, nodos_unicos)
        
        # Penalización cuadrática para repeler centroides en KMedoids
        kmedoids = KMedoids(n_clusters=ctos_reales, metric='precomputed', init='k-medoids++', random_state=42)
        kmedoids.fit(matriz_distancias ** 2) 
        indices_centros = kmedoids.medoid_indices_
        
        # --- ASIGNACIÓN LINEAL GLOBAL (Min-Cost Flow) ---
        total_puertos = ctos_reales * capacidad_maxima
        matriz_costes = np.zeros((n_portales, total_puertos))
        mapa_puerto_cto = np.repeat(np.arange(ctos_reales), capacidad_maxima)
        
        PENALIZACION = 999999
        
        for i in range(n_portales):
            for j in range(total_puertos):
                id_cluster_virtual = mapa_puerto_cto[j]
                idx_centro = indices_centros[id_cluster_virtual]
                dist = matriz_distancias[i][idx_centro]
                
                if dist <= distancia_maxima:
                    matriz_costes[i, j] = dist
                else:
                    matriz_costes[i, j] = PENALIZACION
                    
        # Resuelve la asignación global minimizando el coste total de enrutamiento
        row_ind, col_ind = linear_sum_assignment(matriz_costes)
        asignacion_final = np.full(n_portales, -1)
        
        for i, p_idx in zip(row_ind, col_ind):
            coste = matriz_costes[i, p_idx]
            if coste < PENALIZACION:
                asignacion_final[i] = mapa_puerto_cto[p_idx]
            # Si el coste es PENALIZACION, el portal excede la distancia_maxima de cualquier CTO. 
            # Queda con -1 (huérfano) para que lo revises manualmente.
                
        portales['id_cluster'] = asignacion_final
        
        ctos = []
        for i, idx_centro in enumerate(indices_centros):
            grupo = portales[portales['id_cluster'] == i]
            
            if not grupo.empty:
                nodo_centro = nodos_proyectados[idx_centro]
                x = grafo.nodes[nodo_centro]['x']
                y = grafo.nodes[nodo_centro]['y']
                
                ctos.append({
                    'id_cluster': i,
                    'id_portal_cto': idx_centro,
                    'geometry': Point(x, y),
                    'num_portales': len(grupo)
                })
                
        return portales, gpd.GeoDataFrame(ctos, crs=self.srs_destino)
    
    def agrupar_voronoi_red(self, gdf_portales, grafo_original, numero_ctos):
        portales = gdf_portales.copy().reset_index(drop=True)
        
        # 1. Componente conectada principal para evitar saltos al vacío
        componentes = list(nx.connected_components(grafo_original))
        componente_mayor = max(componentes, key=len)
        grafo = grafo_original.subgraph(componente_mayor).copy()
        
        # 2. Semillas iniciales lógicas (KMeans espacial)
        coords = np.array(list(zip(portales.geometry.x, portales.geometry.y)))
        kmeans = KMeans(n_clusters=numero_ctos, random_state=42, n_init=10).fit(coords)
        nodos_semilla = list(set([ox.distance.nearest_nodes(grafo, cx, cy) for cx, cy in kmeans.cluster_centers_]))
        
        # 3. Inundación topológica (Voronoi de red)
        # multi_source_dijkstra devuelve las distancias acumuladas y las rutas
        distancias_voronoi, paths = nx.multi_source_dijkstra(grafo, nodos_semilla, weight='length')
        mapa_voronoi = {nodo: ruta[0] for nodo, ruta in paths.items()}
        
        # 4. Proyección de portales a las aristas (tramos de calle)
        x_coords = portales.geometry.x.tolist()
        y_coords = portales.geometry.y.tolist()
        aristas_cercanas = ox.distance.nearest_edges(grafo, x_coords, y_coords)
        
        asignacion_final = np.full(len(portales), -1)
        
        # 5. Asignación con cálculo del punto de ruptura topológico
        for i, (u, v, key) in enumerate(aristas_cercanas):
            semilla_u = mapa_voronoi.get(u, nodos_semilla[0])
            semilla_v = mapa_voronoi.get(v, nodos_semilla[0])
            
            # Si la calle entera pertenece a un solo clúster
            if semilla_u == semilla_v:
                asignacion_final[i] = nodos_semilla.index(semilla_u)
            else:
                # Si la calle es frontera, medimos exactamente dónde corta el frente de onda
                p_geom = portales.geometry.iloc[i]
                datos_arista = grafo.get_edge_data(u, v)[key]
                
                # Reconstruimos la geometría de la calle para medir sobre ella
                if 'geometry' in datos_arista:
                    linea = datos_arista['geometry']
                else:
                    linea = LineString([(grafo.nodes[u]['x'], grafo.nodes[u]['y']),
                                        (grafo.nodes[v]['x'], grafo.nodes[v]['y'])])
                    
                # Proyectamos el portal sobre la calle para ver a cuántos metros está de cada extremo
                dist_proyectada = linea.project(p_geom)
                
                # OSMnx puede invertir el orden u-v de las coordenadas en la geometría, lo comprobamos
                coord_u = Point(grafo.nodes[u]['x'], grafo.nodes[u]['y'])
                if Point(linea.coords[0]).distance(coord_u) < 1e-3:
                    dist_a_u = dist_proyectada
                else:
                    dist_a_u = linea.length - dist_proyectada
                    
                dist_a_v = linea.length - dist_a_u
                
                # Calculamos la distancia total real sumando la red por detrás
                coste_via_u = distancias_voronoi.get(u, 999999) + dist_a_u
                coste_via_v = distancias_voronoi.get(v, 999999) + dist_a_v
                
                # Asignamos a la semilla que cueste menos metros de cable
                semilla_ganadora = semilla_u if coste_via_u < coste_via_v else semilla_v
                asignacion_final[i] = nodos_semilla.index(semilla_ganadora)

        # 6. Creación de la capa de CTOs
        ctos = []
        for i, semilla in enumerate(nodos_semilla):
            idx_portales = np.where(asignacion_final == i)[0]
            if len(idx_portales) == 0:
                continue
                
            x, y = grafo.nodes[semilla]['x'], grafo.nodes[semilla]['y']
            ctos.append({
                'id_cluster': i,
                'id_portal_cto': semilla,
                'geometry': Point(x, y),
                'num_portales': len(idx_portales)
            })
            
        portales['id_cluster'] = asignacion_final
        return portales, gpd.GeoDataFrame(ctos, crs=self.srs_destino)