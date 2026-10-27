"""Bitacora de ejecuciones.

Con varios servicios corriendo sin supervision, sin esto el equipo esta ciego: un
servicio puede llevar dos semanas fallando en silencio y nadie lo nota hasta que un
grafico aparece vacio.
"""
from __future__ import annotations

import logging
import socket
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from hana_core.registro import Registro

logger = logging.getLogger(__name__)


@dataclass
class Corrida:
    servicio: str
    filas: int = 0
    mensaje: str = ""


@contextmanager
def anotar(registro: Registro, servicio: str, prueba: bool = False) -> Iterator[Corrida]:
    """Envuelve una corrida y deja la fila, haya terminado bien o mal."""
    c = Corrida(servicio=servicio)
    inicio = datetime.now(timezone.utc)
    t0 = time.monotonic()
    estado = "ok"
    try:
        yield c
    except Exception as e:
        estado = "error"
        c.mensaje = f"{type(e).__name__}: {e}"
        logger.error(f"corrida fallida: {c.mensaje}")
        logger.debug(traceback.format_exc())
        raise
    finally:
        fila = {
            "servicio": servicio,
            "inicio": inicio.isoformat(timespec="seconds"),
            "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "segundos": round(time.monotonic() - t0, 1),
            "estado": "prueba" if prueba and estado == "ok" else estado,
            "filas": c.filas,
            "mensaje": c.mensaje[:500],
            "equipo": socket.gethostname(),
        }
        try:
            registro.anotar_corrida(fila)
        except Exception as e:
            # Que falle la bitacora no puede tumbar la corrida.
            logger.warning(f"no se pudo anotar la corrida: {e}")
        logger.info(f"corrida {fila['estado']} en {fila['segundos']}s, {fila['filas']} filas")
