import ast
import geopandas as gpd
import pandas as pd
from xlsxwriter.utility import xl_col_to_name
from entorno import inicializar_entorno

config, rutas = inicializar_entorno()

# Carga de datos de la fase definitiva
acceso = gpd.read_file(rutas["fase_2"], layer="Acceso_Logico")
troncal = gpd.read_file(rutas["fase_2"], layer="Distribucion_Logica")
ctos = gpd.read_file(rutas["fase_2"], layer="Nodos_CTO")

try:
    empalmes = gpd.read_file(rutas["fase_2"], layer="Cajas_Empalme")
except Exception:
    empalmes = pd.DataFrame(columns=['fibras_involucradas'])

# Lógica de conteo de saltos de empalme por cluster
conteo_empalmes = {}
if not empalmes.empty:
    for f_inv in empalmes['fibras_involucradas']:
        try:
            lista_clusters = ast.literal_eval(f_inv)
            for c in set(lista_clusters):
                conteo_empalmes[c] = conteo_empalmes.get(c, 0) + 1
        except Exception:
            pass

# Preparación de tablas de ingeniería
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

def perdida_splitter(portales):
    if portales <= 4: return 7.2
    elif portales <= 8: return 10.5
    elif portales <= 16: return 13.5
    else: return 17.0

df_detalle['Perdida_Splitter_dB'] = df_detalle['Portales_Splitter'].apply(perdida_splitter)
df_detalle = df_detalle.sort_values(by=['id_cluster', 'id_portal'])
df_detalle.rename(columns={'id_cluster': 'ID_CTO', 'id_portal': 'ID_Portal', 'Saltos_Empalme': 'Num_Empalmes_Troncal'}, inplace=True)

df_resumen = df_detalle.groupby('ID_CTO').agg(
    Portales_Cubiertos=('ID_Portal', 'count'),
    Fibra_Troncal_m=('Longitud_Troncal_m', 'first'),
    Num_Empalmes=('Num_Empalmes_Troncal', 'first'),
    Fibra_Acceso_Total_m=('Longitud_Acceso_m', 'sum')
).reset_index()

# Métricas para el Presupuesto Económico
metros_fibra_total = troncal.length.sum() + acceso.length.sum()
num_ctos = len(ctos)
num_empalmes = len(empalmes)
num_conectores = len(acceso) * 2

df_presupuesto = pd.DataFrame([
    {'Concepto': 'Fibra Óptica Total', 'Cantidad': round(metros_fibra_total, 2), 'Unidad': 'm'},
    {'Concepto': 'Cajas CTO', 'Cantidad': num_ctos, 'Unidad': 'ud'},
    {'Concepto': 'Cajas de Empalme (Torpedos)', 'Cantidad': num_empalmes, 'Unidad': 'ud'},
    {'Concepto': 'Conectores y Rosetas', 'Cantidad': num_conectores, 'Unidad': 'ud'}
])

with pd.ExcelWriter(rutas["excel"], engine='xlsxwriter') as writer:
    workbook = writer.book
    
    # --- HOJA 1: ANÁLISIS ÓPTICO ---
    ws1 = workbook.add_worksheet('Analisis_Fibra')
    writer.sheets['Analisis_Fibra'] = ws1
    
    f_header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
    f_cell = workbook.add_format({'border': 1})
    
    ws1.write('A1', 'Parámetros Ópticos', f_header)
    ws1.write('B1', 'Valor', f_header)
    ws1.write('A3', 'Atenuación Fibra (dB/km)', f_cell); ws1.write_number('B3', 0.25, f_cell)
    ws1.write('A4', 'Atenuación Fusión (dB)', f_cell); ws1.write_number('B4', 0.10, f_cell)
    ws1.write('A5', 'Atenuación Conector (dB)', f_cell); ws1.write_number('B5', 0.50, f_cell)

    start_row = 7
    df_resumen.to_excel(writer, sheet_name='Analisis_Fibra', startrow=start_row, index=False, header=False)
    ws1.add_table(start_row - 1, 0, start_row - 1 + len(df_resumen), len(df_resumen.columns) - 1, 
                 {'columns': [{'header': c} for c in df_resumen.columns], 'style': 'Table Style Light 9'})

    start_col_det = len(df_resumen.columns) + 2
    idx_t, idx_e, idx_s = df_detalle.columns.get_loc('Total_OLT_a_Portal_m') + start_col_det, \
                          df_detalle.columns.get_loc('Num_Empalmes_Troncal') + start_col_det, \
                          df_detalle.columns.get_loc('Perdida_Splitter_dB') + start_col_det
    
    formulas_opticas = [f"=({xl_col_to_name(idx_t)}{start_row+i+2}/1000)*$B$3 + {xl_col_to_name(idx_e)}{start_row+i+2}*$B$4 + 2*$B$5 + {xl_col_to_name(idx_s)}{start_row+i+2}" 
                        for i in range(len(df_detalle))]
    df_detalle['Atenuacion_Total_dB'] = formulas_opticas
    
    df_detalle.to_excel(writer, sheet_name='Analisis_Fibra', startrow=start_row, startcol=start_col_det, index=False, header=False)
    ws1.add_table(start_row - 1, start_col_det, start_row - 1 + len(df_detalle), start_col_det + len(df_detalle.columns) - 1,
                 {'columns': [{'header': c} for c in df_detalle.columns], 'style': 'Table Style Light 11'})

    # --- HOJA 2: RESUMEN DE COSTES ---
    ws2 = workbook.add_worksheet('Resumen_Costes')
    writer.sheets['Resumen_Costes'] = ws2

    ws2.write('A1', 'Precios Unitarios (CAPEX)', f_header)
    ws2.write('B1', 'Euros (€)', f_header)
    ws2.write('A3', 'Cable Fibra Óptica (€/m)', f_cell); ws2.write_number('B3', 1.20, f_cell)
    ws2.write('A4', 'Unidad CTO (€/ud)', f_cell); ws2.write_number('B4', 150.00, f_cell)
    ws2.write('A5', 'Unidad Empalme (€/ud)', f_cell); ws2.write_number('B5', 85.00, f_cell)
    ws2.write('A6', 'Kit Conector/Roseta (€/ud)', f_cell); ws2.write_number('B6', 15.00, f_cell)

    # Inyección de fórmulas con COORDENADAS ABSOLUTAS para evitar el error #¡REF!
    # Los datos se escriben a partir de la fila 8 de indexación (Fila 9 en el Excel)
    # y la columna "Cantidad" es la columna B.
    cost_formulas = [
        "=B9*$B$3",  # Fibra
        "=B10*$B$4", # CTO
        "=B11*$B$5", # Empalme
        "=B12*$B$6"  # Conectores
    ]
    df_presupuesto['Subtotal_€'] = cost_formulas

    df_presupuesto.to_excel(writer, sheet_name='Resumen_Costes', startrow=8, index=False, header=False)
    ws2.add_table(7, 0, 7 + len(df_presupuesto), len(df_presupuesto.columns) - 1, {
        'columns': [{'header': c} for c in df_presupuesto.columns],
        'style': 'Table Style Medium 2',
        'name': 'TablaPresupuesto'
    })

    # Suma final usando el rango estático (D9:D12) en lugar de la referencia de tabla
    total_row = 8 + len(df_presupuesto) + 1
    ws2.write(total_row, 0, 'TOTAL INVERSIÓN MATERIAL', f_header)
    ws2.write_formula(total_row, 3, "=SUM(D9:D12)", f_header)

print(f"Exportación técnica y económica finalizada en {rutas['excel']}")