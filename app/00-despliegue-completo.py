import subprocess
import sys

def ejecutar_flujo_completo():
    scripts = [
        "app/001-obtencion-datos.py",
        "app/002-optimizar-ctos.py",
        "app/003-obra-civil.py",
        "app/004-exportar-hoja-de-calculo.py",
        "app/005-informe.py"
    ]

    for script in scripts:
        print(f"--- Ejecutando {script} ---")
        resultado = subprocess.run([sys.executable, script])
        if resultado.returncode != 0:
            print(f"Error detectado en {script}. Se detiene la ejecución en cadena.")
            break

if __name__ == "__main__":
    ejecutar_flujo_completo()