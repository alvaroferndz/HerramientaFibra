# 🌐 Planificador Automatizado de Redes FTTH

Un motor de diseño lógico y físico para redes de fibra óptica hasta el hogar (FTTH). Esta herramienta automatiza el flujo de trabajo completo de la ingeniería de planta externa (OSP), desde la adquisición topográfica hasta el cálculo dinámico del presupuesto óptico, minimizando el despliegue de cableado y optimizando los recursos.

---

## 🚀 Características Principales

* **Integración Catastral Automática:** Conexión directa con el servicio WFS del Catastro para la extracción de portales y unidades inmobiliarias.
* **Topología Real (OSMnx):** Extracción y enrutamiento sobre el grafo vial real extraído de OpenStreetMap, diferenciando nodos topológicos de vértices geométricos.
* **Detección Inteligente de Empalmes:** Identificación autónoma de puntos de bifurcación y sangrado de mazo topológico para la ubicación precisa de cajas de empalme/torpedos.
* **Cálculo de Atenuación Dinámico:** Generación de un libro Excel nativo con tablas de datos y fórmulas paramétricas inyectadas para el cálculo del balance óptico en tiempo real.
* **Salida GIS Preparada:** Generación de archivos GeoPackage (.gpkg) limpios y versionados, listos para su edición e inspección visual en QGIS.

---

## 🏗️ Arquitectura y Fases del Despliegue

El sistema está orquestado en cuatro fases secuenciales independientes, lo que permite la intervención manual o la revisión técnica entre cada paso sin romper el flujo de trabajo.

### Fase 0: Adquisición y Agrupación (`000-obtencion-datos.py`)
Lee el polígono de diseño base y la central OLT desde un archivo GeoJSON. Extrae la cartografía vial, descarga los portales y ejecuta algoritmos de *clustering* paramétrico (espacial, topológico o de Voronoi) para definir las áreas de influencia geométrica de cada Caja Terminal Óptica (CTO).

### Fase 1: Optimización Geométrica (`001-optimizar-ctos.py`)
Abandona los cruces de calles estrictos para proyectar matemáticamente la posición de las CTOs sobre el trazado asfáltico (vértices geométricos). Ubica la CTO en el centro de carga de la calle curva o segmento lineal para minimizar los metros totales de acometidas privadas.

### Fase 2: Obra Civil y Enrutamiento (`002-obra-civil.py`)
Despliega el árbol de distribución. Calcula las rutas de menor esfuerzo desde la OLT hasta los clústeres (red troncal) y desde las CTOs a los portales (red de dispersión). Analiza el flujo de las fibras por la red para plantar cajas de empalme donde el cable físico se divide.

### Fase 3: Presupuesto Óptico (`003-exportar-hoja-de-calculo.py`)
Consolida las métricas espaciales en un modelo de datos estructurado. Exporta un Excel paramétrico que evalúa la atenuación extrema a extremo teniendo en cuenta longitud de fibra, conectores, pérdidas teóricas por splitters (según altas potenciales) y saltos de empalme.

A parte se ofrece la opción de ejecutar todo el proyecto a la vez para pruebas iniciales.

---

## 📂 Estructura del Proyecto

```text
📦 Planificador-FTTH
 ┣ 📂 app
 ┃ ┣ 📜 00-despliegue-completo.py     # Orquestador principal
 ┃ ┣ 📜 001-obtencion-datos.py        # Adquisición y clustering
 ┃ ┣ 📜 002-optimizar-ctos.py         # Ajuste geométrico de nodos
 ┃ ┣ 📜 003-obra-civil.py             # Enrutamiento de planta externa
 ┃ ┣ 📜 004-exportar-hoja-de-calculo.py # Generador del modelo Excel
 ┃ ┣ 📜 agrupacion.py
 ┃ ┣ 📜 datos.py
 ┃ ┣ 📜 enrutamiento.py
 ┃ ┣ 📜 entorno.py                    # Gestor de rutas dinámico
 ┃ ┗ 📜 viales.py
 ┣ 📂 out                             # Directorio autogenerado de resultados
 ┃ ┗ 📂 [nombre_proyecto]
 ┃   ┣ 🗺️ [nombre]_00_datos.gpkg
 ┃   ┣ 🗺️ [nombre]_01_ctos.gpkg
 ┃   ┣ 🗺️ [nombre]_02_obra.gpkg
 ┃   ┗ 📊 [nombre]_resumen.xlsx
 ┣ 📜 config.json                     # Parámetros de diseño del despliegue
 ┗ 📜 README.md
```

---

## 💻 Requisitos e Instalación

El proyecto requiere Python 3.9 o superior y un entorno virtual configurado con librerías de análisis geoespacial.

1. Clona el repositorio:
   ```bash
   git clone https://github.com/alvaroferndz/HerramientaFibra.git
   cd HerramientaFibra
   ```
2. Crea y activa tu entorno virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   ```
3. Instala las dependencias core:
   ```bash
   pip install requirements.txt
   ```

---

## ⚙️ Uso Básico

1. Configura tu polígono de actuación guardando un polígono y un punto (la OLT) en un archivo `.geojson`.
2. Actualiza la ruta en `config.json`.
3. Ejecuta el orquestador general para lanzar todas las fases en cadena y generar un proyecto desde cero:

```bash
python app/00-despliegue-completo.py
```

*Nota: Si prefieres ajustar manualmente las posiciones topológicas en QGIS, puedes ejecutar los scripts secuencialmente. Guarda tus cambios en el `.gpkg` de la fase correspondiente antes de lanzar el siguiente script.*