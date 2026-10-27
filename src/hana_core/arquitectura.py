"""Revision automatica de las reglas de arquitectura que una maquina puede comprobar.

Vive en hana_core para que cada servicio la use en la misma version que su contrato:
al subir la version de hana-core, suben las reglas. Lee el codigo sin ejecutarlo.

    python -m hana_core.arquitectura                  el servicio de la carpeta actual
    python -m hana_core.arquitectura ruta/servicio    uno o varios servicios

Devuelve 0 si no hay problemas y 1 si los hay, con la lista en pantalla.

Lo que NO revisa, porque necesita criterio: que el texto este en espanol, que la logica
viva en el modulo correcto y el diseno en general. Eso queda para la revision del PR.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

from hana_core.contrato import CONTRATO

#: Mismo patron que `hana_core.contrato._NOMBRE`: el nombre del servicio es tambien
#: el prefijo de cada `capa_id`.
NOMBRE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
#: Funciones permitidas en process/: pasos numerados y el encadenador.
FUNCION_DE_PIPELINE = re.compile(r"^(paso_\d+_[a-z0-9_]+|correr)$")
#: Marcadores de formato `%` dentro de un mensaje de log.
FORMATO_PORCENTAJE = re.compile(r"%[-+ #0-9.]*[sdifrxXeEgG]")
NIVELES_LOG = {"debug", "info", "warning", "error", "exception", "critical"}
#: Carpetas que no son codigo del servicio.
IGNORADAS = {".git", ".venv", "venv", "env", "build", "dist", "datos", "outputs", "node_modules", "__pycache__"}

#: Lo que todo servicio tiene, relativo a su carpeta. `{p}` es el paquete.
OBLIGATORIOS = (
    "servicio.toml",
    "pyproject.toml",
    "config/config.json",
    "config/estilo.json",
    "src/{p}/__init__.py",
    "src/{p}/__main__.py",
    "src/{p}/interface/__init__.py",
    "src/{p}/interface/servicio.py",
    "src/{p}/core/__init__.py",
    "src/{p}/process/__init__.py",
    "src/{p}/process/pipeline.py",
    "src/{p}/utils/__init__.py",
)


# --------------------------------------------------------------------------- utilidades
def _rel(p: Path, base: Path) -> str:
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.as_posix()


def _modulos_importados(arbol: ast.AST) -> Iterator[tuple[int, str]]:
    """(linea, modulo) de cada import absoluto del archivo."""
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                yield nodo.lineno, a.name
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            yield nodo.lineno, nodo.module


def _empieza(modulo: str, prefijos: tuple[str, ...]) -> bool:
    return any(modulo == p or modulo.startswith(p + ".") for p in prefijos)


def _leer_toml(p: Path, problemas: list[str], base: Path) -> dict:
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        problemas.append(f"{_rel(p, base)}: no se pudo leer ({e})")
        return {}


def nombre_del_servicio(carpeta: Path) -> str:
    """El nombre declarado en servicio.toml; si no se puede leer, el de la carpeta."""
    try:
        return tomllib.loads((carpeta / "servicio.toml").read_text(encoding="utf-8"))["servicio"]["nombre"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return carpeta.name


def archivos_python(carpeta: Path) -> list[Path]:
    """El codigo de la carpeta, sin entornos virtuales ni datos generados."""
    return sorted(
        p for p in carpeta.rglob("*.py")
        if not any(parte in IGNORADAS for parte in p.relative_to(carpeta).parts[:-1])
    )


# ---------------------------------------------------------------------- por servicio
def revisar_servicio(carpeta: Path, contrato: int = CONTRATO) -> list[str]:
    """Problemas de forma y de capas de un servicio. Lista vacia: todo en orden.

    Args:
        carpeta: la raiz del servicio, la que tiene `servicio.toml`.
        contrato: la version del contrato contra la que se revisa.
    """
    carpeta = carpeta.resolve()
    if not (carpeta / "servicio.toml").is_file():
        return [f"{carpeta}: no es un servicio (no tiene servicio.toml)"]

    n = nombre_del_servicio(carpeta)
    pq = f"hana_{n}"
    problemas: list[str] = []

    if not NOMBRE.match(n):
        problemas.append(f"servicio.toml: el nombre {n!r} debe ser minusculas, numeros y guion bajo")

    faltan = [o.format(p=pq) for o in OBLIGATORIOS if not (carpeta / o.format(p=pq)).exists()]
    for f in faltan:
        problemas.append(f"falta {f}")

    # ---- servicio.toml
    toml = _leer_toml(carpeta / "servicio.toml", problemas, carpeta)
    s = toml.get("servicio", {})
    if toml:
        if s.get("paquete") != pq:
            problemas.append(f"servicio.toml: paquete debe ser {pq!r}")
        if s.get("contrato") != contrato:
            problemas.append(f"servicio.toml: contrato {s.get('contrato')!r}, hana_core habla {contrato}")
        if not toml.get("publica", {}).get("capas"):
            problemas.append("servicio.toml: [publica] capas no puede estar vacio")
        cron = toml.get("agenda", {}).get("cron", "")
        if len(str(cron).split()) != 5:
            problemas.append("servicio.toml: [agenda] cron debe tener 5 campos")
        malos = [x for x in toml.get("secretos", {}).get("requiere", []) if not str(x).startswith("HANA_")]
        if malos:
            problemas.append(f"servicio.toml: secretos sin prefijo HANA_: {malos}")

    # ---- estilo.json: las capas que se dibujan son las que se declaran
    estilo_p = carpeta / "config/estilo.json"
    if toml and estilo_p.exists():
        try:
            en_estilo = {c["capa"] for c in json.loads(estilo_p.read_text(encoding="utf-8"))["capas"]}
        except (ValueError, KeyError, TypeError) as e:
            problemas.append(f"config/estilo.json: no se pudo leer ({e})")
        else:
            declaradas = set(toml.get("publica", {}).get("capas", []))
            if en_estilo != declaradas:
                problemas.append(
                    f"estilo.json tiene {sorted(en_estilo)} y servicio.toml declara {sorted(declaradas)}"
                )

    # ---- pyproject.toml
    if "pyproject.toml" not in faltan:
        py = _leer_toml(carpeta / "pyproject.toml", problemas, carpeta).get("project", {})
        esperado = f"hana-{n.replace('_', '-')}"
        if py and py.get("name", "").replace("_", "-") != esperado:
            problemas.append(f"pyproject.toml: name debe ser {esperado!r}")
        if py and not any(str(d).startswith("hana-core") for d in py.get("dependencies", [])):
            problemas.append("pyproject.toml: debe depender de hana-core")

    # ---- pruebas
    if not list((carpeta / "tests").glob("test_*.py")):
        problemas.append("tests/ no tiene ningun test_*.py")

    # ---- punto de entrada: los verbos los pone hana_core, nadie los reprograma
    main = carpeta / f"src/{pq}/__main__.py"
    if main.exists() and "from hana_core.cli import main" not in main.read_text(encoding="utf-8"):
        problemas.append(f"src/{pq}/__main__.py: debe entregar el servicio a hana_core.cli.main")

    problemas += _revisar_capas_de_codigo(carpeta / "src" / pq, pq, carpeta)
    return problemas


def _revisar_capas_de_codigo(paquete: Path, pq: str, base: Path) -> list[str]:
    """Que cada carpeta del servicio importe solo lo que le corresponde."""
    problemas: list[str] = []
    if not paquete.is_dir():
        return problemas

    reglas = {
        # core/ es logica pura: no conoce el proyecto
        "core": (f"{pq}.interface", f"{pq}.process", f"{pq}.utils", "hana_core"),
        # process/ orquesta: no conoce la clase del servicio ni los verbos
        "process": (f"{pq}.interface", "hana_core.servicio", "hana_core.cli"),
        "utils": (f"{pq}.interface", f"{pq}.process"),
    }

    for archivo in sorted(paquete.rglob("*.py")):
        rel = _rel(archivo, base)
        partes = archivo.relative_to(paquete).parts
        capa = partes[0] if len(partes) > 1 else ""
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))

        for linea, mod in _modulos_importados(arbol):
            if mod.startswith("hana_") and not _empieza(mod, (pq, "hana_core")):
                problemas.append(f"{rel}:{linea}: importa {mod}; un servicio no importa a otro")
            if capa in reglas and _empieza(mod, reglas[capa]):
                problemas.append(f"{rel}:{linea}: {capa}/ no puede importar {mod}")

        if capa == "core":
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and not nodo.name.startswith("_"):
                    if nodo.args.vararg or nodo.args.kwarg:
                        problemas.append(
                            f"{rel}:{nodo.lineno}: {nodo.name}() usa *args o **kwargs; core/ pide parametros explicitos"
                        )
                usa_pm = (isinstance(nodo, ast.Name) and nodo.id == "PathManager") or (
                    isinstance(nodo, ast.ImportFrom) and any(a.name == "PathManager" for a in nodo.names)
                )
                if usa_pm:
                    problemas.append(f"{rel}:{nodo.lineno}: core/ no usa PathManager; recibe pathlib.Path")

        if capa == "process" and archivo.name != "__init__.py":
            for nodo in arbol.body:
                if isinstance(nodo, ast.ClassDef):
                    problemas.append(f"{rel}:{nodo.lineno}: process/ solo orquesta; la clase {nodo.name} va en core/")
                if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and not FUNCION_DE_PIPELINE.match(nodo.name):
                    problemas.append(
                        f"{rel}:{nodo.lineno}: {nodo.name}() no es un paso (paso_N_nombre) ni correr(); "
                        "las funciones auxiliares van en core/"
                    )
    return problemas


# --------------------------------------------------------------------- todo el codigo
def revisar_codigo(archivos: list[Path], base: Path) -> list[str]:
    """Reglas de Python que valen para cualquier archivo del proyecto."""
    problemas: list[str] = []
    for archivo in archivos:
        rel = _rel(archivo, base)
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        except SyntaxError as e:
            problemas.append(f"{rel}:{e.lineno}: error de sintaxis")
            continue
        es_logs = archivo.as_posix().endswith("hana_core/logs.py")

        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.level > 0 and archivo.name != "__init__.py":
                problemas.append(f"{rel}:{nodo.lineno}: import relativo; fuera de __init__.py van absolutos")

            if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                continue
            attr = nodo.func.attr

            if attr in ("basicConfig", "addHandler") and not es_logs:
                problemas.append(
                    f"{rel}:{nodo.lineno}: {attr}() solo en hana_core.logs; usa configurar_logs en el punto de entrada"
                )

            dueno = nodo.func.value
            if attr in NIVELES_LOG and isinstance(dueno, ast.Name) and dueno.id in ("logger", "logging"):
                primero = nodo.args[0] if nodo.args else None
                con_porcentaje = (
                    isinstance(primero, ast.Constant)
                    and isinstance(primero.value, str)
                    and FORMATO_PORCENTAJE.search(primero.value)
                )
                if len(nodo.args) > 1 or con_porcentaje:
                    problemas.append(f"{rel}:{nodo.lineno}: log con formato %; usa f-string")
    return problemas


def revisar(carpeta: Path, contrato: int = CONTRATO) -> list[str]:
    """Todos los problemas de un servicio: su forma y su codigo."""
    carpeta = carpeta.resolve()
    problemas = revisar_servicio(carpeta, contrato)
    if (carpeta / "servicio.toml").is_file():
        problemas += revisar_codigo(archivos_python(carpeta), carpeta)
    return problemas


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    carpetas = [Path(a) for a in args] or [Path.cwd()]
    total = 0
    for c in carpetas:
        problemas = revisar(c)
        total += len(problemas)
        if problemas:
            print(f"{c}: {len(problemas)} problema(s)", file=sys.stderr)
            for p in problemas:
                print(f"  - {p}", file=sys.stderr)
    if total:
        print("\nLas reglas estan en CLAUDE.md; esta revision esta en hana_core/arquitectura.py.", file=sys.stderr)
        return 1
    print(f"Arquitectura: {len(carpetas)} servicio(s) revisado(s), sin problemas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
