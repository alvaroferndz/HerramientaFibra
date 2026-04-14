import ast
import geopandas as gpd
import pandas as pd
from xlsxwriter.utility import xl_col_to_name
from entorno import inicializar_entorno

config, rutas = inicializar_entorno()

acceso = gpd.read_file(rutas["fase_2"], layer="Acceso_Logico")
troncal = gpd.read_file(rutas["fase_2"], layer="Distribucion_Logica")
ctos = gpd.read_file(rutas["fase_2"], layer="Nodos_CTO")

try:
    empalmes = gpd.read_file(rutas["fase_2"], layer="Cajas_Empalme")
except Exception:
    empalmes = pd.DataFrame(columns=['fibras_involucradas'])

conteo_empalmes = {}
if not empalmes.empty:
    for f_inv in empalmes['fibras_involucradas']:
        try:
            lista_clusters = ast.literal_eval(f_inv)
            for c in set(lista_clusters):
                conteo_empalmes[c] = conteo_empalmes.get(c, 0) + 1
        except Exception:
            pass

acceso['Longitud_Acceso_m'] = acceso.geometry.length.round(2)
df_acceso = acceso[['id_cluster', 'id_portal', 'Longitud_Acceso_m']].copy()

df_troncal = pd.DataFrame({
    'id_cluster': ctos['id_cluster'],
    'Longitud_Troncal_m': troncal.geometry.length.round(2),
    'Saltos_Empalme': ctos['id_cluster'].map(conteo_empalmes).fillna(0).astype(int),
    'Portales_Splitter': ctos['num_portales']
})

df_detalle = pd.merge(df_acceso, df_troncal, on='id_cluster', how='left')
df_detalle['Total_OLT_a_Portal_m'] = df_detalle['Longitud_Troncal_m'] + df_detalle['Longitud_Acceso_m']

# Calcular la pérdida teórica por inserción del splitter según su tamaño
def perdida_splitter(portales):
    if portales <= 2: return 4.0
    elif portales <= 4: return 7.2
    elif portales <= 8: return 10.5
    elif portales <= 16: return 13.5
    elif portales <= 32: return 17.0
    elif portales <= 64: return 20.5
    else: return 25.0

df_detalle['Perdida_Splitter_dB'] = df_detalle['Portales_Splitter'].apply(perdida_splitter)

# Orden y renombramiento inicial
df_detalle = df_detalle.sort_values(by=['id_cluster', 'id_portal'])
df_detalle.rename(columns={
    'id_cluster': 'ID_CTO',
    'id_portal': 'ID_Portal',
    'Saltos_Empalme': 'Num_Empalmes_Troncal'
}, inplace=True)

# Resumen general por CTO (necesitamos crearlo primero para saber cuánto ocupa)
df_resumen = df_detalle.groupby('ID_CTO').agg(
    Portales_Cubiertos=('ID_Portal', 'count'),
    Fibra_Troncal_m=('Longitud_Troncal_m', 'first'),
    Num_Empalmes=('Num_Empalmes_Troncal', 'first'),
    Fibra_Acceso_Total_m=('Longitud_Acceso_m', 'sum')
).reset_index()

# INYECCIÓN DINÁMICA DE FÓRMULAS CLÁSICAS PARA EVITAR CORRUPCIÓN XML
start_row = 7
start_col_detalle = len(df_resumen.columns) + 2

# Obtenemos las letras de las columnas exactas (ej: "G", "J", etc.)
idx_total = df_detalle.columns.get_loc('Total_OLT_a_Portal_m') + start_col_detalle
idx_empalmes = df_detalle.columns.get_loc('Num_Empalmes_Troncal') + start_col_detalle
idx_splitter = df_detalle.columns.get_loc('Perdida_Splitter_dB') + start_col_detalle

col_total = xl_col_to_name(idx_total)
col_empalmes = xl_col_to_name(idx_empalmes)
col_splitter = xl_col_to_name(idx_splitter)

formulas = []
for i in range(len(df_detalle)):
    excel_row = start_row + i + 2 # +1 por la cabecera, +1 para base 1 de Excel
    f = f"=({col_total}{excel_row}/1000)*$B$3 + {col_empalmes}{excel_row}*$B$4 + 2*$B$5 + {col_splitter}{excel_row}"
    formulas.append(f)
    
df_detalle['Atenuacion_Total_dB'] = formulas

# EXPORTACIÓN NATIVA A FORMATO TABLA DE EXCEL
with pd.ExcelWriter(rutas["excel"], engine='xlsxwriter') as writer:
    workbook = writer.book
    worksheet = workbook.add_worksheet('Analisis_Fibra')
    writer.sheets['Analisis_Fibra'] = worksheet

    # 1. Diseñar el bloque de Parámetros Globales
    formato_header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
    formato_celda = workbook.add_format({'border': 1})

    worksheet.write('A1', 'Parámetros Ópticos', formato_header)
    worksheet.write('B1', 'Valor', formato_header)
    
    worksheet.write('A3', 'Atenuación Fibra (dB/km)', formato_celda)
    worksheet.write_number('B3', 0.25, formato_celda)
    
    worksheet.write('A4', 'Atenuación Fusión (dB)', formato_celda)
    worksheet.write_number('B4', 0.10, formato_celda)
    
    worksheet.write('A5', 'Atenuación Conector (dB)', formato_celda)
    worksheet.write_number('B5', 0.50, formato_celda)

    # 2. Inyectar las Tablas Dinámicas
    # Tabla 1: Resumen
    df_resumen.to_excel(writer, sheet_name='Analisis_Fibra', startrow=start_row, startcol=0, index=False, header=False)
    worksheet.add_table(start_row - 1, 0, start_row - 1 + len(df_resumen), len(df_resumen.columns) - 1, {
        'columns': [{'header': c} for c in df_resumen.columns],
        'style': 'Table Style Light 9',
        'name': 'Resumen_CTOs'
    })

    # Tabla 2: Detalle (ahora con fórmulas estándar invulnerables)
    df_detalle.to_excel(writer, sheet_name='Analisis_Fibra', startrow=start_row, startcol=start_col_detalle, index=False, header=False)
    worksheet.add_table(start_row - 1, start_col_detalle, start_row - 1 + len(df_detalle), start_col_detalle + len(df_detalle.columns) - 1, {
        'columns': [{'header': c} for c in df_detalle.columns],
        'style': 'Table Style Light 11',
        'name': 'Detalle_Portales'
    })

print(f"Exportación paramétrica completada en {rutas['excel']}")