"""Pruebas del contrato de capas.

Un estilo mal formado puede romperle el mapa a todos los usuarios. Por eso `validar`
existe como verbo separado que no escribe nada, y por eso estas reglas tienen prueba.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from hana_core.contrato import (
    CONTRATO,
    ArchivoEstilo,
    EstiloContinuo,
    Fuente,
    Manifiesto,
    Meta,
)

META = Meta(
    autor="Fuente de ejemplo", version="1.0.0", actualizado="2026-10-21",
    unidad="indice", resolucion="10 m", rango="2020 - 2026", frecuencia="Diaria",
)
ESTILO = {"escala": "continua", "dominio": [0.0, 1.0], "paleta": ["#CDE6DD", "#004651"]}


def manifiesto(**kw):
    base = dict(
        capa="indice", servicio="ejemplo", tipo="raster_tiles", nombre="Indice",
        titulo="Indice de ejemplo", descripcion="x", meta=META,
        fuente=Fuente(clase="pmtiles", url="https://r2.example/{fecha}.pmtiles"),
        estilo=ESTILO,
        leyenda={"titulo": "Indice", "unidad": "indice", "decimales": 2},
        ui={"grupo": "General", "orden": 10},
    )
    return Manifiesto(**{**base, **kw})


# ------------------------------------------------------------------ estilo
def test_paleta_y_dominio_deben_calzar():
    with pytest.raises(ValidationError, match="mismo largo"):
        EstiloContinuo(escala="continua", dominio=[0, 1, 2], paleta=["#fff", "#000"])


def test_dominio_debe_ir_creciendo():
    with pytest.raises(ValidationError, match="creciente"):
        EstiloContinuo(escala="continua", dominio=[1, 0], paleta=["#fff", "#000"])


def test_color_invalido_se_rechaza():
    with pytest.raises(ValidationError, match="hex"):
        EstiloContinuo(escala="continua", dominio=[0, 1], paleta=["verde", "#000"])


def test_campo_de_mas_se_rechaza():
    """extra=forbid: un typo falla en `validar`, no en produccion."""
    with pytest.raises(ValidationError):
        EstiloContinuo(escala="continua", dominio=[0, 1], paleta=["#fff", "#000"], opacidd=0.5)


# ------------------------------------------------------------------ manifiesto
def test_manifiesto_minimo_vale():
    m = manifiesto()
    assert m.contrato == CONTRATO
    assert m.fila()["capa_id"] == "ejemplo.indice"


def test_tipo_desconocido_se_rechaza():
    with pytest.raises(ValidationError):
        manifiesto(tipo="holograma")


def test_rol_desconocido_se_rechaza():
    with pytest.raises(ValidationError, match="roles desconocidos"):
        manifiesto(roles=["admin", "vecino"])


def test_nombre_de_capa_debe_ser_slug():
    with pytest.raises(ValidationError, match="minusculas"):
        manifiesto(capa="Indice Bonito")


def test_contrato_distinto_se_rechaza():
    with pytest.raises(ValidationError, match="contrato"):
        manifiesto(contrato=99)


def test_fuente_pmtiles_necesita_url():
    with pytest.raises(ValidationError, match="necesita url"):
        manifiesto(fuente={"clase": "pmtiles"})


def test_fila_lleva_todo_lo_que_la_web_necesita():
    f = manifiesto().fila()
    for campo in ("tipo", "estilo", "leyenda", "ui", "meta", "fuente", "roles", "params"):
        assert campo in f, f"falta {campo} en la fila de capas"


# ------------------------------------------------------------------ archivo de estilo
def test_capas_repetidas_se_rechazan():
    entrada = {"capa": "indice", "estilo": ESTILO,
               "leyenda": {"titulo": "Indice"}, "ui": {"grupo": "General"}}
    with pytest.raises(ValidationError, match="repetidas"):
        ArchivoEstilo(contrato=1, capas=[entrada, entrada])
