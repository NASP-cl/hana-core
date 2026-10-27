"""El registro: la tabla `capas` y la bitacora `corridas`.

Los servicios escriben aqui su manifiesto; la web lee de aqui y dibuja. Es la bisagra
entre ambos lados y la razon por la que agregar un servicio no toca el visualizador.

Hay dos implementaciones con la misma interfaz:
  - RegistroSupabase: produccion. Necesita HANA_SUPABASE_SECRET_KEY y HANA_SUPABASE_URL.
  - RegistroLocal:    escribe JSON en datos/registro/. Permite correr los cuatro verbos
                      sin credenciales, que es como se trabaja antes de tener proyecto.

`abrir_registro()` elige segun lo que haya en el entorno y lo dice en el log.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hana_core.contrato import Manifiesto
from hana_core.secretos import secreto_opcional

logger = logging.getLogger(__name__)

AGENTE = "hana-core/0.1"


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registro(ABC):
    """Lo que todo registro sabe hacer."""

    @abstractmethod
    def publicar(self, manifiestos: list[Manifiesto]) -> int: ...

    @abstractmethod
    def listar(self, servicio: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def anotar_corrida(self, fila: dict[str, Any]) -> None: ...

    @abstractmethod
    def ultima_corrida(self, servicio: str) -> dict[str, Any] | None: ...


class RegistroLocal(Registro):
    """Registro en disco. Mismo contrato, sin credenciales."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = carpeta
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.capas = carpeta / "capas.json"
        self.corridas = carpeta / "corridas.json"

    def _leer(self, p: Path) -> list[dict[str, Any]]:
        if not p.exists():
            return []
        return json.loads(p.read_text(encoding="utf-8"))

    def _escribir(self, p: Path, filas: list[dict[str, Any]]) -> None:
        p.write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")

    def publicar(self, manifiestos: list[Manifiesto]) -> int:
        filas = {f["capa_id"]: f for f in self._leer(self.capas)}
        for m in manifiestos:
            f = m.fila()
            f["actualizado"] = ahora()
            filas[f["capa_id"]] = f
        self._escribir(self.capas, sorted(filas.values(), key=lambda f: f["capa_id"]))
        logger.info(f"registro local: {len(manifiestos)} manifiestos en {self.capas}")
        return len(manifiestos)

    def listar(self, servicio: str | None = None) -> list[dict[str, Any]]:
        filas = self._leer(self.capas)
        return [f for f in filas if servicio is None or f["servicio"] == servicio]

    def anotar_corrida(self, fila: dict[str, Any]) -> None:
        filas = self._leer(self.corridas)
        filas.append(fila)
        self._escribir(self.corridas, filas[-200:])

    def ultima_corrida(self, servicio: str) -> dict[str, Any] | None:
        filas = [f for f in self._leer(self.corridas) if f.get("servicio") == servicio]
        return filas[-1] if filas else None


class RegistroSupabase(Registro):
    """Registro sobre PostgREST. Escribe con la secret key, que nunca llega al navegador."""

    def __init__(self, url: str, llave: str) -> None:
        self.url = url.rstrip("/")
        self._llave = llave

    def _pide(self, metodo: str, ruta: str, cuerpo: Any = None, extra: dict | None = None) -> Any:
        cabeceras = {
            "apikey": self._llave,
            "Authorization": f"Bearer {self._llave}",
            "Content-Type": "application/json",
            "User-Agent": AGENTE,
            **(extra or {}),
        }
        datos = None if cuerpo is None else json.dumps(cuerpo).encode()
        req = urllib.request.Request(f"{self.url}{ruta}", data=datos, headers=cabeceras, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt else None
        except urllib.error.HTTPError as e:
            # Nunca se imprime la llave, solo lo que respondio el servidor.
            raise RuntimeError(f"{metodo} {ruta} -> {e.code}: {e.read().decode()[:300]}") from None

    def publicar(self, manifiestos: list[Manifiesto]) -> int:
        filas = []
        for m in manifiestos:
            f = m.fila()
            f["actualizado"] = ahora()
            filas.append(f)
        self._pide(
            "POST",
            "/rest/v1/capas?on_conflict=capa_id",
            filas,
            {"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        logger.info(f"registro: {len(filas)} manifiestos publicados en capas")
        return len(filas)

    def listar(self, servicio: str | None = None) -> list[dict[str, Any]]:
        q = "/rest/v1/capas?select=capa_id,servicio,capa,tipo,ui,actualizado&order=capa_id"
        if servicio:
            q += f"&servicio=eq.{servicio}"
        return self._pide("GET", q) or []

    def anotar_corrida(self, fila: dict[str, Any]) -> None:
        self._pide("POST", "/rest/v1/corridas", [fila], {"Prefer": "return=minimal"})

    def ultima_corrida(self, servicio: str) -> dict[str, Any] | None:
        filas = self._pide(
            "GET",
            f"/rest/v1/corridas?servicio=eq.{servicio}&order=inicio.desc&limit=1",
        )
        return filas[0] if filas else None


def abrir_registro(carpeta_local: Path) -> Registro:
    """Supabase si el entorno lo permite; si no, el registro local."""
    url = secreto_opcional("HANA_SUPABASE_URL")
    llave = secreto_opcional("HANA_SUPABASE_SECRET_KEY")
    if url and llave and "PENDIENTE" not in url:
        logger.info(f"registro: Supabase ({url})")
        return RegistroSupabase(url, llave)
    logger.info(f"registro: local en {carpeta_local} (sin credenciales de Supabase)")
    return RegistroLocal(carpeta_local)
