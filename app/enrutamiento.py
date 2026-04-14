import networkx as nx
import geopandas as gpd
import osmnx as ox
from shapely.geometry import LineString, Point
from shapely.ops import substring

class EnrutadorFibra:
    def __init__(self, srs_destino, punto_olt):
        self.srs_destino = srs_destino
        self.punto_olt = punto_olt

    def calcular_distribucion(self, grafo, gdf_viales, gdf_ctos):
        nodo_olt = ox.distance.nearest_nodes(grafo, self.punto_olt.x, self.punto_olt.y)
        distribucion = []
        rutas_troncales = {}
        tramos_fuera_grafo = []
        aristas_insercion = []
        
        for _, cto in gdf_ctos.iterrows():
            id_cluster = cto['id_cluster']
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
                rutas_troncales[id_cluster] = ruta_nodos
                
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

    def calcular_acceso(self, grafo, gdf_viales, gdf_portales_cluster, gdf_ctos):
        acceso = []
        rutas_acceso = []
        tramos_fuera_grafo = []
        aristas_insercion = []
        
        for idx_portal, portal in gdf_portales_cluster.iterrows():
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
                
                acceso.append({
                    'geometry': LineString(coords_finales), 
                    'id_cluster': id_cluster,
                    'id_portal': portal.name 
                })
                
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

    def calcular_infraestructura_fisica(self, grafo, dict_rutas_troncales, listas_nodos_acceso, aristas_troncal_insercion, aristas_acceso_insercion):
        nx.set_edge_attributes(grafo, 0, 'fibras_troncal')
        nx.set_edge_attributes(grafo, 0, 'fibras_acceso')
        
        for ruta in dict_rutas_troncales.values():
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

    def calcular_empalmes(self, grafo, dict_rutas_troncales):
        transiciones = {}
        fibras_pasantes = {}
        fibras_terminantes = {}
        
        nodo_olt = ox.distance.nearest_nodes(grafo, self.punto_olt.x, self.punto_olt.y)

        for id_cluster, ruta in dict_rutas_troncales.items():
            for i in range(len(ruta)):
                nodo = ruta[i]
                
                if nodo not in transiciones:
                    transiciones[nodo] = set()
                if nodo not in fibras_pasantes:
                    fibras_pasantes[nodo] = []
                if nodo not in fibras_terminantes:
                    fibras_terminantes[nodo] = []
                    
                if i < len(ruta) - 1:
                    # La fibra continúa hacia otro nodo
                    siguiente = ruta[i+1]
                    transiciones[nodo].add(siguiente)
                    fibras_pasantes[nodo].append(id_cluster)
                else:
                    # La fibra termina en este nodo para alimentar la CTO
                    fibras_terminantes[nodo].append(id_cluster)

        empalmes = []
        for nodo in transiciones.keys():
            # Omitimos plantar un empalme en la central OLT para no ensuciar
            if nodo == nodo_olt:
                continue
                
            es_bifurcacion = len(transiciones[nodo]) > 1
            es_sangrado = len(fibras_terminantes[nodo]) > 0 and len(fibras_pasantes[nodo]) > 0
            
            # Si el cable se divide en varias calles, o si soltamos fibra pero el mazo sigue
            if es_bifurcacion or es_sangrado:
                x = grafo.nodes[nodo]['x']
                y = grafo.nodes[nodo]['y']
                todas_fibras = fibras_pasantes[nodo] + fibras_terminantes[nodo]
                
                if es_bifurcacion and es_sangrado:
                    tipo = "Bifurcación y Sangrado"
                elif es_bifurcacion:
                    tipo = "Bifurcación"
                else:
                    tipo = "Sangrado"
                
                empalmes.append({
                    'id_nudo': nodo,
                    'tipo': tipo,
                    'fibras_involucradas': str(todas_fibras),
                    'total_fibras_entrantes': len(todas_fibras),
                    'rutas_salientes': len(transiciones[nodo]),
                    'geometry': Point(x, y)
                })

        if not empalmes:
            return gpd.GeoDataFrame(columns=['id_nudo', 'tipo', 'fibras_involucradas', 'total_fibras_entrantes', 'rutas_salientes', 'geometry'], crs=self.srs_destino)
            
        return gpd.GeoDataFrame(empalmes, crs=self.srs_destino)