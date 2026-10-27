"""Contrato de capas de HANA: lo unico que la web necesita para dibujar algo.

Un servicio no entrega solo datos: entrega tambien las instrucciones para dibujarlos.
Ese paquete de instrucciones es el Manifiesto, y se publica en la tabla `capas`.

La web conoce TIPOS de capa, no capas. Un tipo que no reconoce lo ignora sin romperse:
esa compatibilidad hacia adelante es lo que permite agregar servicios sin desplegar la web.

Al cambiar la estructura de un JSON de configuracion hay que revisar el modelo de aqui.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRATO = 1

# Los cinco renderizadores que implementa la web. Agregar uno es trabajo de la web;
# agregar una capa de un tipo ya existente no lo es.
TIPOS_RENDER = ("raster_tiles", "vector", "puntos", "serie", "panel")
ROLES = ("propietario", "piloto", "especialista", "admin")

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_NOMBRE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


class Base(BaseModel):
    """Prohibe campos extra: un typo en un JSON falla en `validar`, no en produccion."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- estilo
class EstiloContinuo(Base):
    """Rampa de color: `dominio` y `paleta` se leen por pares."""

    escala: Literal["continua"]
    dominio: list[float] = Field(min_length=2)
    paleta: list[str] = Field(min_length=2)
    opacidad: float = Field(default=1.0, ge=0, le=1)
    sin_dato: str = "transparente"

    @field_validator("paleta")
    @classmethod
    def _colores_hex(cls, v: list[str]) -> list[str]:
        malos = [c for c in v if not _HEX.match(c)]
        if malos:
            raise ValueError(f"colores que no son hex: {malos}")
        return v

    @model_validator(mode="after")
    def _coherencia(self) -> "EstiloContinuo":
        if len(self.dominio) != len(self.paleta):
            raise ValueError(
                f"dominio ({len(self.dominio)}) y paleta ({len(self.paleta)}) deben tener el mismo largo"
            )
        if self.dominio != sorted(self.dominio):
            raise ValueError("el dominio debe venir en orden creciente")
        return self


class Clase(Base):
    v: str
    color: str

    @field_validator("color")
    @classmethod
    def _color_hex(cls, c: str) -> str:
        if not _HEX.match(c):
            raise ValueError(f"{c!r} no es un color hex")
        return c


class EstiloClases(Base):
    """Categorias discretas: una entrada por clase."""

    escala: Literal["clases"]
    clases: list[Clase] = Field(min_length=1)
    opacidad: float = Field(default=1.0, ge=0, le=1)


Estilo = Annotated[Union[EstiloContinuo, EstiloClases], Field(discriminator="escala")]


# --------------------------------------------------------------------------- resto
class Leyenda(Base):
    titulo: str
    unidad: str = ""
    decimales: int = Field(default=0, ge=0, le=6)


class UI(Base):
    """Donde aparece la capa. La web deriva sus pestanas de `grupo`."""

    grupo: str
    orden: int = 100
    visible: bool = True
    zoom_min: int | None = None


class Meta(Base):
    """Lo que la web muestra en la ficha del indicador. No es decoracion."""

    autor: str
    version: str
    actualizado: str
    unidad: str
    resolucion: str
    rango: str
    frecuencia: str


class Fuente(Base):
    """De donde salen los datos de esta capa."""

    clase: Literal["pmtiles", "cog", "tabla", "ninguna"]
    url: str | None = None
    tabla: str | None = None
    columnas: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _segun_clase(self) -> "Fuente":
        if self.clase in ("pmtiles", "cog") and not self.url:
            raise ValueError(f"una fuente {self.clase} necesita url")
        if self.clase == "tabla" and not self.tabla:
            raise ValueError("una fuente tabla necesita el nombre de la tabla")
        return self


class Manifiesto(Base):
    """Lo que un servicio publica en `capas` cada vez que corre.

    Es idempotente por (servicio, capa): volver a publicarlo actualiza la fila.
    """

    contrato: int = CONTRATO
    capa: str
    servicio: str
    tipo: Literal["raster_tiles", "vector", "puntos", "serie", "panel"]
    nombre: str
    titulo: str
    descripcion: str
    meta: Meta
    fuente: Fuente
    estilo: Estilo
    leyenda: Leyenda
    ui: UI
    roles: list[str] = Field(default_factory=lambda: ["propietario", "especialista", "admin"])
    # Parametros propios del servicio que la web necesita (por ejemplo, los limites que
    # usa un panel). Sacarlos del codigo de la web es lo que permite ajustarlos sin
    # desplegar nada.
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capa", "servicio")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _NOMBRE.match(v):
            raise ValueError(f"{v!r} debe ser minusculas, numeros y guion bajo")
        return v

    @field_validator("roles")
    @classmethod
    def _roles_validos(cls, v: list[str]) -> list[str]:
        malos = [r for r in v if r not in ROLES]
        if malos:
            raise ValueError(f"roles desconocidos: {malos}")
        return v

    @model_validator(mode="after")
    def _contrato_soportado(self) -> "Manifiesto":
        if self.contrato != CONTRATO:
            raise ValueError(
                f"este core habla contrato {CONTRATO} y el manifiesto dice {self.contrato}"
            )
        return self

    def fila(self) -> dict[str, Any]:
        """La fila tal como viaja a la tabla `capas`."""
        d = self.model_dump(mode="json")
        return {
            "capa_id": f"{self.servicio}.{self.capa}",
            "servicio": self.servicio,
            "capa": self.capa,
            "tipo": self.tipo,
            "contrato": self.contrato,
            "nombre": self.nombre,
            "titulo": self.titulo,
            "descripcion": self.descripcion,
            "meta": d["meta"],
            "fuente": d["fuente"],
            "estilo": d["estilo"],
            "leyenda": d["leyenda"],
            "ui": d["ui"],
            "roles": self.roles,
            "params": d["params"],
        }


# ------------------------------------------------------------------- archivo de estilo
class EstiloDeCapa(Base):
    """Una entrada de `config/estilo.json`: la parte del manifiesto que se edita a mano."""

    capa: str
    estilo: Estilo
    leyenda: Leyenda
    ui: UI


class ArchivoEstilo(Base):
    """`config/estilo.json` completo.

    Es EL archivo que se edita para cambiar como se ve una capa. Despues de editarlo:
    `validar` y `registrar`. La web no se toca ni se despliega.
    """

    contrato: int = CONTRATO
    capas: list[EstiloDeCapa] = Field(min_length=1)

    @model_validator(mode="after")
    def _sin_repetidas(self) -> "ArchivoEstilo":
        vistas = [c.capa for c in self.capas]
        repetidas = {c for c in vistas if vistas.count(c) > 1}
        if repetidas:
            raise ValueError(f"capas repetidas en el archivo: {sorted(repetidas)}")
        if self.contrato != CONTRATO:
            raise ValueError(f"este core habla contrato {CONTRATO}, el archivo dice {self.contrato}")
        return self

    def por_capa(self, capa: str) -> EstiloDeCapa:
        for c in self.capas:
            if c.capa == capa:
                return c
        raise KeyError(f"{capa!r} no esta en estilo.json (hay: {[c.capa for c in self.capas]})")
