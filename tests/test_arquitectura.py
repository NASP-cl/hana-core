"""Pruebas de la revision de arquitectura.

Se arma un servicio minimo que cumple todas las reglas, se comprueba que pasa limpio,
y despues se rompe una regla a la vez para comprobar que la revision la detecta. Una
revision que nunca falla no protege nada.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hana_core.arquitectura import main, revisar, revisar_servicio

ARCHIVOS = {
    "servicio.toml": """
[servicio]
nombre   = "minimo"
version  = "0.1.0"
contrato = 1
paquete  = "hana_minimo"
resumen  = "Servicio minimo para probar la revision."

[publica]
capas = ["valor"]

[agenda]
cron = "17 3 * * *"

[secretos]
requiere = ["HANA_SUPABASE_SECRET_KEY"]
""",
    "pyproject.toml": """
[project]
name = "hana-minimo"
version = "0.1.0"
dependencies = ["hana-core"]
""",
    "config/config.json": json.dumps({"factor": 1.0}),
    "config/estilo.json": json.dumps({
        "contrato": 1,
        "capas": [{
            "capa": "valor",
            "estilo": {"escala": "continua", "dominio": [0, 1], "paleta": ["#CDE6DD", "#1C759D"]},
            "leyenda": {"titulo": "Valor"},
            "ui": {"grupo": "General"},
        }],
    }),
    "src/hana_minimo/__init__.py": '"""Minimo."""\n',
    "src/hana_minimo/__main__.py": (
        "import sys\n\nfrom hana_core.cli import main\n"
        "from hana_minimo.interface.servicio import ServicioMinimo\n\n"
        "if __name__ == '__main__':\n    sys.exit(main(ServicioMinimo()))\n"
    ),
    "src/hana_minimo/interface/__init__.py": "",
    "src/hana_minimo/interface/servicio.py": (
        "import logging\n\nfrom hana_core.servicio import ServicioBase\n"
        "from hana_minimo.process import pipeline\n\nlogger = logging.getLogger(__name__)\n\n\n"
        "class ServicioMinimo(ServicioBase):\n    nombre = 'minimo'\n"
    ),
    "src/hana_minimo/core/__init__.py": "",
    "src/hana_minimo/core/calculo.py": (
        "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
        "def escalar(valores: list[float], factor: float) -> list[float]:\n"
        "    logger.info(f'escalando {len(valores)} valores')\n"
        "    return [v * factor for v in valores]\n"
    ),
    "src/hana_minimo/process/__init__.py": "",
    "src/hana_minimo/process/pipeline.py": (
        "from pathlib import Path\n\nfrom hana_core.rutas import PathManager\n"
        "from hana_minimo.core import calculo\n\n\n"
        "def paso_1_calcular(destino: Path, factor: float) -> Path:\n"
        "    calculo.escalar([1.0], factor)\n    return destino\n\n\n"
        "def correr(rutas: PathManager, factor: float) -> dict:\n"
        "    paso_1_calcular(rutas.datos_raw, factor)\n    return {}\n"
    ),
    "src/hana_minimo/utils/__init__.py": "",
    "tests/test_calculo.py": "def test_algo():\n    assert True\n",
}


@pytest.fixture
def servicio(tmp_path: Path) -> Path:
    raiz = tmp_path / "hana-minimo"
    for rel, texto in ARCHIVOS.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    return raiz


def _agregar(p: Path, texto: str) -> None:
    p.write_text(p.read_text(encoding="utf-8") + texto, encoding="utf-8")


def test_el_servicio_minimo_no_tiene_problemas(servicio: Path):
    assert revisar(servicio) == []


def test_main_devuelve_cero_si_esta_bien_y_uno_si_no(servicio: Path, capsys):
    assert main([str(servicio)]) == 0
    _agregar(servicio / "src/hana_minimo/core/calculo.py", "\nlogger.info('hay %s', 1)\n")
    assert main([str(servicio)]) == 1
    assert "log con formato %" in capsys.readouterr().err


def test_carpeta_sin_servicio_toml(tmp_path: Path):
    assert any("no es un servicio" in p for p in revisar(tmp_path))


def test_ignora_entornos_virtuales(servicio: Path):
    malo = servicio / ".venv/lib/paquete.py"
    malo.parent.mkdir(parents=True)
    malo.write_text("logging.basicConfig()\n", encoding="utf-8")
    assert revisar(servicio) == []


def test_detecta_core_que_importa_el_proyecto(servicio: Path):
    _agregar(servicio / "src/hana_minimo/core/calculo.py", "\nfrom hana_core.rutas import PathManager\n")
    problemas = revisar(servicio)
    assert any("core/ no puede importar hana_core.rutas" in p for p in problemas)
    assert any("core/ no usa PathManager" in p for p in problemas)


def test_detecta_funcion_auxiliar_en_process(servicio: Path):
    _agregar(servicio / "src/hana_minimo/process/pipeline.py", "\ndef ayuda():\n    return 1\n")
    assert any("ayuda() no es un paso" in p for p in revisar(servicio))


def test_detecta_clase_en_process(servicio: Path):
    _agregar(servicio / "src/hana_minimo/process/pipeline.py", "\nclass Ayudante:\n    pass\n")
    assert any("la clase Ayudante va en core/" in p for p in revisar(servicio))


def test_detecta_process_que_importa_interface(servicio: Path):
    _agregar(servicio / "src/hana_minimo/process/pipeline.py", "\nfrom hana_minimo.interface import servicio\n")
    assert any("process/ no puede importar hana_minimo.interface" in p for p in revisar(servicio))


def test_detecta_kwargs_en_core(servicio: Path):
    _agregar(servicio / "src/hana_minimo/core/calculo.py", "\ndef flexible(**opciones):\n    return opciones\n")
    assert any("flexible() usa *args o **kwargs" in p for p in revisar(servicio))


def test_detecta_log_con_porcentaje(servicio: Path):
    _agregar(servicio / "src/hana_minimo/core/calculo.py", '\nlogger.info("hay %s valores", 3)\n')
    assert any("log con formato %" in p for p in revisar(servicio))


def test_detecta_basicconfig(servicio: Path):
    _agregar(servicio / "src/hana_minimo/core/calculo.py", "\nlogging.basicConfig()\n")
    assert any("basicConfig() solo en hana_core.logs" in p for p in revisar(servicio))


def test_detecta_import_relativo(servicio: Path):
    _agregar(servicio / "src/hana_minimo/core/calculo.py", "\nfrom .otro import algo\n")
    assert any("import relativo" in p for p in revisar(servicio))


def test_detecta_un_servicio_que_importa_otro(servicio: Path):
    _agregar(servicio / "src/hana_minimo/interface/servicio.py", "\nimport hana_otro_servicio\n")
    assert any("un servicio no importa a otro" in p for p in revisar(servicio))


def test_detecta_capa_sin_estilo(servicio: Path):
    toml = servicio / "servicio.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('["valor"]', '["valor", "nueva"]'), encoding="utf-8")
    assert any("estilo.json tiene" in p for p in revisar(servicio))


def test_detecta_contrato_distinto(servicio: Path):
    assert any("hana_core habla 2" in p for p in revisar_servicio(servicio, 2))


def test_detecta_servicio_sin_pruebas(servicio: Path):
    shutil.rmtree(servicio / "tests")
    assert any("tests/ no tiene ningun test_*.py" in p for p in revisar(servicio))


def test_detecta_archivo_obligatorio_faltante(servicio: Path):
    (servicio / "src/hana_minimo/utils/__init__.py").unlink()
    assert any("falta src/hana_minimo/utils/__init__.py" in p for p in revisar(servicio))


def test_detecta_dependencia_faltante(servicio: Path):
    py = servicio / "pyproject.toml"
    py.write_text(py.read_text(encoding="utf-8").replace('["hana-core"]', "[]"), encoding="utf-8")
    assert any("debe depender de hana-core" in p for p in revisar(servicio))


def test_acepta_hana_core_desde_git(servicio: Path):
    py = servicio / "pyproject.toml"
    py.write_text(
        py.read_text(encoding="utf-8").replace(
            '["hana-core"]', '["hana-core @ git+https://github.com/NASP-cl/hana-core@v0.1.0"]'
        ),
        encoding="utf-8",
    )
    assert revisar(servicio) == []
