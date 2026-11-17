"""Isola suítes legadas que substituem módulos/ambiente ao serem importadas."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ambiente = dict(os.environ, GEOFENCE_RAIO_M="500")
    ambiente["PYTHONPATH"] = str(ROOT) + os.pathsep + ambiente.get("PYTHONPATH", "")
    falhas = []
    for arquivo in sorted((ROOT / "tests").glob("test_*.py")):
        print(f"\nExecutando {arquivo.name}", flush=True)
        resultado = subprocess.run([sys.executable, "-B", str(arquivo)], cwd=ROOT, env=ambiente)
        if resultado.returncode:
            falhas.append(arquivo.name)
    if falhas:
        print("Suítes com falha: " + ", ".join(falhas))
        return 1
    print("Todas as suítes offline passaram; provedores e banco não foram acessados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
