"""Logs. Un logger por modulo; la configuracion global solo en el punto de entrada.

Con varios servicios corriendo bajo un programador, poder leer el log de uno sin el
ruido de los otros deja de ser comodidad y pasa a ser necesidad.

En los modulos de negocio:
    import logging
    logger = logging.getLogger(__name__)
Nunca `logging.basicConfig` fuera de aqui.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path


def configurar_logs(servicio: str, carpeta: Path | None = None, nivel: int = logging.INFO) -> None:
    """Consola siempre; archivo por servicio cuando se entrega carpeta."""
    formato = logging.Formatter(
        fmt=f"%(asctime)s  {servicio}  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)

    consola = logging.StreamHandler(sys.stderr)
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    if carpeta:
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = logging.FileHandler(carpeta / f"{servicio}.log", encoding="utf-8")
        archivo.setFormatter(formato)
        raiz.addHandler(archivo)
