"""Secretos: solo variables de entorno, con el registro de Windows como respaldo.

Nunca en archivos, nunca en el log, nunca en un mensaje de error. Cada servicio lee
solo lo que declara en su `servicio.toml`, con el prefijo HANA_.

El respaldo de Windows existe porque ahi las variables de usuario viven en el registro
y una consola abierta antes de crearlas no las ve.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def secreto_opcional(nombre: str) -> str | None:
    """El valor, o None si no esta definido en ninguna parte."""
    v = os.environ.get(nombre)
    if v:
        return v
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, nombre)[0] or None
    except (ImportError, OSError):
        return None


def secreto(nombre: str) -> str:
    """El valor, o un error que dice que falta sin revelar nada."""
    v = secreto_opcional(nombre)
    if not v:
        raise SystemExit(
            f"Falta la variable de entorno {nombre}. "
            "Se define en el entorno del servidor, nunca en un archivo del repositorio."
        )
    return v


def faltantes(nombres: list[str]) -> list[str]:
    """Los que no estan definidos. Lo usa el verbo `validar`."""
    return [n for n in nombres if not secreto_opcional(n)]
