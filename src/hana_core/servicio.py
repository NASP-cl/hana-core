"""El protocolo que cumple todo servicio de HANA.

Un servicio es un modulo que sabe producir un dato y anunciarlo. Todos tienen la misma
forma, y esa uniformidad es lo que permite agregarlos y quitarlos sin tocar el resto:
el programador de tareas solo conoce los cuatro verbos, nunca el servicio.

Un servicio concreto hereda de ServicioBase y entrega dos cosas:
    manifiestos()  ->  que capas publica y como se dibujan
    ejecutar()     ->  el pipeline que produce los datos

Todo lo demas (cargar y validar config, abrir el registro, anotar la corrida, los
verbos de linea de comandos) lo pone este modulo, igual para todos.
"""
from __future__ import annotations

import inspect
import json
import logging
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hana_core.contrato import CONTRATO, ArchivoEstilo, Manifiesto
from hana_core.registro import Registro, abrir_registro
from hana_core.rutas import PathManager, raiz_proyecto

logger = logging.getLogger(__name__)


@dataclass
class Resultado:
    """Lo que devuelve una corrida. Alimenta la tabla `corridas`."""

    filas: int = 0
    mensaje: str = ""
    archivos: list[str] = field(default_factory=list)


class ErrorDeContrato(Exception):
    """La configuracion o el estilo no cumplen el contrato. Lo levanta `validar`."""


class ServicioBase(ABC):
    """Base comun. No se instancia directamente."""

    #: nombre corto, igual al de la carpeta y al de `servicio.toml`
    nombre: str = ""
    #: version del contrato de capas que habla este servicio
    contrato: int = CONTRATO

    def __init__(self, raiz: Path | None = None) -> None:
        if not self.nombre:
            raise ErrorDeContrato(f"{type(self).__name__} no declara `nombre`")
        if raiz is None:
            # La raiz es la carpeta del servicio: se busca desde el archivo de la clase hija.
            raiz = raiz_proyecto(Path(inspect.getfile(type(self))).parent)
        self.rutas = PathManager(self.nombre, raiz)
        self._descriptor: dict[str, Any] | None = None
        self._config: dict[str, Any] | None = None
        self._estilos: ArchivoEstilo | None = None

    # ------------------------------------------------------------------ carga
    @property
    def descriptor(self) -> dict[str, Any]:
        """`servicio.toml`: identidad, capas que publica, agenda y secretos."""
        if self._descriptor is None:
            p = self.rutas.servicio_toml
            if not p.exists():
                raise ErrorDeContrato(f"falta {p}")
            self._descriptor = tomllib.loads(p.read_text(encoding="utf-8"))
        return self._descriptor

    @property
    def config(self) -> dict[str, Any]:
        """`config/config.json`: los parametros del proceso."""
        if self._config is None:
            p = self.rutas.config_json
            if not p.exists():
                raise ErrorDeContrato(f"falta {p}")
            self._config = json.loads(p.read_text(encoding="utf-8"))
        return self._config

    @property
    def estilos(self) -> ArchivoEstilo:
        """`config/estilo.json`: EL archivo que se edita para cambiar como se ve algo."""
        if self._estilos is None:
            p = self.rutas.estilo_json
            if not p.exists():
                raise ErrorDeContrato(f"falta {p}")
            try:
                self._estilos = ArchivoEstilo.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception as e:
                raise ErrorDeContrato(f"{p}: {e}") from None
        return self._estilos

    def registro(self) -> Registro:
        return abrir_registro(self.rutas.registro_local)

    # ------------------------------------------------------- lo que cada uno pone
    @abstractmethod
    def manifiestos(self) -> list[Manifiesto]:
        """Las capas que publica este servicio, ya combinadas con su estilo."""

    @abstractmethod
    def ejecutar(self, prueba: bool = False) -> Resultado:
        """El pipeline. Con `prueba=True` no escribe nada: solo dice que haria."""

    # ------------------------------------------------------------------ verbos
    def validar(self) -> list[str]:
        """Revisa contrato, descriptor, config, estilo y secretos. No escribe nada.

        Devuelve la lista de problemas: vacia significa que esta todo bien.
        """
        problemas: list[str] = []

        if self.contrato != CONTRATO:
            problemas.append(f"el servicio habla contrato {self.contrato} y core {CONTRATO}")

        try:
            d = self.descriptor
            if d["servicio"]["nombre"] != self.nombre:
                problemas.append(
                    f"servicio.toml dice {d['servicio']['nombre']!r} y la clase {self.nombre!r}"
                )
            declaradas = set(d.get("publica", {}).get("capas", []))
        except (ErrorDeContrato, KeyError) as e:
            problemas.append(str(e))
            declaradas = set()

        try:
            self.config
        except ErrorDeContrato as e:
            problemas.append(str(e))

        try:
            self.estilos
        except ErrorDeContrato as e:
            problemas.append(str(e))

        if not problemas:
            try:
                ms = self.manifiestos()
            except Exception as e:
                problemas.append(f"no se pudieron armar los manifiestos: {e}")
                ms = []
            publicadas = {m.capa for m in ms}
            if declaradas and publicadas != declaradas:
                sobran = sorted(publicadas - declaradas)
                faltan = sorted(declaradas - publicadas)
                if sobran:
                    problemas.append(f"capas que no declara servicio.toml: {sobran}")
                if faltan:
                    problemas.append(f"capas declaradas que nadie publica: {faltan}")

        from hana_core.secretos import faltantes

        requeridos = self.descriptor.get("secretos", {}).get("requiere", []) if not problemas else []
        sin_definir = faltantes(requeridos)
        if sin_definir:
            # No es un error: sin credenciales el servicio corre contra el registro local.
            logger.warning(f"secretos sin definir (se usara el registro local): {sin_definir}")

        return problemas

    def registrar(self) -> int:
        """Publica el manifiesto en el registro. Idempotente."""
        ms = self.manifiestos()
        n = self.registro().publicar(ms)
        logger.info(f"registradas {n} capas: {', '.join(m.capa for m in ms)}")
        return n

    def correr(self, prueba: bool = False) -> Resultado:
        """Ejecuta el pipeline y anota la corrida."""
        from hana_core.corridas import anotar

        with anotar(self.registro(), self.nombre, prueba) as corrida:
            res = self.ejecutar(prueba=prueba)
            corrida.filas = res.filas
            corrida.mensaje = res.mensaje
        return res

    def estado(self) -> dict[str, Any]:
        """Ultima corrida y capas publicadas. No escribe nada."""
        reg = self.registro()
        return {
            "servicio": self.nombre,
            "contrato": self.contrato,
            "capas": [f["capa_id"] for f in reg.listar(self.nombre)],
            "ultima_corrida": reg.ultima_corrida(self.nombre),
        }
