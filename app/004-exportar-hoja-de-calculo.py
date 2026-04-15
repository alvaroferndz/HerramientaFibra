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

try:
    infra = gpd.read_file(rutas["fase_2"], layer="Canalizacion_Publica")[['geometry', 'tipo_instalacion', 'total_fibras']]
except Exception:
    infra = gpd.GeoDataFrame(columns=['geometry', 'tipo_instalacion', 'total_fibras'], crs=config['proyecto']['srs'])

try:
    aco = gpd.read_file(rutas["fase_2"], layer="Acometidas_Privadas")[['geometry', 'tipo_instalacion', 'total_fibras']]
except Exception:
    aco = gpd.GeoDataFrame(columns=['geometry', 'tipo_instalacion', 'total_fibras'], crs=config['proyecto']['srs'])

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

metros_fibra_total = troncal.geometry.length.sum() + acceso.geometry.length.sum()
num_ctos = len(ctos)
num_empalmes = len(empalmes)
num_conectores = len(acceso) * 2

df_obra = pd.concat([infra, aco], ignore_index=True)
if not df_obra.empty:
    df_obra['length'] = df_obra.geometry.length
    if 'total_fibras' not in df_obra.columns:
        df_obra['total_fibras'] = 1
else:
    df_obra = pd.DataFrame({'length': [], 'tipo_instalacion': [], 'total_fibras': []})

def metros_por_tipo(codigo):
    if df_obra.empty: return 0
    return df_obra[df_obra['tipo_instalacion'] == codigo]['length'].sum()

df_mediciones = pd.DataFrame([
    {'Concepto': 'Cableado Fibra Óptica (Total Teórico)', 'Cantidad': round(metros_fibra_total, 2), 'Unidad': 'm'},
    {'Concepto': 'Cajas CTO', 'Cantidad': num_ctos, 'Unidad': 'ud'},
    {'Concepto': 'Cajas de Empalme (Torpedos)', 'Cantidad': num_empalmes, 'Unidad': 'ud'},
    {'Concepto': 'Kits de Conectorización y Rosetas', 'Cantidad': num_conectores, 'Unidad': 'ud'},
    {'Concepto': 'Obra Civil: Tendido Aéreo (Postes)', 'Cantidad': round(metros_por_tipo(1), 2), 'Unidad': 'm'},
    {'Concepto': 'Obra Civil: Zanja (Soterrado)', 'Cantidad': round(metros_por_tipo(2), 2), 'Unidad': 'm'},
    {'Concepto': 'Obra Civil: Canalización Existente', 'Cantidad': round(metros_por_tipo(3), 2), 'Unidad': 'm'},
    {'Concepto': 'Obra Civil: Despliegue en Fachada', 'Cantidad': round(metros_por_tipo(4), 2), 'Unidad': 'm'}
])

df_optico = pd.DataFrame([
    {'Concepto': 'Cableado Fibra Óptica (Promedio)', 'Subtotal_€': "=B14*$B$3"},
    {'Concepto': 'Cajas CTO', 'Subtotal_€': "=B15*$B$4"},
    {'Concepto': 'Cajas de Empalme (Torpedos)', 'Subtotal_€': "=B16*$B$5"},
    {'Concepto': 'Kits de Conectorización y Rosetas', 'Subtotal_€': "=B17*$B$6"}
])

df_civil = pd.DataFrame([
    {'Concepto': 'Obra Civil: Tendido Aéreo (Postes)', 'Subtotal_€': "=B18*$B$7"},
    {'Concepto': 'Obra Civil: Zanja (Soterrado)', 'Subtotal_€': "=B19*$B$8"},
    {'Concepto': 'Obra Civil: Canalización Existente', 'Subtotal_€': "=B20*$B$9"},
    {'Concepto': 'Obra Civil: Despliegue en Fachada', 'Subtotal_€': "=B21*$B$10"}
])

CALIBRES_COMERCIALES = [2, 4, 8, 16, 24, 48, 64, 96, 128, 256]

def obtener_calibre_comercial(n_fibras):
    if pd.isna(n_fibras) or n_fibras <= 0: return 2
    for calibre in CALIBRES_COMERCIALES:
        if n_fibras <= calibre: return calibre
    return CALIBRES_COMERCIALES[-1]

if not df_obra.empty:
    df_obra['Manguera_Comercial'] = df_obra['total_fibras'].apply(obtener_calibre_comercial)
    df_mangueras_det = df_obra.groupby(['total_fibras', 'Manguera_Comercial']).agg(Metros_Totales=('length', 'sum')).reset_index()
    df_mangueras_det['Metros_Totales'] = df_mangueras_det['Metros_Totales'].round(2)
    df_mangueras_det.rename(columns={'total_fibras': 'Fibras Reales', 'Manguera_Comercial': 'Calibre Comercial'}, inplace=True)
    df_mangueras_res = df_obra.groupby('Manguera_Comercial').agg(Total_Metros=('length', 'sum')).reset_index()
    df_mangueras_res['Total_Metros'] = df_mangueras_res['Total_Metros'].round(2)
    df_mangueras_res.rename(columns={'Manguera_Comercial': 'Tipo Manguera (Fibras)'}, inplace=True)
else:
    df_mangueras_det = pd.DataFrame(columns=['Fibras Reales', 'Calibre Comercial', 'Metros_Totales'])
    df_mangueras_res = pd.DataFrame(columns=['Tipo Manguera (Fibras)', 'Total_Metros'])

with pd.ExcelWriter(rutas["excel"], engine='xlsxwriter') as writer:
    workbook = writer.book
    f_header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
    f_cell = workbook.add_format({'border': 1})
    
    ws1 = workbook.add_worksheet('Analisis_Fibra')
    writer.sheets['Analisis_Fibra'] = ws1
    ws1.write('A1', 'Parámetros Ópticos', f_header)
    ws1.write('B1', 'Valor', f_header)
    ws1.write('A3', 'Atenuación Fibra (dB/km)', f_cell); ws1.write_number('B3', 0.25, f_cell)
    ws1.write('A4', 'Atenuación Fusión (dB)', f_cell); ws1.write_number('B4', 0.10, f_cell)
    ws1.write('A5', 'Atenuación Conector (dB)', f_cell); ws1.write_number('B5', 0.50, f_cell)
    
    start_row = 7
    df_resumen.to_excel(writer, sheet_name='Analisis_Fibra', startrow=start_row, index=False, header=False)
    ws1.add_table(start_row - 1, 0, start_row - 1 + len(df_resumen), len(df_resumen.columns) - 1, {'columns': [{'header': c} for c in df_resumen.columns], 'style': 'Table Style Light 9'})
    
    start_col_det = len(df_resumen.columns) + 2
    idx_t, idx_e, idx_s = df_detalle.columns.get_loc('Total_OLT_a_Portal_m') + start_col_det, df_detalle.columns.get_loc('Num_Empalmes_Troncal') + start_col_det, df_detalle.columns.get_loc('Perdida_Splitter_dB') + start_col_det
    formulas_opticas = [f"=({xl_col_to_name(idx_t)}{start_row+i+2}/1000)*$B$3 + {xl_col_to_name(idx_e)}{start_row+i+2}*$B$4 + 2*$B$5 + {xl_col_to_name(idx_s)}{start_row+i+2}" for i in range(len(df_detalle))]
    df_detalle['Atenuacion_Total_dB'] = formulas_opticas
    df_detalle.to_excel(writer, sheet_name='Analisis_Fibra', startrow=start_row, startcol=start_col_det, index=False, header=False)
    ws1.add_table(start_row - 1, start_col_det, start_row - 1 + len(df_detalle), start_col_det + len(df_detalle.columns) - 1, {'columns': [{'header': c} for c in df_detalle.columns], 'style': 'Table Style Light 11'})

    ws2 = workbook.add_worksheet('Mediciones_y_Costes')
    writer.sheets['Mediciones_y_Costes'] = ws2
    ws2.set_column('A:A', 38); ws2.set_column('B:C', 18); ws2.set_column('E:F', 22)
    
    ws2.write('A1', 'Precios Unitarios', f_header)
    ws2.write('B1', 'Euros (€)', f_header)
    for i, (conc, prec) in enumerate([('Cable Fibra Óptica (€/m)', 1.2), ('Unidad CTO (€/ud)', 150.0), ('Unidad Empalme (€/ud)', 85.0), ('Kit Conector/Roseta (€/ud)', 15.0), ('Obra: Tendido Aéreo (€/m)', 8.5), ('Obra: Zanja Soterrada (€/m)', 45.0), ('Obra: Canalización Existente (€/m)', 2.5), ('Obra: Despliegue Fachada (€/m)', 12.0)]):
        ws2.write(f'A{i+3}', conc, f_cell); ws2.write_number(f'B{i+3}', prec, f_cell)

    ws2.write('A12', 'CUADRO DE MEDICIONES FÍSICAS', f_header)
    df_mediciones.to_excel(writer, sheet_name='Mediciones_y_Costes', startrow=13, index=False, header=False)
    ws2.add_table(12, 0, 12 + len(df_mediciones), len(df_mediciones.columns) - 1, {'columns': [{'header': c} for c in df_mediciones.columns], 'style': 'Table Style Light 13', 'name': 'TablaMediciones'})

    idx_optico = 24
    ws2.write(idx_optico, 0, 'PRESUPUESTO: MATERIAL ÓPTICO', f_header)
    df_optico.to_excel(writer, sheet_name='Mediciones_y_Costes', startrow=idx_optico+1, index=False, header=False)
    ws2.add_table(idx_optico, 0, idx_optico + len(df_optico), len(df_optico.columns) - 1, {'columns': [{'header': c} for c in df_optico.columns], 'style': 'Table Style Medium 2', 'name': 'TablaOptico'})
    idx_sub_optico = idx_optico + len(df_optico) + 1
    ws2.write(idx_sub_optico, 0, 'SUBTOTAL MATERIAL ÓPTICO', f_header); ws2.write_formula(idx_sub_optico, 1, f"=SUM(B{idx_optico+2}:B{idx_sub_optico})", f_header)

    idx_civil = idx_sub_optico + 2
    ws2.write(idx_civil, 0, 'PRESUPUESTO: OBRA CIVIL', f_header)
    df_civil.to_excel(writer, sheet_name='Mediciones_y_Costes', startrow=idx_civil+1, index=False, header=False)
    ws2.add_table(idx_civil, 0, idx_civil + len(df_civil), len(df_civil.columns) - 1, {'columns': [{'header': c} for c in df_civil.columns], 'style': 'Table Style Medium 3', 'name': 'TablaCivil'})
    idx_sub_civil = idx_civil + len(df_civil) + 1
    ws2.write(idx_sub_civil, 0, 'SUBTOTAL OBRA CIVIL', f_header); ws2.write_formula(idx_sub_civil, 1, f"=SUM(B{idx_civil+2}:B{idx_sub_civil})", f_header)

    idx_total = idx_sub_civil + 2
    ws2.write(idx_total, 0, 'TOTAL INVERSIÓN GLOBAL (CAPEX)', f_header)
    ws2.write_formula(idx_total, 1, f"=B{idx_sub_optico+1}+B{idx_sub_civil+1}", f_header)

    fila_inv = idx_total + 4
    ws2.write(fila_inv - 1, 0, 'DESGLOSE DETALLADO DE FIBRAS', f_header)
    df_mangueras_det.to_excel(writer, sheet_name='Mediciones_y_Costes', startrow=fila_inv, index=False, header=False)
    ws2.add_table(fila_inv - 1, 0, fila_inv - 1 + len(df_mangueras_det), len(df_mangueras_det.columns) - 1, {'columns': [{'header': c} for c in df_mangueras_det.columns], 'style': 'Table Style Light 14', 'name': 'TablaManguerasDet'})

    ws2.write(fila_inv - 1, 5, 'TOTALES DE COMPRA POR MANGUERA', f_header)
    df_mangueras_res.to_excel(writer, sheet_name='Mediciones_y_Costes', startrow=fila_inv, startcol=5, index=False, header=False)
    ws2.add_table(fila_inv - 1, 5, fila_inv - 1 + len(df_mangueras_res), 5 + len(df_mangueras_res.columns) - 1, {'columns': [{'header': c} for c in df_mangueras_res.columns], 'style': 'Table Style Medium 4', 'name': 'TablaManguerasRes'})

print(f"Exportación técnica finalizada en {rutas['excel']}")