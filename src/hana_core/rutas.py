"""Rutas de cada servicio. Nadie arma paths a mano.

Cada servicio vive en su propio repositorio, y la raiz del servicio es la carpeta que
tiene su `servicio.toml`. Ahi estan su codigo y su configuracion. Los datos que genera
van en `datos/` y `outputs/` dentro de esa misma carpeta, salvo que HANA_DATOS diga
otra cosa: asi se mudan los datos a otro disco sin tocar ningun servicio.

Las funciones de `core/` de cada servicio reciben `Path`, nunca un PathManager.
"""
from __future__ import annotations

import os
from pathlib import Path


def raiz_proyecto(desde: Path | None = None) -> Path:
    """La carpeta del servicio: la primera que tiene `servicio.toml`, subiendo.

    Busca desde `desde` (normalmente el archivo de la clase del servicio) y despues
    desde la carpeta actual. Se puede forzar con la variable de entorno HANA_RAIZ.
    """
    forzada = os.environ.get("HANA_RAIZ")
    if forzada:
        return Path(forzada).resolve()
    inicios = [p.resolve() for p in (desde, Path.cwd()) if p is not None]
    for inicio in inicios:
        for candidata in [inicio, *inicio.parents]:
            if (candidata / "servicio.toml").is_file():
                return candidata
    raise FileNotFoundError(
        f"no se encontro servicio.toml subiendo desde {', '.join(str(i) for i in inicios)}. "
        "Corre el servicio desde su carpeta o define HANA_RAIZ."
    )


class PathManager:
    """Rutas de un servicio. Se instancia en los pipelines, no en `core/`."""

    def __init__(self, servicio: str, raiz: Path | None = None, datos: Path | None = None) -> None:
        self.servicio = servicio
        self.raiz = (raiz or raiz_proyecto()).resolve()
        forzada = os.environ.get("HANA_DATOS")
        #: Donde van datos/ y outputs/. Por defecto, la carpeta del servicio.
        self.base = (datos or (Path(forzada) if forzada else self.raiz)).resolve()

    # --- carpetas del servicio
    @property
    def dir_servicio(self) -> Path:
        return self.raiz

    @property
    def dir_config(self) -> Path:
        return self.raiz / "config"

    @property
    def config_json(self) -> Path:
        return self.dir_config / "config.json"

    @property
    def estilo_json(self) -> Path:
        return self.dir_config / "estilo.json"

    @property
    def servicio_toml(self) -> Path:
        return self.raiz / "servicio.toml"

    # --- datos: originales intactos, intermedios, resultados
    @property
    def datos(self) -> Path:
        return self._mk(self.base / "datos")

    @property
    def datos_raw(self) -> Path:
        return self._mk(self.base / "datos" / "raw" / self.servicio)

    @property
    def datos_interim(self) -> Path:
        return self._mk(self.base / "datos" / "interim" / self.servicio)

    @property
    def datos_processed(self) -> Path:
        return self._mk(self.base / "datos" / "processed" / self.servicio)

    @property
    def outputs_tables(self) -> Path:
        return self._mk(self.base / "outputs" / "tables")

    @property
    def outputs_maps(self) -> Path:
        return self._mk(self.base / "outputs" / "maps")

    @property
    def outputs_logs(self) -> Path:
        return self._mk(self.base / "outputs" / "logs")

    @property
    def registro_local(self) -> Path:
        return self._mk(self.base / "datos" / "registro")

    def paso(self, n: int, nombre: str) -> Path:
        """Salida de un paso del pipeline.

        Los pasos se comunican por disco, no por memoria: si el paso 4 falla,
        se corrige y se reanuda desde el 4 sin volver a descargar nada.
        """
        return self.datos_interim / f"{n:02d}_{nombre}"

    def _mk(self, p: Path) -> Path:
        p.mkdir(parents=True, exist_ok=True)
        return p

    def __repr__(self) -> str:
        return f"PathManager(servicio={self.servicio!r}, raiz={str(self.raiz)!r}, base={str(self.base)!r})"
