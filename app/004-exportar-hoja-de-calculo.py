import geopandas as gpd
import pandas as pd
from entorno import inicializar_entorno

config, rutas = inicializar_entorno()

# Carga de capas finales
acceso = gpd.read_file(rutas["fase_2"], layer="Acceso_Logico")
troncal = gpd.read_file(rutas["fase_2"], layer="Distribucion_Logica")
ctos = gpd.read_file(rutas["fase_2"], layer="Nodos_CTO")

# 1. Preparación de datos de red
acceso['Longitud_Acceso_m'] = acceso.geometry.length.round(2)
df_acceso = acceso[['id_cluster', 'id_portal', 'Longitud_Acceso_m']].copy()

df_troncal = pd.DataFrame({
    'id_cluster': ctos['id_cluster'],
    'Longitud_Troncal_m': troncal.geometry.length.round(2)
})

# 2. Fusión (Merge) para calcular la distancia OLT -> Portal
df_detalle_extremo_a_extremo = pd.merge(df_acceso, df_troncal, on='id_cluster', how='left')
df_detalle_extremo_a_extremo['Total_OLT_a_Portal_m'] = df_detalle_extremo_a_extremo['Longitud_Troncal_m'] + df_detalle_extremo_a_extremo['Longitud_Acceso_m']

# Ordenamos y renombramos para que quede profesional
df_detalle_extremo_a_extremo = df_detalle_extremo_a_extremo.sort_values(by=['id_cluster', 'id_portal'])
df_detalle_extremo_a_extremo.rename(columns={
    'id_cluster': 'ID_CTO',
    'id_portal': 'ID_Portal'
}, inplace=True)

# 3. Resumen agrupado por CTO
df_resumen = df_detalle_extremo_a_extremo.groupby('ID_CTO').agg(
    Portales_Cubiertos=('ID_Portal', 'count'),
    Fibra_Troncal_m=('Longitud_Troncal_m', 'first'),
    Fibra_Acceso_Total_m=('Longitud_Acceso_m', 'sum'),
    Media_Acometida_m=('Longitud_Acceso_m', 'mean')
).reset_index()
df_resumen['Media_Acometida_m'] = df_resumen['Media_Acometida_m'].round(2)

# 4. Exportación horizontal
with pd.ExcelWriter(rutas["excel"], engine='openpyxl') as writer:
    # Bloque 1: Resumen de infraestructura por clúster
    df_resumen.to_excel(writer, sheet_name='Analisis_Fibra', index=False, startcol=0)
    
    # Bloque 2: Detalle de distancias OLT -> Portal
    col_detalle = len(df_resumen.columns) + 2
    df_detalle_extremo_a_extremo.to_excel(writer, sheet_name='Analisis_Fibra', index=False, startcol=col_detalle)

print(f"Exportación detallada finalizada en {rutas['excel']}")