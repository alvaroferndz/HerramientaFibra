import pandas as pd
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
from entorno import inicializar_entorno
from datos import GestorDatos
from viales import GestorVial

# --- 1. CONFIGURACIÓN Y CARGA DE DATOS ---
config, rutas = inicializar_entorno()
archivo_excel = rutas["excel"]
directorio_base = Path(rutas["fase_0"]).parent
srs_proyecto = config['proyecto']['srs']

# Extracción dinámica del nombre del proyecto
nombre_proyecto = Path(rutas["geojson"]).stem.replace('_', ' ').replace('-', ' ').title()
print(f"Generando Informe Ejecutivo para: {nombre_proyecto}")

# Carga dinámica del fondo de calles unificando el CRS
gestor_datos = GestorDatos(srs_proyecto)
gestor_vial = GestorVial(srs_proyecto)

print("Procesando cartografía y descargando viales...")
area_diseno, poligono_base, _, _ = gestor_datos.cargar_area_diseno(rutas["geojson"])
_, viales = gestor_vial.obtener_red_vial(poligono_base)

# Carga de las capas finales del despliegue (ya proyectadas correctamente)
portales = gpd.read_file(rutas["fase_2"], layer="Portales_Demanda")
ctos = gpd.read_file(rutas["fase_2"], layer="Nodos_CTO")
olt = gpd.read_file(rutas["fase_2"], layer="Nodo_OLT")
troncal = gpd.read_file(rutas["fase_2"], layer="Distribucion_Logica")
acceso = gpd.read_file(rutas["fase_2"], layer="Acceso_Logico")
infraestructura = gpd.read_file(rutas["fase_2"], layer="Canalizacion_Publica")

try:
    empalmes = gpd.read_file(rutas["fase_2"], layer="Cajas_Empalme")
    cant_empalmes = len(empalmes)
except Exception:
    empalmes = gpd.GeoDataFrame()
    cant_empalmes = 0


# --- 2. RENDERIZADO AUTOMÁTICO DE MAPAS (PNG) ---
print("Generando capturas cartográficas...")

# Mapa 1: Área de Despliegue
ruta_img_area = directorio_base / "area_despliegue.png"
fig, ax = plt.subplots(figsize=(12, 10))
viales.plot(ax=ax, color='#e0e0e0', linewidth=1, zorder=1)
area_diseno[area_diseno.geometry.type == 'Polygon'].plot(ax=ax, color='none', edgecolor='black', linewidth=2.5, zorder=2)
portales.plot(ax=ax, color='#0056b3', markersize=15, alpha=0.6, zorder=3)
olt.plot(ax=ax, color='#8e44ad', marker='s', markersize=150, edgecolor='black', zorder=4)
ax.axis('off')
plt.savefig(ruta_img_area, dpi=300, bbox_inches='tight')
plt.close()

# Mapa 2: Distribución Troncal
ruta_img_troncal = directorio_base / "distribucion_troncal.png"
fig, ax = plt.subplots(figsize=(12, 10))
viales.plot(ax=ax, color='#f0f0f0', linewidth=1, zorder=1)
troncal.plot(ax=ax, color='#e67e22', linewidth=2.5, zorder=2)
ctos.plot(ax=ax, color='#16a085', marker='^', markersize=80, edgecolor='black', zorder=3)
olt.plot(ax=ax, color='#8e44ad', marker='s', markersize=150, edgecolor='black', zorder=4)
if not empalmes.empty:
    empalmes.plot(ax=ax, color='#c0392b', marker='*', markersize=120, edgecolor='white', zorder=5)
ax.axis('off')
plt.savefig(ruta_img_troncal, dpi=300, bbox_inches='tight')
plt.close()

# Mapa 3: Acceso Lógico
ruta_img_acceso = directorio_base / "acceso_logico.png"
fig, ax = plt.subplots(figsize=(12, 10))
viales.plot(ax=ax, color='#f0f0f0', linewidth=1, zorder=1)
acceso.plot(ax=ax, color='#3498db', linewidth=1, alpha=0.7, zorder=2)
ctos.plot(ax=ax, color='#16a085', marker='^', markersize=80, edgecolor='black', zorder=3)
portales.plot(ax=ax, color='#2c3e50', markersize=10, zorder=4)
ax.axis('off')
plt.savefig(ruta_img_acceso, dpi=300, bbox_inches='tight')
plt.close()

# Mapa 4: Obra Civil
ruta_img_obra = directorio_base / "obra_civil.png"
fig, ax = plt.subplots(figsize=(12, 10))
viales.plot(ax=ax, color='#f0f0f0', linewidth=1, zorder=1)
infraestructura.plot(ax=ax, column='total_fibras', cmap='YlOrRd', linewidth=3, legend=True, zorder=2)
ctos.plot(ax=ax, color='black', marker='^', markersize=50, zorder=3)
olt.plot(ax=ax, color='#8e44ad', marker='s', markersize=150, edgecolor='black', zorder=4)
ax.axis('off')
plt.savefig(ruta_img_obra, dpi=300, bbox_inches='tight')
plt.close()


# --- 3. EXTRACCIÓN DE MÉTRICAS DEL EXCEL ---
print("Extrayendo métricas y presupuesto...")

# Lectura basada en nombres de columnas para evitar fallos por desplazamiento
df_analisis = pd.read_excel(archivo_excel, sheet_name='Analisis_Fibra', skiprows=6)
total_ctos = df_analisis['ID_CTO'].dropna().nunique()
total_portales = df_analisis['Portales_Cubiertos'].sum()
fibra_troncal = df_analisis['Fibra_Troncal_m'].sum()
fibra_acceso = df_analisis['Fibra_Acceso_Total_m'].sum()
fibra_total = fibra_troncal + fibra_acceso
dist_max = df_analisis['Total_OLT_a_Portal_m'].max()
dist_min = df_analisis['Total_OLT_a_Portal_m'].min()
dist_media = df_analisis['Total_OLT_a_Portal_m'].mean()

# Lectura de la hoja de costes
df_precios = pd.read_excel(archivo_excel, sheet_name='Resumen_Costes', header=None)
precio_fibra = df_precios.iloc[2, 1]
precio_cto = df_precios.iloc[3, 1]
precio_empalme = df_precios.iloc[4, 1]
precio_conector = df_precios.iloc[5, 1]

df_costes = pd.read_excel(archivo_excel, sheet_name='Resumen_Costes', skiprows=7)
cant_fibra = df_costes.loc[df_costes['Concepto'].str.contains('Fibra', na=False, case=False), 'Cantidad'].values[0]
cant_ctos = df_costes.loc[df_costes['Concepto'].str.contains('CTO', na=False, case=False), 'Cantidad'].values[0]
cant_empalmes = df_costes.loc[df_costes['Concepto'].str.contains('Empalme', na=False, case=False), 'Cantidad'].values[0]
cant_conectores = df_costes.loc[df_costes['Concepto'].str.contains('Conector', na=False, case=False), 'Cantidad'].values[0]

sub_fibra = cant_fibra * precio_fibra
sub_cto = cant_ctos * precio_cto
sub_empalme = cant_empalmes * precio_empalme
sub_conector = cant_conectores * precio_conector
coste_total = sub_fibra + sub_cto + sub_empalme + sub_conector


# --- 4. GENERACIÓN DEL HTML CORPORATIVO ---
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
    tr.total-row { font-weight: bold; background-color: #eef2f5; border-top: 2px solid #ccc; }
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
            <div class="metric-title">Inversión Material (CAPEX)</div>
            <div class="metric-value">{round(coste_total, 2):,} €</div>
        </div>
    </div>
    
    <h2>2. Métricas de Topología e Infraestructura</h2>
    <table>
        <thead>
            <tr><th>Elemento de Red</th><th style="text-align: right;">Métrica</th></tr>
        </thead>
        <tbody>
            <tr><td>Longitud Fibra Troncal (Alimentación)</td><td class="num">{round(fibra_troncal, 2)} m</td></tr>
            <tr><td>Longitud Fibra Acceso (Dispersión)</td><td class="num">{round(fibra_acceso, 2)} m</td></tr>
            <tr><td>Cajas de Empalme / Torpedos</td><td class="num">{int(cant_empalmes)} ud</td></tr>
            <tr><td>Distancia Media al Hogar (OLT -> Portal)</td><td class="num">{round(dist_media, 2)} m</td></tr>
            <tr><td>Distancia Máxima de Atenuación (Peor Caso)</td><td class="num">{round(dist_max, 2)} m</td></tr>
            <tr><td>Distancia Mínima (Mejor Caso)</td><td class="num">{round(dist_min, 2)} m</td></tr>
        </tbody>
    </table>
    
    <h2>3. Presupuesto Desglosado de Materiales</h2>
    <table>
        <thead>
            <tr>
                <th>Concepto</th>
                <th style="text-align: right;">Cantidad</th>
                <th style="text-align: right;">Precio Unit.</th>
                <th style="text-align: right;">Subtotal</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Cableado de Fibra Óptica</td>
                <td class="num">{round(cant_fibra, 2)} m</td>
                <td class="num">{precio_fibra} €</td>
                <td class="num">{round(sub_fibra, 2):,} €</td>
            </tr>
            <tr>
                <td>Cajas Terminales Ópticas (CTO)</td>
                <td class="num">{int(cant_ctos)} ud</td>
                <td class="num">{precio_cto} €</td>
                <td class="num">{round(sub_cto, 2):,} €</td>
            </tr>
            <tr>
                <td>Cajas de Empalme de Mazo</td>
                <td class="num">{int(cant_empalmes)} ud</td>
                <td class="num">{precio_empalme} €</td>
                <td class="num">{round(sub_empalme, 2):,} €</td>
            </tr>
            <tr>
                <td>Kits de Conectorización y Roseta</td>
                <td class="num">{int(cant_conectores)} ud</td>
                <td class="num">{precio_conector} €</td>
                <td class="num">{round(sub_conector, 2):,} €</td>
            </tr>
            <tr class="total-row">
                <td colspan="3">TOTAL INVERSIÓN MATERIAL (SIN IVA)</td>
                <td class="num" style="color: #0056b3;">{round(coste_total, 2):,} €</td>
            </tr>
        </tbody>
    </table>
    
    <h2>4. Anexos Cartográficos</h2>
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
        <img src="obra_civil.png" alt="Obra Civil" class="map-render">
        <div class="img-caption">Figura 4: Obra civil e infraestructura física (mapa de calor por densidad de fibra)</div>
    </div>
</body>
</html>
"""

with open(ruta_html, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"✅ Informe corporativo completado exitosamente: {ruta_html}")