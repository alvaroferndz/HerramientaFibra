import requests
import geopandas as gpd
import numpy as np
import pandas as pd
import os

class GestorDatos:
    def __init__(self, srs_destino="EPSG:25830", wfs_url="http://ovc.catastro.meh.es/INSPIRE/wfsAD.aspx"):
        self.srs_destino = srs_destino
        self.wfs_url_direcciones = wfs_url

    def cargar_area_diseno(self, ruta_geojson):
        gdf_inicial = gpd.read_file(ruta_geojson).to_crs(self.srs_destino)
        area_diseno = gdf_inicial[gdf_inicial.geometry.type == 'Polygon']
        poligono_base = area_diseno.geometry.union_all()
        
        gdf_punto = gdf_inicial[gdf_inicial.geometry.type == 'Point']
        if gdf_punto.empty:
            raise ValueError("El GeoJSON no contiene el punto de la OLT.")
            
        punto_olt = gdf_punto.geometry.iloc[0]
        gdf_olt = gdf_punto.head(1)
        
        return area_diseno, poligono_base, punto_olt, gdf_olt

    def _generar_cuadricula(self, area_diseno, tamano_celda_m):
        minx, miny, maxx, maxy = area_diseno.total_bounds
        tramos_x = np.arange(minx, maxx, tamano_celda_m)
        tramos_y = np.arange(miny, maxy, tamano_celda_m)
        
        celdas = []
        for x in tramos_x:
            for y in tramos_y:
                celda_maxx = min(x + tamano_celda_m, maxx)
                celda_maxy = min(y + tamano_celda_m, maxy)
                celdas.append(f"{int(x)},{int(y)},{int(celda_maxx)},{int(celda_maxy)}")
                
        return celdas

    def descargar_direcciones_portales(self, area_diseno, poligono_base):
        lista_bboxes = self._generar_cuadricula(area_diseno, 500)
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
        gdf_recortado = gpd.clip(gdf_completo, poligono_base)
        
        return gdf_recortado.drop_duplicates(subset=['geometry'])

    def exportar_geopackage(self, archivo_salida, gdf_distribucion, gdf_acceso, gdf_infraestructura, gdf_acometidas, gdf_ctos, gdf_portales, gdf_olt):
        if not gdf_distribucion.empty:
            gdf_distribucion.to_file(archivo_salida, layer="Distribucion_Logica", driver="GPKG")
        if not gdf_acceso.empty:
            gdf_acceso.to_file(archivo_salida, layer="Acceso_Logico", driver="GPKG")
        if not gdf_infraestructura.empty:
            gdf_infraestructura.to_file(archivo_salida, layer="Canalizacion_Publica", driver="GPKG")
        if not gdf_acometidas.empty:
            gdf_acometidas.to_file(archivo_salida, layer="Acometidas_Privadas", driver="GPKG")
            
        gdf_olt.to_file(archivo_salida, layer="Nodo_OLT", driver="GPKG")
        gdf_ctos.to_file(archivo_salida, layer="Nodos_CTO", driver="GPKG")
        
        if not gdf_portales.empty:
            gdf_portales.to_file(archivo_salida, layer="Portales_Demanda", driver="GPKG")