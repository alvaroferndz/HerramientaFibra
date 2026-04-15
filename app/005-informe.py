import pandas as pd
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
from entorno import inicializar_entorno
from datos import GestorDatos
from viales import GestorVial

config, rutas = inicializar_entorno()
archivo_excel = rutas["excel"]
directorio_base = Path(rutas["fase_0"]).parent
srs_proyecto = config['proyecto']['srs']

nombre_proyecto = Path(rutas["geojson"]).stem.replace('_', ' ').replace('-', ' ').title()
print(f"Generando Informe Maestro para: {nombre_proyecto}")

gestor_datos = GestorDatos(srs_proyecto)
gestor_vial = GestorVial(srs_proyecto)

# --- 1. PREPARACIÓN DE CARTOGRAFÍA ---
print("Sincronizando capas y descargando fondo vial...")
area_diseno, poligono_base, _, _ = gestor_datos.cargar_area_diseno(rutas["geojson"])
_, viales = gestor_vial.obtener_red_vial(poligono_base)

portales = gpd.read_file(rutas["fase_2"], layer="Portales_Demanda")
ctos = gpd.read_file(rutas["fase_2"], layer="Nodos_CTO")
olt = gpd.read_file(rutas["fase_2"], layer="Nodo_OLT")
troncal = gpd.read_file(rutas["fase_2"], layer="Distribucion_Logica")
acceso = gpd.read_file(rutas["fase_2"], layer="Acceso_Logico")
infraestructura = gpd.read_file(rutas["fase_2"], layer="Canalizacion_Publica")
acometidas = gpd.read_file(rutas["fase_2"], layer="Acometidas_Privadas")

try:
    empalmes = gpd.read_file(rutas["fase_2"], layer="Cajas_Empalme")
    cant_empalmes = len(empalmes)
except Exception:
    empalmes = gpd.GeoDataFrame()
    cant_empalmes = 0

# --- 2. RENDERIZADO CARTOGRÁFICO (5 MAPAS) ---
print("Renderizando cartografía técnica...")
estilos_mapa = {'figsize': (12, 10), 'dpi': 300}

def guardar_mapa(fig, nombre):
    fig.savefig(directorio_base / nombre, bbox_inches='tight', dpi=estilos_mapa['dpi'])
    plt.close(fig)

# Mapa 1: Área General
fig, ax = plt.subplots(figsize=estilos_mapa['figsize'])
viales.plot(ax=ax, color='#e0e0e0', linewidth=1); area_diseno.plot(ax=ax, color='none', edgecolor='black', linewidth=2)
portales.plot(ax=ax, color='#0056b3', markersize=15, alpha=0.5); olt.plot(ax=ax, color='#8e44ad', marker='s', markersize=120)
ax.axis('off'); guardar_mapa(fig, "area_despliegue.png")

# Mapa 2: Red Troncal
fig, ax = plt.subplots(figsize=estilos_mapa['figsize'])
viales.plot(ax=ax, color='#f0f0f0', linewidth=1); troncal.plot(ax=ax, color='#e67e22', linewidth=2.5)
ctos.plot(ax=ax, color='#16a085', marker='^', markersize=80); olt.plot(ax=ax, color='#8e44ad', marker='s', markersize=120)
if not empalmes.empty: empalmes.plot(ax=ax, color='#c0392b', marker='*', markersize=100)
ax.axis('off'); guardar_mapa(fig, "distribucion_troncal.png")

# Mapa 3: Red de Acceso
fig, ax = plt.subplots(figsize=estilos_mapa['figsize'])
viales.plot(ax=ax, color='#f0f0f0', linewidth=1); acceso.plot(ax=ax, color='#3498db', linewidth=1, alpha=0.7)
ctos.plot(ax=ax, color='#16a085', marker='^', markersize=80); portales.plot(ax=ax, color='#2c3e50', markersize=8)
ax.axis('off'); guardar_mapa(fig, "acceso_logico.png")

# Mapa 4: Densidad de Fibra (Obra Civil)
fig, ax = plt.subplots(figsize=estilos_mapa['figsize'])
viales.plot(ax=ax, color='#f0f0f0', linewidth=1)
infraestructura.plot(ax=ax, column='total_fibras', cmap='YlOrRd', linewidth=3, legend=True)
ax.axis('off'); guardar_mapa(fig, "obra_civil.png")

# Mapa 5: Tipos de Instalación Constructiva
print("Generando mapa de métodos constructivos...")
fig, ax = plt.subplots(figsize=estilos_mapa['figsize'])
viales.plot(ax=ax, color='#f0f0f0', linewidth=1)
red_fisica = pd.concat([infraestructura, acometidas], ignore_index=True)
colores_inst = {1: '#3498db', 2: '#e74c3c', 3: '#2ecc71', 4: '#9b59b6'}
labels_inst = {1: 'Aérea (Poste)', 2: 'Zanja (Soterrado)', 3: 'Existente', 4: 'Fachada'}

for tipo, color in colores_inst.items():
    subset = red_fisica[red_fisica['tipo_instalacion'] == tipo]
    if not subset.empty:
        subset.plot(ax=ax, color=color, linewidth=2.5, label=labels_inst[tipo])

ax.legend(title="Método Constructivo", loc='lower right', fontsize=10)
ax.axis('off'); guardar_mapa(fig, "tipos_instalacion.png")


# --- 3. EXTRACCIÓN DE DATOS Y CÁLCULOS ---
print("Extrayendo métricas financieras y calculando materiales...")
df_analisis = pd.read_excel(archivo_excel, sheet_name='Analisis_Fibra', skiprows=6)
col_atenuacion = [c for c in df_analisis.columns if 'Atenuacion' in c][-1]
atenuacion_max = df_analisis[col_atenuacion].max()
atenuacion_media = df_analisis[col_atenuacion].mean()

total_ctos = df_analisis['ID_CTO'].dropna().nunique()
total_portales = df_analisis['Portales_Cubiertos'].sum()
fibra_troncal = df_analisis['Fibra_Troncal_m'].sum()
fibra_acceso = df_analisis['Fibra_Acceso_Total_m'].sum()
fibra_total = fibra_troncal + fibra_acceso
dist_max = df_analisis['Total_OLT_a_Portal_m'].max()
dist_min = df_analisis['Total_OLT_a_Portal_m'].min()

# Precios del Excel
df_precios = pd.read_excel(archivo_excel, sheet_name='Mediciones_y_Costes', header=None)
precio_fibra = df_precios.iloc[2, 1]
precio_cto = df_precios.iloc[3, 1]
precio_empalme = df_precios.iloc[4, 1]
precio_conector = df_precios.iloc[5, 1]
precio_aereo = df_precios.iloc[6, 1]
precio_zanja = df_precios.iloc[7, 1]
precio_existente = df_precios.iloc[8, 1]
precio_fachada = df_precios.iloc[9, 1]

# Cantidades Físicas
cant_fibra = fibra_total
cant_ctos = total_ctos
cant_empalmes = cant_empalmes
cant_conectores = len(acceso) * 2

def sumar_tipo(cod):
    if red_fisica.empty: return 0
    return red_fisica[red_fisica['tipo_instalacion'] == cod].geometry.length.sum()

cant_aereo = sumar_tipo(1)
cant_zanja = sumar_tipo(2)
cant_existente = sumar_tipo(3)
cant_fachada = sumar_tipo(4)

# Subtotales Económicos
sub_optico = (cant_fibra * precio_fibra) + (cant_ctos * precio_cto) + (cant_empalmes * precio_empalme) + (cant_conectores * precio_conector)
sub_civil = (cant_aereo * precio_aereo) + (cant_zanja * precio_zanja) + (cant_existente * precio_existente) + (cant_fachada * precio_fachada)
coste_total = sub_optico + sub_civil

# Cálculo de Mangueras
CALIBRES_COMERCIALES = [2, 4, 8, 16, 24, 48, 64, 96, 128, 256]
def obtener_calibre_comercial(n_fibras):
    if pd.isna(n_fibras) or n_fibras <= 0: return 2
    for calibre in CALIBRES_COMERCIALES:
        if n_fibras <= calibre: return calibre
    return CALIBRES_COMERCIALES[-1]

filas_mangueras_html = ""
if not red_fisica.empty:
    if 'total_fibras' not in red_fisica.columns:
        red_fisica['total_fibras'] = 1
    
    red_fisica['Manguera_Comercial'] = red_fisica['total_fibras'].apply(obtener_calibre_comercial)
    df_mangueras = red_fisica.groupby('Manguera_Comercial').agg(Total_Metros=('geometry', lambda x: x.length.sum())).reset_index()
    
    for _, row in df_mangueras.iterrows():
        filas_mangueras_html += f"<tr><td>Manguera de {int(row['Manguera_Comercial'])} Fibras</td><td class='num'>{round(row['Total_Metros'], 2)} m</td></tr>\n"
else:
    filas_mangueras_html = "<tr><td colspan='2'>No hay datos de red física.</td></tr>"


# --- 4. CONSTRUCCIÓN DEL HTML ---
print("Ensamblando documento web...")
ruta_html = directorio_base / f"{Path(rutas['geojson']).stem}_informe_tecnico.html"

css_styles = """
<style>
    :root { --primary-color: #0056b3; --text-main: #333; --bg-light: #f8f9fa; --border-color: #e0e0e0; }
    body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: var(--text-main); line-height: 1.6; max-width: 1000px; margin: 0 auto; padding: 40px 20px; background-color: #fff; }
    header { border-bottom: 3px solid var(--primary-color); padding-bottom: 20px; margin-bottom: 40px; }
    h1 { color: var(--primary-color); margin: 0 0 10px 0; font-size: 2.2rem; }
    .subtitle { color: #666; font-size: 1.1rem; margin: 0; }
    h2 { color: #2c3e50; font-size: 1.5rem; margin-top: 40px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 40px; }
    .metric-card { background: var(--bg-light); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; border-left: 5px solid var(--primary-color); box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .metric-title { font-size: 0.85rem; color: #666; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; margin-bottom: 5px; }
    .metric-value { font-size: 1.8rem; font-weight: bold; color: #1a1a1a; margin: 0; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.95rem; }
    th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--border-color); }
    th { background-color: var(--bg-light); color: var(--text-main); font-weight: 600; }
    tr:hover { background-color: #f5f7fa; }
    td.num { text-align: right; font-family: monospace; font-size: 1rem; }
    tr.subtotal-row { font-weight: 600; background-color: #f8f9fa; border-top: 1px solid #ccc; color: #555; }
    tr.total-row { font-weight: bold; background-color: #eef2f5; border-top: 2px solid #ccc; font-size: 1.1rem; }
    .img-container { margin: 30px 0; page-break-inside: avoid; }
    img.map-render { width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .img-caption { text-align: center; font-size: 0.9rem; color: #666; margin-top: 10px; font-weight: 500; }
    @media print { body { padding: 0; } .metric-card { break-inside: avoid; } table { break-inside: avoid; } }
</style>
"""

html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Despliegue FTTH - {nombre_proyecto}</title>
    {css_styles}
</head>
<body>
    <header>
        <h1>Informe Ejecutivo FTTH: {nombre_proyecto}</h1>
        <p class="subtitle">Análisis técnico y viabilidad económica de red de acceso de nueva generación.</p>
    </header>
    
    <h2>1. Dashboard de Proyecto</h2>
    <div class="metric-grid">
        <div class="metric-card">
            <div class="metric-title">Unidades Inmobiliarias</div>
            <div class="metric-value">{int(total_portales)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Cajas CTO (Nodos)</div>
            <div class="metric-value">{int(total_ctos)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Despliegue Óptico Total</div>
            <div class="metric-value">{round(fibra_total, 2)} m</div>
        </div>
        <div class="metric-card" style="border-left-color: #28a745;">
            <div class="metric-title">Inversión (CAPEX)</div>
            <div class="metric-value">{round(coste_total, 2):,} €</div>
        </div>
    </div>
    
    <h2>2. Métricas de Topología y Atenuación Óptica</h2>
    <table>
        <thead>
            <tr><th>Elemento de Red</th><th style="text-align: right;">Métrica</th></tr>
        </thead>
        <tbody>
            <tr><td>Longitud Fibra Troncal (Alimentación)</td><td class="num">{round(fibra_troncal, 2)} m</td></tr>
            <tr><td>Longitud Fibra Acceso (Dispersión)</td><td class="num">{round(fibra_acceso, 2)} m</td></tr>
            <tr><td>Distancia Máxima de Enlace (Peor Caso)</td><td class="num">{round(dist_max, 2)} m</td></tr>
            <tr><td>Distancia Mínima de Enlace (Mejor Caso)</td><td class="num">{round(dist_min, 2)} m</td></tr>
            <tr class="subtotal-row"><td>Atenuación Estimada Máxima</td><td class="num" style="color: #c0392b;">{round(atenuacion_max, 2)} dB</td></tr>
            <tr class="subtotal-row"><td>Atenuación Estimada Media</td><td class="num" style="color: #0056b3;">{round(atenuacion_media, 2)} dB</td></tr>
        </tbody>
    </table>

    <h2>3. Lista de Compra: Mangueras Comerciales</h2>
    <table>
        <thead>
            <tr><th>Tipo de Cable</th><th style="text-align: right;">Longitud Necesaria</th></tr>
        </thead>
        <tbody>
            {filas_mangueras_html}
        </tbody>
    </table>
    
    <h2>4. Presupuesto Desglosado por Fase Constructiva</h2>
    <table>
        <thead>
            <tr><th>Concepto</th><th style="text-align: right;">Cantidad</th><th style="text-align: right;">Precio Unit.</th><th style="text-align: right;">Subtotal</th></tr>
        </thead>
        <tbody>
            <tr><td>Cableado Fibra Óptica (Promedio)</td><td class="num">{round(cant_fibra, 2)} m</td><td class="num">{precio_fibra} €</td><td class="num">{round(cant_fibra * precio_fibra, 2):,} €</td></tr>
            <tr><td>Cajas Terminales Ópticas (CTO)</td><td class="num">{int(cant_ctos)} ud</td><td class="num">{precio_cto} €</td><td class="num">{round(cant_ctos * precio_cto, 2):,} €</td></tr>
            <tr><td>Cajas de Empalme de Mazo</td><td class="num">{int(cant_empalmes)} ud</td><td class="num">{precio_empalme} €</td><td class="num">{round(cant_empalmes * precio_empalme, 2):,} €</td></tr>
            <tr><td>Kits de Conectorización y Roseta</td><td class="num">{int(cant_conectores)} ud</td><td class="num">{precio_conector} €</td><td class="num">{round(cant_conectores * precio_conector, 2):,} €</td></tr>
            <tr class="subtotal-row"><td colspan="3">SUBTOTAL MATERIAL ÓPTICO</td><td class="num">{round(sub_optico, 2):,} €</td></tr>
            
            <tr><td>Obra Civil: Tendido Aéreo (Postes)</td><td class="num">{round(cant_aereo, 2)} m</td><td class="num">{precio_aereo} €</td><td class="num">{round(cant_aereo * precio_aereo, 2):,} €</td></tr>
            <tr><td>Obra Civil: Zanja (Soterrado)</td><td class="num">{round(cant_zanja, 2)} m</td><td class="num">{precio_zanja} €</td><td class="num">{round(cant_zanja * precio_zanja, 2):,} €</td></tr>
            <tr><td>Obra Civil: Canalización Existente</td><td class="num">{round(cant_existente, 2)} m</td><td class="num">{precio_existente} €</td><td class="num">{round(cant_existente * precio_existente, 2):,} €</td></tr>
            <tr><td>Obra Civil: Despliegue en Fachada</td><td class="num">{round(cant_fachada, 2)} m</td><td class="num">{precio_fachada} €</td><td class="num">{round(cant_fachada * precio_fachada, 2):,} €</td></tr>
            <tr class="subtotal-row"><td colspan="3">SUBTOTAL OBRA CIVIL</td><td class="num">{round(sub_civil, 2):,} €</td></tr>
            
            <tr class="total-row"><td colspan="3">TOTAL INVERSIÓN GLOBAL (CAPEX)</td><td class="num" style="color: #0056b3;">{round(coste_total, 2):,} €</td></tr>
        </tbody>
    </table>
    
    <h2>5. Anexos Cartográficos</h2>
    <div class="img-container">
        <img src="area_despliegue.png" alt="Área de Despliegue" class="map-render">
        <div class="img-caption">Figura 1: Área de despliegue y viviendas afectadas</div>
    </div>
    <div class="img-container">
        <img src="distribucion_troncal.png" alt="Distribución Troncal" class="map-render">
        <div class="img-caption">Figura 2: Distribución troncal y ubicación de empalmes</div>
    </div>
    <div class="img-container">
        <img src="acceso_logico.png" alt="Acceso Lógico" class="map-render">
        <div class="img-caption">Figura 3: Acceso lógico y áreas de influencia por CTO</div>
    </div>
    <div class="img-container">
        <img src="obra_civil.png" alt="Obra Civil Densidad" class="map-render">
        <div class="img-caption">Figura 4: Densidad de fibra e infraestructura física compartida</div>
    </div>
    <div class="img-container">
        <img src="tipos_instalacion.png" alt="Tipos Instalación" class="map-render">
        <div class="img-caption">Figura 5: Métodos constructivos de la red física (Aéreo, Zanja, Existente, Fachada)</div>
    </div>
</body>
</html>
"""

with open(ruta_html, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"✅ Informe maestro generado con éxito: {ruta_html}")